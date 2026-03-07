from django.shortcuts import render, get_object_or_404, redirect
from django.views.generic import ListView, CreateView, UpdateView, DeleteView
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.http import JsonResponse, HttpResponse
from django.urls import reverse_lazy
from django.views.decorators.http import require_GET, require_POST
from django.contrib.auth.decorators import login_required
from django.db.models import Count, Q, Subquery, OuterRef, IntegerField, Value
from django.db.models.functions import Coalesce
from directory.models import Employee, Organization, SIZIssued
from directory.models.siz import SIZ, SIZNorm
from directory.models.position import Position
from directory.models.subdivision import StructuralSubdivision
from directory.forms.siz import SIZForm, SIZNormForm
from directory.mixins import AccessControlMixin, AccessControlObjectMixin
from directory.utils.permissions import AccessControlHelper
import zipfile
import io
import re
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


class SIZListView(LoginRequiredMixin, ListView):
    """
    🛡️ Показ списка СИЗ
    """
    model = SIZ
    template_name = 'directory/siz/list.html'
    context_object_name = 'siz_list'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['title'] = 'Средства индивидуальной защиты'

        # Получаем доступные организации через AccessControlHelper
        accessible_orgs = AccessControlHelper.get_accessible_organizations(
            self.request.user, self.request
        )

        # Фильтрация списка сотрудников по доступным организациям
        employees = Employee.objects.filter(organization__in=accessible_orgs)
        context['employees'] = employees.order_by('full_name_nominative')

        # Фильтрация последних выданных СИЗ по доступным организациям
        recent_issued = SIZIssued.objects.filter(
            employee__organization__in=accessible_orgs
        ).select_related('employee', 'siz')
        context['recent_issued'] = recent_issued.order_by('-issue_date')[:10]

        return context


class SIZNormCreateView(LoginRequiredMixin, CreateView):
    """
    📝 Создание нормы выдачи СИЗ
    """
    model = SIZNorm
    form_class = SIZNormForm
    template_name = 'directory/siz/norm_form.html'
    success_url = reverse_lazy('directory:siz:siz_list')

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        position_id = self.request.GET.get('position_id')
        if position_id:
            kwargs['position_id'] = position_id
        return kwargs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['title'] = 'Создание нормы выдачи СИЗ'

        position_id = self.request.GET.get('position_id')
        if position_id:
            position = Position.objects.filter(id=position_id).first()
            if position:
                context['position'] = position

        return context


def position_siz_norms(request, position_id):
    """
    📋 Представление для отображения норм СИЗ для должности
    """
    position = get_object_or_404(Position, pk=position_id)

    # Получаем все нормы СИЗ для данной должности
    base_norms = SIZNorm.objects.filter(position=position, condition='').select_related('siz')

    # Получаем уникальные условия (кроме пустых)
    conditions = SIZNorm.objects.filter(position=position).exclude(condition='').values_list('condition',
                                                                                             flat=True).distinct()

    # Формируем группы СИЗ по условиям
    groups = []
    for condition in conditions:
        norms = SIZNorm.objects.filter(position=position, condition=condition).select_related('siz').order_by('order')
        groups.append({
            'name': condition,
            'norms': norms
        })

    context = {
        'position': position,
        'base_norms': base_norms,
        'groups': groups
    }

    return render(request, 'admin/directory/position/siz_norms.html', context)


def siz_by_position_api(request):
    """
    🔍 API для получения норм СИЗ для должности по AJAX-запросу
    """
    position_id = request.GET.get('position_id')
    if not position_id:
        return JsonResponse({'error': 'Не указан ID должности'}, status=400)

    try:
        position = Position.objects.get(pk=position_id)
    except Position.DoesNotExist:
        return JsonResponse({'error': 'Должность не найдена'}, status=404)

    norms = SIZNorm.objects.filter(position=position).select_related('siz')

    # Формируем результат
    result = {
        'position_id': position.id,
        'position_name': position.position_name,
        'norms': []
    }

    for norm in norms:
        result['norms'].append({
            'id': norm.id,
            'siz_id': norm.siz.id,
            'siz_name': norm.siz.name,
            'classification': norm.siz.classification,
            'quantity': norm.quantity,
            'condition': norm.condition,
            'wear_period': norm.siz.wear_period,
            'unit': norm.siz.unit
        })

    return JsonResponse(result)


@require_GET
def get_position_siz_norms(request, position_id):
    """
    API для получения норм СИЗ для должности
    Используется для формирования лицевой стороны личной карточки
    """
    position = get_object_or_404(Position, pk=position_id)

    # Получаем все нормы СИЗ для данной должности
    norms = position.siz_norms.all().select_related('siz')

    # Формируем результат
    result = {
        'position_name': position.position_name,
        'base_norms': [],
        'conditional_norms': []
    }

    # Разделяем на основные и условные нормы
    for norm in norms:
        norm_data = {
            'siz_name': norm.siz.name,
            'classification': norm.siz.classification,
            'unit': norm.siz.unit,
            'quantity': norm.quantity,
            'wear_period': "До износа" if norm.siz.wear_period == 0 else f"{norm.siz.wear_period} мес."
        }

        if norm.condition:
            # Если есть условие - добавляем в условные нормы
            result['conditional_norms'].append({
                'condition': norm.condition,
                'norm': norm_data
            })
        else:
            # Иначе - в основные
            result['base_norms'].append(norm_data)

    return JsonResponse(result)


@require_GET
def get_employee_issued_siz(request, employee_id):
    """
    API для получения фактически выданных СИЗ сотруднику
    Используется для формирования оборотной стороны личной карточки
    """
    employee = get_object_or_404(Employee, pk=employee_id)

    # Здесь должен быть код для получения выданных СИЗ
    # Пока это заглушка, т.к. у нас нет соответствующей модели

    # TODO: Заменить на получение реальных данных, когда будет модель выдачи СИЗ
    issued_siz = []

    return JsonResponse({
        'employee_name': f"{employee.last_name} {employee.first_name}",
        'position': employee.position.position_name if employee.position else "",
        'issued_siz': issued_siz
    })


@require_GET
def get_siz_details(request, siz_id):
    """
    🔍 API для получения детальной информации о СИЗ
    Используется для автозаполнения полей в форме редактирования норм
    """
    siz = get_object_or_404(SIZ, pk=siz_id)

    # Формируем данные о СИЗ для отображения в форме
    result = {
        'id': siz.id,
        'name': siz.name,
        'classification': siz.classification,
        'unit': siz.unit,
        'wear_period': siz.wear_period,
        'wear_period_display': "До износа" if siz.wear_period == 0 else f"{siz.wear_period} мес."
    }

    return JsonResponse(result)


# =============================================
# КАТАЛОГ СИЗ — CRUD
# =============================================

class SIZCreateView(LoginRequiredMixin, CreateView):
    """Создание новой позиции в каталоге СИЗ"""
    model = SIZ
    form_class = SIZForm
    template_name = 'directory/siz/catalog_form.html'
    success_url = reverse_lazy('directory:siz:siz_catalog')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['title'] = 'Добавить СИЗ в каталог'
        return context


class SIZUpdateView(LoginRequiredMixin, UpdateView):
    """Редактирование позиции каталога СИЗ"""
    model = SIZ
    form_class = SIZForm
    template_name = 'directory/siz/catalog_form.html'
    success_url = reverse_lazy('directory:siz:siz_catalog')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['title'] = f'Редактировать: {self.object.name}'
        return context


class SIZDeleteView(LoginRequiredMixin, DeleteView):
    """Удаление позиции из каталога СИЗ"""
    model = SIZ
    template_name = 'directory/siz/catalog_delete.html'
    success_url = reverse_lazy('directory:siz:siz_catalog')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['title'] = 'Удалить СИЗ из каталога'
        return context


class SIZCatalogView(LoginRequiredMixin, ListView):
    """Каталог СИЗ с возможностью редактирования"""
    model = SIZ
    template_name = 'directory/siz/catalog.html'
    context_object_name = 'siz_list'
    paginate_by = 50

    def get_queryset(self):
        qs = SIZ.objects.all().order_by('name')
        search = self.request.GET.get('q')
        if search:
            qs = qs.filter(name__icontains=search)
        return qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['title'] = 'Каталог СИЗ'
        context['search'] = self.request.GET.get('q', '')
        return context


# =============================================
# МАССОВАЯ ГЕНЕРАЦИЯ КАРТОЧЕК СИЗ
# =============================================


class SIZMassGenerationView(LoginRequiredMixin, ListView):
    """
    📦 Карточки СИЗ - генерация по структурным подразделениям
    """
    model = StructuralSubdivision
    template_name = 'directory/siz/mass_generation.html'
    context_object_name = 'subdivisions'

    def _get_selected_org_id(self):
        """Определяем выбранную организацию из GET (приоритет) → сессия"""
        org_id_param = self.request.GET.get('org') or self.request.session.get('selected_org_id')
        if org_id_param:
            try:
                return int(org_id_param)
            except (ValueError, TypeError):
                pass
        return None

    def get_queryset(self):
        """Получаем только те подразделения, где есть сотрудники с нормами СИЗ"""
        accessible_orgs = AccessControlHelper.get_accessible_organizations(
            self.request.user, self.request
        )

        selected_org_id = self._get_selected_org_id()
        if selected_org_id and accessible_orgs.filter(id=selected_org_id).exists():
            accessible_orgs = accessible_orgs.filter(id=selected_org_id)

        # Subquery to count employees with SIZ norms per subdivision.
        # Учитываем три варианта связи с подразделением: через отдел, через subdivision у должности и напрямую у сотрудника.
        employees_with_norms = Employee.objects.filter(
            (
                Q(position__siz_norms__isnull=False) |
                Q(position__position_name__in=Position.objects.filter(
                    siz_norms__isnull=False
                ).values_list('position_name', flat=True))
            ) &
            (
                Q(position__department__subdivision=OuterRef('pk')) |
                Q(position__subdivision=OuterRef('pk')) |
                Q(subdivision=OuterRef('pk'))
            )
        ).order_by().values(
            dummy=Value(1)
        ).annotate(
            count=Count('id', distinct=True)
        ).values('count')

        queryset = StructuralSubdivision.objects.filter(
            organization__in=accessible_orgs
        ).annotate(
            # Annotate the main queryset with the count from the subquery.
            # Use Coalesce to handle cases where a subdivision has no such employees (results in NULL).
            employees_with_norms_count=Coalesce(
                Subquery(employees_with_norms, output_field=IntegerField()),
                0
            )
        ).filter(
            # Now filter the main queryset to only include subdivisions with more than 0 such employees.
            employees_with_norms_count__gt=0
        ).select_related('organization').order_by('organization__full_name_ru', 'name')

        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['title'] = 'Карточки СИЗ'

        # Организации с сотрудниками без подразделений, у которых есть нормы СИЗ
        accessible_orgs = AccessControlHelper.get_accessible_organizations(
            self.request.user, self.request
        )

        selected_org_id = self._get_selected_org_id()
        if selected_org_id and accessible_orgs.filter(id=selected_org_id).exists():
            accessible_orgs = accessible_orgs.filter(id=selected_org_id)

        orgs_no_subdivision = self._get_orgs_no_subdivision_with_siz(accessible_orgs)
        context['orgs_no_subdivision'] = orgs_no_subdivision

        return context

    @staticmethod
    def _get_orgs_no_subdivision_with_siz(accessible_orgs):
        """Организации с сотрудниками без подразделения, у которых есть нормы СИЗ"""
        employees_qs = Employee.objects.filter(
            status='active',
            position__isnull=False,
            organization__in=accessible_orgs,
            subdivision__isnull=True,
            position__subdivision__isnull=True,
            position__department__isnull=True,
        ).filter(
            Q(position__siz_norms__isnull=False) |
            Q(position__position_name__in=Position.objects.filter(
                siz_norms__isnull=False
            ).values_list('position_name', flat=True))
        )

        org_counts = (
            employees_qs
            .values('organization_id')
            .annotate(employees_count=Count('id', distinct=True))
            .filter(employees_count__gt=0)
        )

        org_ids = [item['organization_id'] for item in org_counts]
        counts_map = {item['organization_id']: item['employees_count'] for item in org_counts}

        orgs = Organization.objects.filter(id__in=org_ids).order_by('full_name_ru')

        return [
            {'organization': org, 'employees_count': counts_map[org.id]}
            for org in orgs
        ]


@login_required
@require_POST
def generate_siz_cards_bulk(request):
    """
    📦 Генерация ZIP-архива с карточками СИЗ для выбранных подразделений
    """
    from directory.document_generators.siz_card_docx_generator import generate_siz_card_docx

    subdivision_ids = request.POST.getlist('subdivision_ids')
    organization_ids = request.POST.getlist('organization_ids')
    issue_date = request.POST.get('issue_date') or ''

    if not subdivision_ids and not organization_ids:
        return HttpResponse("Не выбрано ни одного подразделения", status=400)

    issue_date_display = ''
    if issue_date:
        try:
            issue_date_display = datetime.strptime(issue_date, '%Y-%m-%d').strftime('%d.%m.%Y')
        except ValueError:
            issue_date_display = issue_date

    custom_context = {
        'siz_issue_date': issue_date_display
    }

    # Создаём ZIP-архив в памяти
    zip_buffer = io.BytesIO()

    with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
        generated_count = 0
        errors = []

        for subdivision_id in subdivision_ids:
            try:
                subdivision = StructuralSubdivision.objects.get(pk=subdivision_id)

                # Получаем всех сотрудников подразделения, у которых есть нормы СИЗ
                employees = Employee.objects.filter(
                    Q(position__department__subdivision=subdivision) |
                    Q(position__subdivision=subdivision) |
                    Q(subdivision=subdivision)
                ).select_related(
                    'position',
                    'position__department',
                    'position__subdivision'
                ).distinct()

                for employee in employees:
                    if not employee.position:
                        continue

                    # Проверяем, есть ли нормы для должности (прямо или через эталонную)
                    has_norms = SIZNorm.objects.filter(position=employee.position).exists()

                    if not has_norms:
                        # Ищем эталонную должность
                        reference_positions = Position.objects.filter(
                            position_name=employee.position.position_name
                        )
                        has_norms = any(
                            SIZNorm.objects.filter(position=pos).exists()
                            for pos in reference_positions
                        )

                    if not has_norms:
                        continue

                    # Генерируем карточку
                    try:
                        result = generate_siz_card_docx(
                            employee,
                            request.user,
                            custom_context,
                            raise_on_error=True,
                        )
                    except Exception as e:
                        errors.append(f"Ошибка генерации для {employee.full_name_nominative}: {e}")
                        continue

                    if result and 'content' in result:
                        # Формируем безопасное имя файла
                        safe_subdivision = re.sub(r'[<>:"/\\|?*]', '_', subdivision.name)
                        safe_employee = re.sub(r'[<>:"/\\|?*]', '_', employee.full_name_nominative)

                        # Добавляем файл в архив
                        file_path = f"{safe_subdivision}/{safe_employee}_карточка_СИЗ.docx"
                        zip_file.writestr(file_path, result['content'])
                        generated_count += 1

                        logger.info(f"Добавлена карточка: {file_path}")
                    else:
                        errors.append(f"Ошибка генерации для {employee.full_name_nominative}")

            except Exception as e:
                logger.error(f"Ошибка при обработке подразделения {subdivision_id}: {e}")
                errors.append(f"Ошибка подразделения ID={subdivision_id}: {str(e)}")

        # Генерация для организаций без подразделений
        for org_id in organization_ids:
            try:
                org = Organization.objects.get(pk=org_id)

                employees = Employee.objects.filter(
                    organization=org,
                    subdivision__isnull=True,
                    position__subdivision__isnull=True,
                    position__department__isnull=True,
                    position__isnull=False,
                ).select_related(
                    'position',
                    'position__department',
                    'position__subdivision',
                ).distinct()

                safe_org = re.sub(r'[<>:"/\\|?*]', '_', org.short_name_ru or org.full_name_ru)
                folder_name = f"{safe_org} (без подразделения)"

                for employee in employees:
                    has_norms = SIZNorm.objects.filter(position=employee.position).exists()
                    if not has_norms:
                        reference_positions = Position.objects.filter(
                            position_name=employee.position.position_name
                        )
                        has_norms = any(
                            SIZNorm.objects.filter(position=pos).exists()
                            for pos in reference_positions
                        )
                    if not has_norms:
                        continue

                    try:
                        result = generate_siz_card_docx(
                            employee,
                            request.user,
                            custom_context,
                            raise_on_error=True,
                        )
                    except Exception as e:
                        errors.append(f"Ошибка генерации для {employee.full_name_nominative}: {e}")
                        continue

                    if result and 'content' in result:
                        safe_employee = re.sub(r'[<>:"/\\|?*]', '_', employee.full_name_nominative)
                        file_path = f"{folder_name}/{safe_employee}_карточка_СИЗ.docx"
                        zip_file.writestr(file_path, result['content'])
                        generated_count += 1
                        logger.info(f"Добавлена карточка: {file_path}")
                    else:
                        errors.append(f"Ошибка генерации для {employee.full_name_nominative}")

            except Organization.DoesNotExist:
                errors.append(f"Организация ID={org_id} не найдена")
            except Exception as e:
                logger.error(f"Ошибка при обработке организации {org_id}: {e}")
                errors.append(f"Ошибка организации ID={org_id}: {str(e)}")

        # Добавляем файл со сводкой
        summary = f"""Массовая генерация карточек СИЗ
Дата: {datetime.now().strftime('%d.%m.%Y %H:%M')}
Сгенерировано карточек: {generated_count}

"""
        if errors:
            summary += "Ошибки:\n" + "\n".join(errors)

        zip_file.writestr("_summary.txt", summary.encode('utf-8'))

    # Отправляем архив пользователю
    zip_buffer.seek(0)
    response = HttpResponse(zip_buffer.read(), content_type='application/zip')
    response['Content-Disposition'] = f'attachment; filename="Карточки_СИЗ_{datetime.now().strftime("%Y%m%d_%H%M%S")}.zip"'

    logger.info(f"Массовая генерация завершена. Создано файлов: {generated_count}")

    return response
