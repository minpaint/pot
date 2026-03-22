from django.shortcuts import render, get_object_or_404
from django.views.generic import ListView, CreateView
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import JsonResponse, HttpResponse
from django.urls import reverse_lazy
from django.views.decorators.http import require_GET, require_POST
from django.contrib.auth.decorators import login_required
from django.db.models import Count, Q, Subquery, OuterRef, IntegerField, Value
from django.utils import timezone
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
        import calendar as _cal
        from datetime import date as _date

        context = super().get_context_data(**kwargs)
        context['title'] = 'Средства индивидуальной защиты'

        accessible_orgs = AccessControlHelper.get_accessible_organizations(
            self.request.user, self.request
        )
        selected_org_id = self.request.session.get('selected_org_id')

        # Список сотрудников для модального поиска
        employees = Employee.objects.filter(organization__in=accessible_orgs)
        if selected_org_id:
            employees = employees.filter(organization_id=selected_org_id)
        context['employees'] = employees.order_by('full_name_nominative')

        # Последние выданные СИЗ (блок 2)
        recent_qs = SIZIssued.objects.filter(
            employee__organization__in=accessible_orgs
        ).select_related('employee', 'siz', 'employee__subdivision')
        if selected_org_id:
            recent_qs = recent_qs.filter(employee__organization_id=selected_org_id)
        context['recent_issued'] = recent_qs.order_by('-issue_date', '-id')[:10]

        # ── Контроль сроков (блок 1) ──
        def _add_months(d, months):
            month = d.month - 1 + months
            year = d.year + month // 12
            month = month % 12 + 1
            day = min(d.day, _cal.monthrange(year, month)[1])
            return _date(year, month, day)

        today = timezone.now().date()
        active_qs = SIZIssued.objects.filter(
            employee__organization__in=accessible_orgs,
            is_returned=False,
            siz__wear_period__gt=0,
        ).select_related('employee', 'siz', 'employee__subdivision', 'employee__department')
        if selected_org_id:
            active_qs = active_qs.filter(employee__organization_id=selected_org_id)

        deadline_items = []
        for item in active_qs:
            planned = _add_months(item.issue_date, item.siz.wear_period)
            delta = (planned - today).days
            if delta <= 60:
                deadline_items.append({
                    'item': item,
                    'planned_return': planned,
                    'days_left': delta,
                    'is_overdue': delta < 0,
                    'is_soon': 0 <= delta <= 30,
                })
        deadline_items.sort(key=lambda x: x['days_left'])

        context['deadline_items'] = deadline_items
        context['deadline_overdue_count'] = sum(1 for x in deadline_items if x['is_overdue'])
        context['deadline_soon_count'] = sum(1 for x in deadline_items if x['is_soon'])

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
# МАССОВАЯ ГЕНЕРАЦИЯ КАРТОЧЕК СИЗ
# =============================================


def has_effective_siz_norms(position):
    """
    Проверяет, есть ли у должности эффективные нормы СИЗ.
    Логика: requires_siz=True И (есть нормы напрямую ИЛИ есть в справочнике профессий)
    """
    from directory.models import ProfessionSIZNorm

    if not position:
        return False
    if not getattr(position, 'requires_siz', True):
        return False
    if position.siz_norms.exists():
        return True
    if getattr(position, 'siz_norms_overridden', False):
        return False

    profession_lower = (position.position_name or '').lower()
    has_profession_norms = ProfessionSIZNorm.objects.filter(
        profession_name__iexact=profession_lower
    ).exists()
    if has_profession_norms:
        return True

    # Fallback: в другой должности с таким же названием есть прямые нормы.
    return Position.objects.filter(
        position_name=position.position_name,
        siz_norms__isnull=False,
    ).exclude(pk=position.pk).exists()


def extract_unique_emails(recipient_items):
    """Возвращает уникальные email в исходном порядке."""
    seen = set()
    unique = []

    for item in recipient_items or []:
        if isinstance(item, dict):
            email_value = (item.get('email') or '').strip().lower()
        else:
            email_value = str(item or '').strip().lower()

        if email_value and email_value not in seen:
            seen.add(email_value)
            unique.append(email_value)

    return unique


def _safe_name(value):
    return re.sub(r'[<>:"/\\|?*]', '_', str(value or '').strip()) or 'unknown'


def _request_value(request, key, default=''):
    return request.POST.get(key, default) if request.method == 'POST' else request.GET.get(key, default)


def _request_bool(request, key, default=False):
    raw = _request_value(request, key, None)
    if raw is None:
        return default
    return str(raw).strip().lower() in {'1', 'true', 'yes', 'on'}


def _parse_issue_date(issue_date_raw):
    if not issue_date_raw:
        return None, ''
    try:
        parsed = datetime.strptime(issue_date_raw, '%Y-%m-%d').date()
        return parsed, parsed.strftime('%d.%m.%Y')
    except ValueError:
        return None, issue_date_raw


def _subdivision_employee_queryset(subdivision):
    """
    Сотрудники подразделения с учетом всех вариантов привязки:
    1) через Employee.subdivision
    2) через Position.subdivision
    3) через Position.department.subdivision
    """
    return Employee.objects.filter(
        status='active',
        position__isnull=False
    ).annotate(
        effective_subdivision_id=Coalesce(
            'subdivision_id',
            'position__subdivision_id',
            'position__department__subdivision_id',
        )
    ).filter(
        effective_subdivision_id=subdivision.pk
    ).select_related(
        'position',
        'position__department',
        'position__subdivision'
    ).distinct()


def _subdivision_main_employee_queryset(subdivision):
    """Сотрудники основного подразделения (без отдела)."""
    return _subdivision_employee_queryset(subdivision).filter(
        department__isnull=True,
        position__department__isnull=True
    )


def _department_employee_queryset(subdivision, department):
    """Сотрудники конкретного отдела в рамках подразделения."""
    return _subdivision_employee_queryset(subdivision).filter(
        Q(department=department) | Q(position__department=department)
    )


def _create_cards_archive(employees, user, custom_context, folder_name):
    """Генерирует ZIP-архив карточек СИЗ для списка сотрудников."""
    from directory.document_generators.siz_card_docx_generator import generate_siz_card_docx

    zip_buffer = io.BytesIO()
    errors = []
    generated_count = 0
    safe_folder = _safe_name(folder_name)

    with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
        for employee in employees:
            if not employee.position or not has_effective_siz_norms(employee.position):
                continue

            try:
                result = generate_siz_card_docx(
                    employee,
                    user,
                    custom_context,
                    raise_on_error=True,
                )
            except Exception as exc:
                errors.append(f"Ошибка для {employee.full_name_nominative}: {exc}")
                continue

            if not result or 'content' not in result:
                errors.append(f"Ошибка генерации для {employee.full_name_nominative}: пустой результат")
                continue

            safe_emp = _safe_name(employee.full_name_nominative)
            zip_file.writestr(f"{safe_folder}/{safe_emp}_карточка_СИЗ.docx", result['content'])
            generated_count += 1

        summary = (
            f"Карточки СИЗ\n"
            f"Дата: {datetime.now().strftime('%d.%m.%Y %H:%M')}\n"
            f"Сгенерировано: {generated_count}\n"
        )
        if errors:
            summary += "\nОшибки:\n" + "\n".join(errors)
        zip_file.writestr("_summary.txt", summary.encode('utf-8'))

    if generated_count == 0:
        return None, 0, errors

    return zip_buffer.getvalue(), generated_count, errors


def _render_siz_email_template(email_settings, template_vars):
    template_data = email_settings.get_email_template('siz_cards')
    if not template_data:
        subject = (
            f"Карточки СИЗ: {template_vars['organization_name']} / "
            f"{template_vars['subdivision_name']} / {template_vars['department_name']}"
        )
        html_message = (
            f"<p>Направляем карточки СИЗ.</p>"
            f"<p><b>Организация:</b> {template_vars['organization_name']}<br>"
            f"<b>Подразделение:</b> {template_vars['subdivision_name']}<br>"
            f"<b>Отдел:</b> {template_vars['department_name']}<br>"
            f"<b>Дата выдачи:</b> {template_vars['date']}<br>"
            f"<b>Количество карточек:</b> {template_vars['cards_count']}</p>"
        )
        return subject, html_message

    subject_tpl, body_tpl = template_data
    try:
        subject = subject_tpl.format(**template_vars)
    except Exception:
        subject = subject_tpl

    try:
        html_message = body_tpl.format(**template_vars)
    except Exception:
        html_message = body_tpl

    return subject, html_message


def _resolve_recipients_for_send(base_recipients, test_mode, test_email, fallback_email=''):
    """Возвращает итоговый список получателей с учётом тестового режима."""
    if test_mode:
        target = (test_email or fallback_email or '').strip().lower()
        return [target] if target else []
    return extract_unique_emails(base_recipients)


def _send_cards_group(
    *,
    bulk_sender,
    email_settings,
    organization,
    subdivision_name,
    department_name,
    employees,
    recipients,
    issue_date_display,
    user,
    test_mode=False,
    test_email='',
):
    """Отправляет карточки СИЗ для одной группы (подразделение/отдел)."""
    employees = list(employees)
    if not employees:
        return {
            'status': 'skipped',
            'reason': 'no_employees',
            'cards_count': 0,
            'recipients': [],
            'message': 'Нет сотрудников для отправки',
        }

    final_recipients = _resolve_recipients_for_send(
        recipients,
        test_mode=test_mode,
        test_email=test_email,
        fallback_email=(user.email or ''),
    )
    if not final_recipients:
        return {
            'status': 'skipped',
            'reason': 'no_recipients',
            'cards_count': 0,
            'recipients': [],
            'message': 'Нет получателей для отправки',
        }

    custom_context = {'siz_issue_date': issue_date_display}
    archive_folder = f"{subdivision_name} - {department_name}"
    archive_content, cards_count, generation_errors = _create_cards_archive(
        employees=employees,
        user=user,
        custom_context=custom_context,
        folder_name=archive_folder,
    )
    if not archive_content:
        return {
            'status': 'skipped',
            'reason': 'no_cards',
            'cards_count': 0,
            'recipients': final_recipients,
            'message': 'Не удалось сгенерировать карточки',
            'errors': generation_errors,
        }

    template_vars = {
        'organization_name': organization.full_name_ru,
        'subdivision_name': subdivision_name,
        'department_name': department_name,
        'date': issue_date_display or datetime.now().strftime('%d.%m.%Y'),
        'employee_count': len(employees),
        'cards_count': cards_count,
    }
    subject, html_message = _render_siz_email_template(email_settings, template_vars)

    success, error = bulk_sender.send_email(
        subject=subject,
        body_text=subject,
        body_html=html_message,
        to_emails=final_recipients,
        attachment_name=f"{_safe_name(archive_folder)}_карточки_СИЗ.zip",
        attachment_content=archive_content,
        attachment_mimetype='application/zip',
    )

    if not success:
        return {
            'status': 'failed',
            'reason': 'email_send_failed',
            'cards_count': cards_count,
            'recipients': final_recipients,
            'message': error or 'Ошибка отправки email',
            'errors': generation_errors,
        }

    return {
        'status': 'success',
        'reason': '',
        'cards_count': cards_count,
        'recipients': final_recipients,
        'message': 'Отправлено',
        'errors': generation_errors,
    }


class SIZMassGenerationView(LoginRequiredMixin, ListView):
    """📦 Карточки СИЗ - генерация по структурным подразделениям"""
    model = StructuralSubdivision
    template_name = 'directory/siz/mass_generation.html'
    context_object_name = 'subdivisions'

    def _get_selected_org_id(self, accessible_orgs):
        """
        Выбранная организация из GET (приоритет) или из сессии.
        Если доступна только одна организация — выбираем её автоматически.
        """
        org_id_param = self.request.GET.get('org') or self.request.session.get('selected_org_id')
        selected_org_id = None

        if org_id_param:
            try:
                org_id = int(org_id_param)
                if accessible_orgs.filter(id=org_id).exists():
                    selected_org_id = org_id
            except (TypeError, ValueError):
                pass

        if selected_org_id is None and accessible_orgs.count() == 1:
            selected_org_id = accessible_orgs.first().id

        if selected_org_id:
            self.request.session['selected_org_id'] = selected_org_id

        return selected_org_id

    def get_queryset(self):
        from directory.models import ProfessionSIZNorm
        from django.db.models.functions import Lower

        accessible_orgs = AccessControlHelper.get_accessible_organizations(
            self.request.user, self.request
        )
        selected_org_id = self._get_selected_org_id(accessible_orgs)
        if selected_org_id:
            accessible_orgs = accessible_orgs.filter(id=selected_org_id)

        profession_names_with_norms = ProfessionSIZNorm.objects.annotate(
            profession_name_lower=Lower('profession_name')
        ).values_list('profession_name_lower', flat=True).distinct()
        reference_positions_with_norms = Position.objects.filter(
            siz_norms__isnull=False
        ).values_list('position_name', flat=True).distinct()

        employees_with_norms = Employee.objects.annotate(
            position_name_lower=Lower('position__position_name'),
            effective_subdivision_id=Coalesce(
                'subdivision_id',
                'position__subdivision_id',
                'position__department__subdivision_id',
            )
        ).filter(
            Q(position__requires_siz=True) & (
                Q(position__siz_norms__isnull=False) |
                Q(
                    position__siz_norms_overridden=False,
                    position_name_lower__in=profession_names_with_norms
                ) |
                Q(position__position_name__in=reference_positions_with_norms)
            ),
            effective_subdivision_id=OuterRef('pk')
        ).order_by().values(
            dummy=Value(1)
        ).annotate(
            count=Count('id', distinct=True)
        ).values('count')

        return StructuralSubdivision.objects.filter(
            organization__in=accessible_orgs
        ).annotate(
            employees_with_norms_count=Coalesce(
                Subquery(employees_with_norms, output_field=IntegerField()),
                0
            )
        ).filter(
            employees_with_norms_count__gt=0
        ).select_related('organization').order_by('organization__full_name_ru', 'name')

    def get_context_data(self, **kwargs):
        from directory.models import Department, Organization, ProfessionSIZNorm
        from django.db.models.functions import Lower

        context = super().get_context_data(**kwargs)
        context['title'] = 'Карточки СИЗ'
        accessible_orgs = AccessControlHelper.get_accessible_organizations(
            self.request.user, self.request
        )
        selected_org_id = self._get_selected_org_id(accessible_orgs)
        context['selected_org_id'] = selected_org_id

        orgs_for_context = accessible_orgs
        if selected_org_id:
            orgs_for_context = accessible_orgs.filter(id=selected_org_id)

        profession_names_with_norms = ProfessionSIZNorm.objects.annotate(
            profession_name_lower=Lower('profession_name')
        ).values_list('profession_name_lower', flat=True).distinct()

        reference_positions_with_norms = Position.objects.filter(
            siz_norms__isnull=False
        ).values_list('position_name', flat=True).distinct()

        def _employees_with_norms_qs(qs):
            return qs.annotate(
                position_name_lower=Lower('position__position_name')
            ).filter(
                Q(position__requires_siz=True) & (
                    Q(position__siz_norms__isnull=False) |
                    Q(
                        position__siz_norms_overridden=False,
                        position_name_lower__in=profession_names_with_norms
                    ) |
                    Q(position__position_name__in=reference_positions_with_norms)
                )
            ).distinct()

        # Подразделения с сотрудниками
        subdivisions = context.get('subdivisions', [])
        subdivisions_with_departments = []
        for subdivision in subdivisions:
            subdivision_employees_qs = _employees_with_norms_qs(
                _subdivision_employee_queryset(subdivision)
            ).select_related('position')
            subdivision.employees_count = subdivision_employees_qs.count()
            departments_with_employees = []

            # Сотрудники подразделения без отдела (для дерева)
            main_employees = subdivision_employees_qs.filter(
                department__isnull=True,
                position__department__isnull=True,
            ).order_by('full_name_nominative')
            subdivision.main_employees = list(main_employees)

            for dept in Department.objects.filter(subdivision=subdivision):
                dept_employees = _employees_with_norms_qs(
                    _department_employee_queryset(subdivision, dept)
                ).select_related('position').order_by('full_name_nominative')
                count = dept_employees.count()
                if count > 0:
                    dept.employees_count = count
                    dept.employees = list(dept_employees)
                    departments_with_employees.append(dept)

            subdivision.departments_with_employees = departments_with_employees
            subdivisions_with_departments.append(subdivision)

        context['subdivisions'] = subdivisions_with_departments

        # Организации, у которых есть сотрудники с нормами БЕЗ подразделения
        orgs_with_direct_employees = []
        for org in orgs_for_context:
            direct_emps_qs = _employees_with_norms_qs(
                Employee.objects.filter(
                    organization=org,
                    status='active',
                    position__isnull=False,
                    subdivision__isnull=True,
                ).annotate(
                    effective_subdivision_id=Coalesce(
                        'position__subdivision_id',
                        'position__department__subdivision_id',
                    )
                ).filter(effective_subdivision_id__isnull=True)
            ).select_related('position').order_by('full_name_nominative')
            count = direct_emps_qs.count()
            if count > 0:
                orgs_with_direct_employees.append({
                    'org': org,
                    'employees_count': count,
                    'employees': list(direct_emps_qs),
                })

        context['orgs_with_direct_employees'] = orgs_with_direct_employees
        return context


@login_required
def get_siz_recipients(request, subdivision_id):
    """
    AJAX: возвращает JSON со списком получателей для подразделения.
    Используется модальным окном подтверждения перед отправкой.
    """
    from directory.utils.email_recipients import (
        get_recipients_detailed, get_recipients_for_department
    )
    from directory.models import Department
    from directory.models import ProfessionSIZNorm
    from deadline_control.models import EmailSettings
    from django.db.models.functions import Lower

    subdivision = get_object_or_404(StructuralSubdivision, pk=subdivision_id)

    if not AccessControlHelper.can_access_object(request.user, subdivision):
        return JsonResponse({'error': 'Нет доступа'}, status=403)

    organization = subdivision.organization

    try:
        email_settings = EmailSettings.get_settings(organization)
        test_email = getattr(email_settings, 'test_recipient_email', '') or ''
    except Exception:
        test_email = ''

    subdivision_recipients_data = get_recipients_detailed(
        subdivision=subdivision,
        organization=organization,
        notification_type='siz_cards'
    )
    profession_names_with_norms = ProfessionSIZNorm.objects.annotate(
        profession_name_lower=Lower('profession_name')
    ).values_list('profession_name_lower', flat=True).distinct()
    reference_positions_with_norms = Position.objects.filter(
        siz_norms__isnull=False
    ).values_list('position_name', flat=True).distinct()

    subdivision_employees = _subdivision_main_employee_queryset(subdivision).annotate(
        position_name_lower=Lower('position__position_name')
    ).filter(
        position__requires_siz=True
    ).filter(
        Q(position__siz_norms__isnull=False) |
        Q(
            position__siz_norms_overridden=False,
            position_name_lower__in=profession_names_with_norms
        ) |
        Q(position__position_name__in=reference_positions_with_norms)
    ).distinct()

    departments_data = []
    total_employees = subdivision_employees.count()

    for dept in Department.objects.filter(subdivision=subdivision):
        dept_employees = _department_employee_queryset(subdivision, dept).annotate(
            position_name_lower=Lower('position__position_name')
        ).filter(
            position__requires_siz=True
        ).filter(
            Q(position__siz_norms__isnull=False) |
            Q(
                position__siz_norms_overridden=False,
                position_name_lower__in=profession_names_with_norms
            ) |
            Q(position__position_name__in=reference_positions_with_norms)
        ).distinct()

        count = dept_employees.count()
        if count == 0:
            continue

        total_employees += count

        recipients_info = get_recipients_for_department(
            department=dept,
            subdivision=subdivision,
            organization=organization,
            notification_type='siz_cards'
        )

        departments_data.append({
            'department_id': dept.pk,
            'department_name': dept.name,
            'employees_count': count,
            'recipients': recipients_info['recipients'],
            'fallback_used': recipients_info.get('fallback_used', False),
        })

    return JsonResponse({
        'subdivision_name': subdivision.name,
        'subdivision_employees_count': subdivision_employees.count(),
        'total_employees_count': total_employees,
        'subdivision_recipients': subdivision_recipients_data['recipients'],
        'departments': departments_data,
        'test_email': test_email,
        'skip_email_notifications': subdivision.skip_email_notifications,
    })


def _generate_siz_cards_for_org(request, org_id, issue_date):
    """Генерация ZIP-архива карточек СИЗ для всех сотрудников организации без подразделений."""
    from directory.document_generators.siz_card_docx_generator import generate_siz_card_docx
    from directory.models import Organization

    try:
        org = Organization.objects.get(pk=org_id)
    except Organization.DoesNotExist:
        return HttpResponse("Организация не найдена", status=404)

    if not AccessControlHelper.can_access_object(request.user, org) and not request.user.is_superuser:
        if not hasattr(request.user, 'profile') or org not in request.user.profile.organizations.all():
            return HttpResponse("Нет доступа к организации", status=403)

    issue_date_display = ''
    if issue_date:
        try:
            issue_date_display = datetime.strptime(issue_date, '%Y-%m-%d').strftime('%d.%m.%Y')
        except ValueError:
            issue_date_display = issue_date

    custom_context = {'siz_issue_date': issue_date_display}

    employees = Employee.objects.filter(
        organization=org,
        status='active',
        position__isnull=False,
        subdivision__isnull=True,
    ).annotate(
        effective_subdivision_id=Coalesce(
            'position__subdivision_id',
            'position__department__subdivision_id',
        )
    ).filter(
        effective_subdivision_id__isnull=True
    ).select_related('position')

    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
        generated_count = 0
        errors = []
        for employee in employees:
            if not employee.position or not has_effective_siz_norms(employee.position):
                continue
            try:
                result = generate_siz_card_docx(employee, request.user, custom_context, raise_on_error=True)
            except Exception as e:
                errors.append(f"Ошибка для {employee.full_name_nominative}: {e}")
                continue
            if result and 'content' in result:
                safe_emp = _safe_name(employee.full_name_nominative)
                zip_file.writestr(f"{safe_emp}_карточка_СИЗ.docx", result['content'])
                generated_count += 1

        summary = (
            f"Массовая генерация карточек СИЗ\n"
            f"Организация: {org.short_name_ru}\n"
            f"Дата: {datetime.now().strftime('%d.%m.%Y %H:%M')}\n"
            f"Сгенерировано: {generated_count}\n"
        )
        if errors:
            summary += "\nОшибки:\n" + "\n".join(errors)
        zip_file.writestr("_summary.txt", summary.encode('utf-8'))

    zip_buffer.seek(0)
    response = HttpResponse(zip_buffer.read(), content_type='application/zip')
    response['Content-Disposition'] = f'attachment; filename="Карточки_СИЗ_{_safe_name(org.short_name_ru)}_{datetime.now().strftime("%Y%m%d_%H%M%S")}.zip"'
    return response


@login_required
@require_POST
def generate_siz_cards_bulk(request):
    """POST: генерирует ZIP-архив с карточками СИЗ для выбранных подразделений или организации"""
    from directory.document_generators.siz_card_docx_generator import generate_siz_card_docx

    subdivision_ids = request.POST.getlist('subdivision_ids')
    org_id = request.POST.get('org_id')
    issue_date = request.POST.get('issue_date') or ''

    # Генерация для организации без подразделений
    if org_id and not subdivision_ids:
        return _generate_siz_cards_for_org(request, org_id, issue_date)

    if not subdivision_ids:
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
                employees = _subdivision_employee_queryset(subdivision)

                for employee in employees:
                    if not employee.position or not has_effective_siz_norms(employee.position):
                        continue

                    try:
                        result = generate_siz_card_docx(
                            employee,
                            request.user,
                            custom_context,
                            raise_on_error=True,
                        )
                    except Exception as e:
                        errors.append(f"Ошибка для {employee.full_name_nominative}: {e}")
                        continue

                    if result and 'content' in result:
                        safe_sub = _safe_name(subdivision.name)
                        safe_emp = _safe_name(employee.full_name_nominative)
                        zip_file.writestr(f"{safe_sub}/{safe_emp}_карточка_СИЗ.docx", result['content'])
                        generated_count += 1

            except Exception as e:
                errors.append(f"Ошибка подразделения ID={subdivision_id}: {str(e)}")

        summary = (
            f"Массовая генерация карточек СИЗ\n"
            f"Дата: {datetime.now().strftime('%d.%m.%Y %H:%M')}\n"
            f"Сгенерировано: {generated_count}\n"
        )
        if errors:
            summary += "\nОшибки:\n" + "\n".join(errors)
        zip_file.writestr("_summary.txt", summary.encode('utf-8'))

    zip_buffer.seek(0)
    response = HttpResponse(zip_buffer.read(), content_type='application/zip')
    response['Content-Disposition'] = f'attachment; filename="Карточки_СИЗ_{datetime.now().strftime("%Y%m%d_%H%M%S")}.zip"'
    return response


def _send_for_subdivision(
    *,
    request,
    subdivision,
    email_settings,
    bulk_sender,
    issue_date_display,
    test_mode=False,
    test_email='',
    summary_mode=False,
):
    """Внутренняя отправка карточек СИЗ для одного подразделения."""
    from directory.models import Department
    from directory.utils.email_recipients import (
        collect_recipients_for_subdivision, get_recipients_for_department
    )

    if subdivision.skip_email_notifications:
        return {
            'status': 'skipped',
            'successful': 0,
            'failed': 0,
            'skipped': 1,
            'total_cards': 0,
            'details': [{
                'scope': 'subdivision',
                'name': subdivision.name,
                'status': 'skipped',
                'reason': 'skip_email_notifications',
            }],
        }

    details = []
    successful = 0
    failed = 0
    skipped = 0
    total_cards = 0
    organization = subdivision.organization

    if summary_mode:
        employees = _subdivision_employee_queryset(subdivision).filter(
            position__requires_siz=True,
        )

        recipients = collect_recipients_for_subdivision(
            subdivision=subdivision,
            organization=organization,
            notification_type='siz_cards'
        )
        send_result = _send_cards_group(
            bulk_sender=bulk_sender,
            email_settings=email_settings,
            organization=organization,
            subdivision_name=subdivision.name,
            department_name='Сводный архив',
            employees=employees,
            recipients=recipients,
            issue_date_display=issue_date_display,
            user=request.user,
            test_mode=test_mode,
            test_email=test_email,
        )
        details.append({
            'scope': 'subdivision',
            'name': subdivision.name,
            **send_result,
        })
        total_cards += send_result.get('cards_count', 0)

        if send_result['status'] == 'success':
            successful += 1
        elif send_result['status'] == 'failed':
            failed += 1
        else:
            skipped += 1
    else:
        subdivision_employees = _subdivision_main_employee_queryset(subdivision).filter(
            position__requires_siz=True,
        )

        subdivision_recipients = collect_recipients_for_subdivision(
            subdivision=subdivision,
            organization=organization,
            notification_type='siz_cards'
        )
        sub_result = _send_cards_group(
            bulk_sender=bulk_sender,
            email_settings=email_settings,
            organization=organization,
            subdivision_name=subdivision.name,
            department_name='Основное подразделение',
            employees=subdivision_employees,
            recipients=subdivision_recipients,
            issue_date_display=issue_date_display,
            user=request.user,
            test_mode=test_mode,
            test_email=test_email,
        )
        details.append({
            'scope': 'subdivision',
            'name': subdivision.name,
            **sub_result,
        })
        total_cards += sub_result.get('cards_count', 0)

        if sub_result['status'] == 'success':
            successful += 1
        elif sub_result['status'] == 'failed':
            failed += 1
        else:
            skipped += 1

        for department in Department.objects.filter(subdivision=subdivision):
            dept_employees = _department_employee_queryset(subdivision, department).filter(
                position__requires_siz=True,
            )

            recipients_info = get_recipients_for_department(
                department=department,
                subdivision=subdivision,
                organization=organization,
                notification_type='siz_cards'
            )
            dept_result = _send_cards_group(
                bulk_sender=bulk_sender,
                email_settings=email_settings,
                organization=organization,
                subdivision_name=subdivision.name,
                department_name=department.name,
                employees=dept_employees,
                recipients=recipients_info['recipients'],
                issue_date_display=issue_date_display,
                user=request.user,
                test_mode=test_mode,
                test_email=test_email,
            )
            details.append({
                'scope': 'department',
                'department_id': department.id,
                'name': department.name,
                'fallback_used': recipients_info.get('fallback_used', False),
                **dept_result,
            })
            total_cards += dept_result.get('cards_count', 0)

            if dept_result['status'] == 'success':
                successful += 1
            elif dept_result['status'] == 'failed':
                failed += 1
            else:
                skipped += 1

    if successful > 0 and failed == 0 and skipped == 0:
        status = 'completed'
    elif successful > 0:
        status = 'partial'
    elif failed > 0:
        status = 'failed'
    else:
        status = 'skipped'

    return {
        'status': status,
        'successful': successful,
        'failed': failed,
        'skipped': skipped,
        'total_cards': total_cards,
        'details': details,
    }


@login_required
def send_siz_cards_for_department(request, department_id):
    """Отправка карточек СИЗ для одного отдела."""
    from directory.models import Department
    from directory.utils.bulk_email_sender import BulkEmailSender
    from directory.utils.email_recipients import get_recipients_for_department
    from deadline_control.models import EmailSettings

    department = get_object_or_404(Department, pk=department_id)
    subdivision = department.subdivision
    organization = department.organization

    if not AccessControlHelper.can_access_object(request.user, organization):
        return JsonResponse({'success': False, 'error': 'Нет доступа'}, status=403)

    if subdivision and subdivision.skip_email_notifications:
        return JsonResponse({
            'success': False,
            'status': 'skipped',
            'message': 'Для подразделения включён пропуск email-уведомлений',
        })

    issue_date_raw = _request_value(request, 'issue_date', '')
    _, issue_date_display = _parse_issue_date(issue_date_raw)
    test_mode = _request_bool(request, 'test_mode', False)

    email_settings = EmailSettings.get_settings(organization)
    if not email_settings.is_active:
        return JsonResponse({'success': False, 'error': 'Email уведомления отключены'}, status=400)
    if not email_settings.email_host:
        return JsonResponse({'success': False, 'error': 'SMTP сервер не настроен'}, status=400)

    test_email = getattr(email_settings, 'test_recipient_email', '') or ''
    employees = Employee.objects.filter(
        position__department=department,
        position__isnull=False,
        status='active',
        position__requires_siz=True,
    ).select_related('position', 'position__department').distinct()

    recipients_info = get_recipients_for_department(
        department=department,
        subdivision=subdivision,
        organization=organization,
        notification_type='siz_cards'
    )

    with BulkEmailSender(
        email_settings=email_settings,
        delay_seconds=float(email_settings.email_delay_seconds),
        max_retries=email_settings.max_retry_attempts,
        connection_timeout=email_settings.connection_timeout,
    ) as bulk_sender:
        result = _send_cards_group(
            bulk_sender=bulk_sender,
            email_settings=email_settings,
            organization=organization,
            subdivision_name=subdivision.name if subdivision else '',
            department_name=department.name,
            employees=employees,
            recipients=recipients_info['recipients'],
            issue_date_display=issue_date_display,
            user=request.user,
            test_mode=test_mode,
            test_email=test_email,
        )

    success = result['status'] == 'success'
    return JsonResponse({
        'success': success,
        'status': result['status'],
        'department_id': department.id,
        'department_name': department.name,
        'cards_count': result.get('cards_count', 0),
        'recipients': result.get('recipients', []),
        'message': result.get('message', ''),
        'errors': result.get('errors', []),
        'fallback_used': recipients_info.get('fallback_used', False),
    })


@login_required
def send_siz_cards_single(request, subdivision_id):
    """Отправка карточек СИЗ для одного подразделения (и его отделов)."""
    from directory.utils.bulk_email_sender import BulkEmailSender
    from deadline_control.models import EmailSettings

    subdivision = get_object_or_404(StructuralSubdivision, pk=subdivision_id)
    organization = subdivision.organization

    if not AccessControlHelper.can_access_object(request.user, subdivision):
        return JsonResponse({'success': False, 'error': 'Нет доступа'}, status=403)

    issue_date_raw = _request_value(request, 'issue_date', '')
    _, issue_date_display = _parse_issue_date(issue_date_raw)
    test_mode = _request_bool(request, 'test_mode', False)
    summary_mode = _request_bool(request, 'summary_mode', False)

    email_settings = EmailSettings.get_settings(organization)
    if not email_settings.is_active:
        return JsonResponse({'success': False, 'error': 'Email уведомления отключены'}, status=400)
    if not email_settings.email_host:
        return JsonResponse({'success': False, 'error': 'SMTP сервер не настроен'}, status=400)

    test_email = getattr(email_settings, 'test_recipient_email', '') or ''

    with BulkEmailSender(
        email_settings=email_settings,
        delay_seconds=float(email_settings.email_delay_seconds),
        max_retries=email_settings.max_retry_attempts,
        connection_timeout=email_settings.connection_timeout,
    ) as bulk_sender:
        result = _send_for_subdivision(
            request=request,
            subdivision=subdivision,
            email_settings=email_settings,
            bulk_sender=bulk_sender,
            issue_date_display=issue_date_display,
            test_mode=test_mode,
            test_email=test_email,
            summary_mode=summary_mode,
        )

    success = result['status'] in {'completed', 'partial'}
    return JsonResponse({
        'success': success,
        'status': result['status'],
        'subdivision_id': subdivision.id,
        'subdivision_name': subdivision.name,
        'summary_mode': summary_mode,
        'test_mode': test_mode,
        'successful_count': result['successful'],
        'failed_count': result['failed'],
        'skipped_count': result['skipped'],
        'total_cards': result['total_cards'],
        'details': result['details'],
    })


@login_required
def send_siz_cards_for_organization(request, organization_id):
    """Массовая отправка карточек СИЗ для всех подразделений организации."""
    from directory.utils.bulk_email_sender import BulkEmailSender
    from deadline_control.models import EmailSettings, SIZCardSendLog

    organization = get_object_or_404(Organization, pk=organization_id)
    if not AccessControlHelper.can_access_object(request.user, organization):
        return JsonResponse({'success': False, 'error': 'Нет доступа'}, status=403)

    issue_date_raw = _request_value(request, 'issue_date', '')
    issue_date_obj, issue_date_display = _parse_issue_date(issue_date_raw)
    test_mode = _request_bool(request, 'test_mode', False)
    summary_mode = _request_bool(request, 'summary_mode', False)

    email_settings = EmailSettings.get_settings(organization)
    if not email_settings.is_active:
        return JsonResponse({'success': False, 'error': 'Email уведомления отключены'}, status=400)
    if not email_settings.email_host:
        return JsonResponse({'success': False, 'error': 'SMTP сервер не настроен'}, status=400)

    subdivisions = StructuralSubdivision.objects.filter(organization=organization).order_by('name')
    if not subdivisions.exists():
        return JsonResponse({
            'success': False,
            'status': 'skipped',
            'message': 'У организации нет подразделений',
        })

    send_log = SIZCardSendLog.objects.create(
        organization=organization,
        initiated_by=request.user,
        issue_date=issue_date_obj,
        total_subdivisions=subdivisions.count(),
        successful_count=0,
        failed_count=0,
        skipped_count=0,
        total_cards=0,
        test_mode=test_mode,
        status='in_progress',
    )

    test_email = getattr(email_settings, 'test_recipient_email', '') or ''
    details = []

    with BulkEmailSender(
        email_settings=email_settings,
        delay_seconds=float(email_settings.email_delay_seconds),
        max_retries=email_settings.max_retry_attempts,
        connection_timeout=email_settings.connection_timeout,
    ) as bulk_sender:
        for subdivision in subdivisions:
            sub_result = _send_for_subdivision(
                request=request,
                subdivision=subdivision,
                email_settings=email_settings,
                bulk_sender=bulk_sender,
                issue_date_display=issue_date_display,
                test_mode=test_mode,
                test_email=test_email,
                summary_mode=summary_mode,
            )

            send_log.total_cards += sub_result['total_cards']
            details.append({
                'subdivision_id': subdivision.id,
                'subdivision_name': subdivision.name,
                **sub_result,
            })

            if sub_result['status'] == 'completed':
                send_log.successful_count += 1
            elif sub_result['status'] == 'partial':
                send_log.successful_count += 1
            elif sub_result['status'] == 'failed':
                send_log.failed_count += 1
            else:
                send_log.skipped_count += 1

    if send_log.successful_count > 0 and send_log.failed_count == 0 and send_log.skipped_count == 0:
        send_log.status = 'completed'
    elif send_log.successful_count > 0:
        send_log.status = 'partial'
    else:
        send_log.status = 'failed'
    send_log.save()

    return JsonResponse({
        'success': send_log.successful_count > 0,
        'status': send_log.status,
        'log_id': send_log.id,
        'organization_id': organization.id,
        'organization_name': organization.short_name_ru or organization.full_name_ru,
        'total_subdivisions': send_log.total_subdivisions,
        'successful_count': send_log.successful_count,
        'failed_count': send_log.failed_count,
        'skipped_count': send_log.skipped_count,
        'total_cards': send_log.total_cards,
        'test_mode': test_mode,
        'summary_mode': summary_mode,
        'details': details,
    })
