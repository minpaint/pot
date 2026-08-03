# directory/views/hiring.py

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.utils.translation import gettext_lazy as _
from django.views.generic import ListView, DetailView, CreateView, UpdateView, DeleteView, FormView, View
from django.views.generic.detail import SingleObjectMixin
from django.contrib.auth.mixins import LoginRequiredMixin
from django.urls import reverse_lazy, reverse
from django.db import transaction
from django.utils import timezone
from django.http import JsonResponse, HttpResponseRedirect, HttpResponse
from django.db.models import Q, Prefetch
from django import forms
from crispy_forms.helper import FormHelper
from django.core.mail import EmailMultiAlternatives
from django.utils.html import strip_tags
from django.utils.safestring import mark_safe

from directory.models import (
    Employee,
    EmployeeHiring,
    Organization,
    Position,
    GeneratedDocument,
    DocumentEmailSendLog
)
from deadline_control.models.medical_norm import MedicalExaminationNorm
from deadline_control.models import EmailSettings
from directory.forms.hiring import CombinedEmployeeHiringForm, DocumentAttachmentForm
from directory.forms.document_forms import DocumentSelectionForm
from directory.utils.hiring_utils import create_hiring_from_employee, attach_document_to_hiring
from directory.utils.declension import decline_full_name, get_initials_from_name
from directory.forms.mixins import OrganizationRestrictionFormMixin
from directory.mixins import AccessControlMixin, AccessControlObjectMixin
from directory.utils.permissions import AccessControlHelper
from directory.views.documents.selection import get_auto_selected_document_types
from directory.utils.email_recipients import collect_recipients_for_subdivision

import logging
import io
import zipfile
from urllib.parse import quote

logger = logging.getLogger(__name__)


class SimpleHiringView(LoginRequiredMixin, FormView):
    """
    🧙‍♂️ Упрощенная форма приема на работу вместо многошагового мастера.
    Все поля представлены на одной странице с динамическим отображением
    дополнительных полей для медосмотра и СИЗ.
    """
    template_name = 'directory/hiring/simple_form.html'
    form_class = CombinedEmployeeHiringForm
    success_url = reverse_lazy('directory:hiring:hiring_list')

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['user'] = self.request.user
        org_id = self.request.session.get('selected_org_id')
        if org_id:
            try:
                kwargs['initial_org_id'] = int(org_id)
            except (ValueError, TypeError):
                pass
        return kwargs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['title'] = _('Прием на работу: Новый сотрудник')

        # Используем AccessControlHelper для получения доступных организаций
        context['organizations'] = AccessControlHelper.get_accessible_organizations(
            self.request.user, self.request
        )

        return context

    @transaction.atomic
    def form_valid(self, form):
        """
        Обработка валидной формы с сохранением сотрудника и записи о приеме.
        """
        try:
            # Получаем данные формы
            data = form.cleaned_data

            # Определяем contract_type на основе hiring_type
            hiring_type = data['hiring_type']
            if hiring_type == 'new':
                contract_type = 'standard'
            elif hiring_type in ('contractor', 'part_time', 'transfer', 'return'):
                contract_type = hiring_type
            else:
                contract_type = 'standard'

            # Получаем дату начала работы из формы
            hire_date = data.get('hire_date') or timezone.now().date()

            # Создаем сотрудника
            employee = Employee(
                full_name_nominative=data['full_name_nominative'],
                date_of_birth=data.get('date_of_birth'),
                organization=data['organization'],
                subdivision=data.get('subdivision'),
                department=data.get('department'),
                position=data['position'],
                height=data.get('height'),
                clothing_size=data.get('clothing_size'),
                shoe_size=data.get('shoe_size'),
                hire_date=hire_date,
                start_date=hire_date,
                contract_type=contract_type,
                status='active'
            )
            employee.save()

            # Если указана дата первичного медосмотра, применяем ее ко всем медосмотрам сотрудника
            initial_medical_date = data.get('initial_medical_examination_date')
            if initial_medical_date:
                # Импортируем модель медосмотров
                from deadline_control.models import EmployeeMedicalExamination

                # Получаем все медосмотры сотрудника (созданные через Signal)
                medical_examinations = EmployeeMedicalExamination.objects.filter(employee=employee)

                # Применяем дату ко всем медосмотрам
                for exam in medical_examinations:
                    exam.perform_examination(initial_medical_date)

            # Создаем запись о приеме
            hiring = EmployeeHiring(
                employee=employee,
                hiring_date=hire_date,
                start_date=hire_date,
                hiring_type=data['hiring_type'],
                organization=data['organization'],
                subdivision=data.get('subdivision'),
                department=data.get('department'),
                position=data['position'],
                created_by=self.request.user
            )
            hiring.save()

            # Добавляем сообщение об успехе
            messages.success(
                self.request,
                _('Сотрудник {} успешно принят на работу').format(employee.full_name_nominative)
            )

            # Изменяем URL редиректа на детали записи о приеме
            self.success_url = reverse('directory:hiring:hiring_detail', kwargs={'pk': hiring.pk})

            return super().form_valid(form)

        except Exception as e:
            # Логируем ошибку и добавляем сообщение
            logger.error(f"Ошибка при создании сотрудника: {str(e)}")

            messages.error(
                self.request,
                _('Произошла ошибка при создании сотрудника: {}').format(str(e))
            )

            return self.form_invalid(form)


@login_required
def position_requirements_api(request, position_id):
    """
    🔍 API для получения информации о требованиях должности.

    Проверяет, требуется ли медосмотр и СИЗ для выбранной должности.
    Используется в форме приема на работу для определения необходимых полей.

    Args:
        request: HttpRequest
        position_id: ID должности

    Returns:
        JsonResponse с данными о требованиях должности
    """
    try:
        # Получаем должность или 404
        position = get_object_or_404(Position, pk=position_id)

        # Проверяем переопределения для медосмотра
        has_custom_medical = position.medical_factors.filter(is_disabled=False).exists()

        # Проверяем эталонные нормы, если нет переопределений
        has_reference_medical = False
        if not has_custom_medical:
            has_reference_medical = MedicalExaminationNorm.objects.filter(
                position_name=position.position_name
            ).exists()

        # Проверяем переопределения для СИЗ
        has_custom_siz = position.siz_norms.exists()

        # Проверяем эталонные нормы СИЗ, если нет переопределений
        has_reference_siz = False
        if not has_custom_siz:
            has_reference_siz = Position.find_reference_norms(position.position_name).exists()

        # Логируем информацию для отладки
        logger.info(
            f"Position '{position.position_name}' (ID={position.id}): "
            f"has_custom_medical={has_custom_medical}, "
            f"has_reference_medical={has_reference_medical}, "
            f"has_custom_siz={has_custom_siz}, "
            f"has_reference_siz={has_reference_siz}"
        )

        # Формируем ответ
        response_data = {
            'position_id': position.id,
            'position_name': position.position_name,
            'needs_medical': has_custom_medical or has_reference_medical,
            'needs_siz': has_custom_siz or has_reference_siz,
            'status': 'success',
            # Отладочная информация
            'debug': {
                'has_custom_medical': has_custom_medical,
                'has_reference_medical': has_reference_medical,
                'has_custom_siz': has_custom_siz,
                'has_reference_siz': has_reference_siz,
            }
        }

        return JsonResponse(response_data)

    except Exception as e:
        # Логируем ошибку
        logger.error(f"Ошибка в position_requirements_api для должности ID={position_id}: {str(e)}")

        return JsonResponse({
            'status': 'error',
            'message': str(e)
        }, status=500)


# Оставляем существующие классы представлений
class HiringTreeView(LoginRequiredMixin, AccessControlMixin, ListView):
    """
    Древовидное представление записей о приеме на работу
    по организационной структуре
    """
    model = EmployeeHiring
    template_name = 'directory/hiring/tree_view.html'
    context_object_name = 'hiring_records'

    def get_queryset(self):
        # AccessControlMixin автоматически фильтрует по правам доступа
        queryset = super().get_queryset()

        # Фильтр по выбранной организации из глобального селектора
        selected_org_id = self.request.session.get('selected_org_id')
        if selected_org_id:
            queryset = queryset.filter(organization_id=selected_org_id)

        # Фильтрация по активности
        is_active = self.request.GET.get('is_active')
        if is_active == 'true':
            queryset = queryset.filter(is_active=True)
        elif is_active == 'false':
            queryset = queryset.filter(is_active=False)

        # Фильтрация по типу приема
        hiring_type = self.request.GET.get('hiring_type')
        if hiring_type:
            queryset = queryset.filter(hiring_type=hiring_type)

        # Поиск по ФИО
        search = self.request.GET.get('search')
        if search:
            queryset = queryset.filter(
                Q(employee__full_name_nominative__icontains=search) |
                Q(position__position_name__icontains=search)
            )

        return queryset.select_related(
            'employee', 'organization', 'subdivision', 'department', 'position'
        ).prefetch_related('documents')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['title'] = _('Приемы на работу')

        allowed_orgs = AccessControlHelper.get_accessible_organizations(
            self.request.user, self.request
        )

        # Один запрос — группируем в памяти (убираем N+1)
        all_hirings = list(self.get_queryset())

        # Индексируем по (org_id, sub_id, dept_id)
        from collections import defaultdict
        by_key = defaultdict(list)
        for h in all_hirings:
            by_key[(h.organization_id, h.subdivision_id, h.department_id)].append(h)

        tree_data = []
        for org in allowed_orgs:
            org_hirings = by_key[(org.id, None, None)]
            subdivisions_data = []

            for subdivision in org.subdivisions.prefetch_related('departments').all():
                sub_hirings = by_key[(org.id, subdivision.id, None)]
                departments_data = []

                for department in subdivision.departments.all():
                    dept_hirings = by_key[(org.id, subdivision.id, department.id)]
                    if dept_hirings:
                        departments_data.append({
                            'id': department.id,
                            'name': department.name,
                            'hirings': dept_hirings,
                        })

                if sub_hirings or departments_data:
                    sub_total = len(sub_hirings) + sum(len(d['hirings']) for d in departments_data)
                    subdivisions_data.append({
                        'id': subdivision.id,
                        'name': subdivision.name,
                        'hirings': sub_hirings,
                        'departments': departments_data,
                        'total': sub_total,
                    })

            if org_hirings or subdivisions_data:
                org_total = len(org_hirings) + sum(s['total'] for s in subdivisions_data)
                tree_data.append({
                    'id': org.id,
                    'name': org.short_name_ru or org.full_name_ru,
                    'hirings': org_hirings,
                    'subdivisions': subdivisions_data,
                    'total': org_total,
                })

        context['tree_data'] = tree_data
        context['hiring_types'] = dict(EmployeeHiring.HIRING_TYPE_CHOICES)
        context['current_hiring_type'] = self.request.GET.get('hiring_type', '')
        context['current_is_active'] = self.request.GET.get('is_active', '')
        context['search_query'] = self.request.GET.get('search', '')

        return context


class HiringListView(LoginRequiredMixin, AccessControlMixin, ListView):
    """
    Представление для отображения списка записей о приеме на работу
    """
    model = EmployeeHiring
    template_name = 'directory/hiring/list.html'
    context_object_name = 'hiring_records'
    paginate_by = 20

    def get_queryset(self):
        from datetime import date, timedelta
        import calendar as cal

        queryset = super().get_queryset()

        selected_org_id = self.request.session.get('selected_org_id')
        if selected_org_id:
            queryset = queryset.filter(organization_id=selected_org_id)

        # Фильтр по поиску
        search = self.request.GET.get('search')
        if search:
            queryset = queryset.filter(
                Q(employee__full_name_nominative__icontains=search) |
                Q(position__position_name__icontains=search)
            )

        # Быстрые периоды
        today = date.today()
        period = self.request.GET.get('period', '')
        date_from_str = self.request.GET.get('date_from', '')
        date_to_str = self.request.GET.get('date_to', '')

        if period == 'today':
            queryset = queryset.filter(hiring_date=today)
        elif period == 'week':
            week_start = today - timedelta(days=today.weekday())
            queryset = queryset.filter(hiring_date__gte=week_start, hiring_date__lte=today)
        elif period == 'month':
            queryset = queryset.filter(hiring_date__year=today.year, hiring_date__month=today.month)
        elif period == 'last_month':
            first_day = (today.replace(day=1) - timedelta(days=1)).replace(day=1)
            last_day = today.replace(day=1) - timedelta(days=1)
            queryset = queryset.filter(hiring_date__gte=first_day, hiring_date__lte=last_day)
        elif period == 'year':
            queryset = queryset.filter(hiring_date__year=today.year)
        else:
            # Произвольный диапазон
            if date_from_str:
                try:
                    from datetime import datetime
                    queryset = queryset.filter(hiring_date__gte=datetime.strptime(date_from_str, '%Y-%m-%d').date())
                except ValueError:
                    pass
            if date_to_str:
                try:
                    from datetime import datetime
                    queryset = queryset.filter(hiring_date__lte=datetime.strptime(date_to_str, '%Y-%m-%d').date())
                except ValueError:
                    pass

        return queryset.select_related(
            'employee', 'organization', 'subdivision', 'department', 'position'
        ).prefetch_related('documents')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['title'] = _('Приемы на работу')
        context['search_query'] = self.request.GET.get('search', '')
        context['current_period'] = self.request.GET.get('period', '')
        context['date_from'] = self.request.GET.get('date_from', '')
        context['date_to'] = self.request.GET.get('date_to', '')
        return context


class HiringDetailView(LoginRequiredMixin, AccessControlObjectMixin, DetailView):
    """
    Представление для просмотра детальной информации о приеме на работу
    """
    model = EmployeeHiring
    template_name = 'directory/hiring/detail.html'
    context_object_name = 'hiring'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['title'] = _(f'Прием на работу: {self.object.employee.full_name_nominative}')

        # Добавляем форму для прикрепления документов
        context['attachment_form'] = DocumentAttachmentForm(
            employee_id=self.object.employee.id,
            initial={'documents': self.object.documents.all()}
        )

        # Добавляем форму для генерации документов
        employee = self.object.employee
        auto_selected = get_auto_selected_document_types(employee)

        context['document_selection_form'] = DocumentSelectionForm(
            initial={
                'employee_id': employee.id,
                'document_types': auto_selected
            }
        )
        context['employee'] = employee

        # Руководитель стажировки: авто-подбор + список кандидатов
        from directory.views.documents.utils import get_internship_leader
        internship_leader, il_level, il_success = get_internship_leader(employee)
        context['internship_leader'] = internship_leader
        context['internship_leader_level'] = il_level
        context['internship_leader_success'] = il_success

        il_level_display = {
            'department': 'В отделе',
            'subdivision': 'В подразделении',
            'organization': 'В организации',
        }.get(il_level, '')
        context['internship_leader_level_display'] = il_level_display

        # Все кандидаты в руководители стажировки в организации
        internship_leader_candidates = Employee.objects.active_for_operations().filter(
            organization=employee.organization,
            position__can_be_internship_leader=True,
        ).exclude(id=employee.id).select_related(
            'position', 'subdivision', 'department'
        ).order_by('full_name_nominative')
        context['internship_leader_candidates'] = internship_leader_candidates

        return context

    def post(self, request, *args, **kwargs):
        self.object = self.get_object()

        # Обработка формы прикрепления документов
        if 'attach_documents' in request.POST:
            form = DocumentAttachmentForm(
                request.POST,
                employee_id=self.object.employee.id
            )

            if form.is_valid():
                # Очищаем существующие документы и добавляем выбранные
                self.object.documents.clear()
                selected_docs = form.cleaned_data['documents']
                self.object.documents.add(*selected_docs)
                messages.success(request, _(f'Прикреплено документов: {len(selected_docs)}'))
                return redirect('directory:hiring:hiring_detail', pk=self.object.pk)

        # ВАЖНО: Проверка отправки email ПЕРЕД генерацией,
        # т.к. при form.submit() могут передаться оба параметра
        if 'send_documents' in request.POST:
            return self._handle_send_documents(request)

        # Обработка формы генерации документов
        if 'generate_documents' in request.POST:
            return self._handle_document_generation(request)

        return self.get(request, *args, **kwargs)

    def _handle_document_generation(self, request):
        """Обработка генерации документов"""
        form = DocumentSelectionForm(request.POST)

        if not form.is_valid():
            messages.error(request, "Ошибка в форме выбора документов")
            return redirect('directory:hiring:hiring_detail', pk=self.object.pk)

        document_types = form.cleaned_data.get('document_types', [])

        if not document_types:
            messages.error(request, "Не выбран ни один тип документа")
            return redirect('directory:hiring:hiring_detail', pk=self.object.pk)

        employee = self.object.employee

        # Явно выбранный руководитель стажировки (из дропдауна на странице)
        internship_leader_override = None
        internship_leader_id = request.POST.get('internship_leader_id')
        if internship_leader_id:
            try:
                internship_leader_override = Employee.objects.select_related(
                    'position', 'subdivision', 'department'
                ).get(id=int(internship_leader_id))
            except (Employee.DoesNotExist, ValueError):
                pass

        # Импортируем генераторы
        from directory.document_generators.order_generator import generate_all_orders
        from directory.document_generators.protocol_generator import generate_knowledge_protocol
        from directory.document_generators.familiarization_generator import generate_familiarization_document
        from directory.document_generators.ot_card_generator import generate_personal_ot_card
        from directory.document_generators.journal_example_generator import generate_journal_example
        from directory.document_generators.siz_card_docx_generator import generate_siz_card_docx
        from directory.document_generators.vvodny_journal_generator import generate_vvodny_journal

        generator_map = {
            'all_orders': generate_all_orders,
            'knowledge_protocol': generate_knowledge_protocol,
            'doc_familiarization': generate_familiarization_document,
            'personal_ot_card': generate_personal_ot_card,
            'journal_example': generate_journal_example,
            'siz_card': generate_siz_card_docx,
            'vvodny_journal_template': generate_vvodny_journal,
        }

        # Генерируем документы
        files_to_archive = []

        for doc_type in document_types:
            try:
                generator_func = generator_map.get(doc_type)
                if generator_func:
                    if doc_type == 'doc_familiarization':
                        result = generator_func(employee=employee, user=request.user, document_list=None)
                    elif doc_type == 'all_orders':
                        result = generator_func(
                            employee=employee, user=request.user,
                            internship_leader_override=internship_leader_override
                        )
                    else:
                        result = generator_func(employee=employee, user=request.user)

                    # Обрабатываем как список (для generate_all_orders) так и одиночный документ
                    if result:
                        # Если результат - список (например, от generate_all_orders)
                        if isinstance(result, list):
                            for doc in result:
                                if isinstance(doc, dict) and 'content' in doc and 'filename' in doc:
                                    files_to_archive.append((doc['content'], doc['filename']))
                                    logger.info(f"Сгенерирован документ: {doc['filename']}")
                        # Если результат - одиночный словарь
                        elif isinstance(result, dict) and 'content' in result and 'filename' in result:
                            files_to_archive.append((result['content'], result['filename']))
                            logger.info(f"Сгенерирован документ: {result['filename']}")
            except Exception as e:
                logger.error(f"Ошибка при генерации {doc_type}: {str(e)}", exc_info=True)
                messages.warning(request, f"Ошибка при генерации документа типа {doc_type}: {str(e)}")
                continue

        if not files_to_archive:
            messages.error(request, "Не удалось сгенерировать ни один документ")
            return redirect('directory:hiring:hiring_detail', pk=self.object.pk)

        # Создаем архив
        try:
            zip_buffer = io.BytesIO()
            with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zipf:
                for content, filename in files_to_archive:
                    zipf.writestr(filename, content)

            zip_buffer.seek(0)

            employee_initials = get_initials_from_name(employee.full_name_nominative)
            zip_filename = f"Документы_{employee_initials}.zip"

            response = HttpResponse(zip_buffer.getvalue(), content_type='application/zip')
            encoded_filename = quote(zip_filename)
            response['Content-Disposition'] = f"attachment; filename*=UTF-8''{encoded_filename}"

            messages.success(request, f"Успешно сгенерировано документов: {len(files_to_archive)}")
            return response

        except Exception as e:
            logger.error(f"Ошибка при создании архива: {str(e)}", exc_info=True)
            messages.error(request, f"Ошибка при создании архива: {str(e)}")
            return redirect('directory:hiring:hiring_detail', pk=self.object.pk)

    def _handle_send_documents(self, request):
        """Обработка отправки выбранных документов по email"""
        # ШАГ 1: Получить выбранные типы документов
        document_types = request.POST.getlist('document_types')

        if not document_types:
            messages.error(request, "Не выбран ни один тип документа для отправки")
            return redirect('directory:hiring:hiring_detail', pk=self.object.pk)

        employee = self.object.employee
        organization = self.object.organization
        subdivision = self.object.subdivision

        logger.info(
            f"Начало отправки документов приема для сотрудника '{employee.full_name_nominative}' "
            f"(hiring_id={self.object.pk}). Выбрано типов: {len(document_types)}"
        )

        # Явно выбранный руководитель стажировки (из дропдауна на странице)
        internship_leader_override = None
        internship_leader_id = request.POST.get('internship_leader_id')
        if internship_leader_id:
            try:
                internship_leader_override = Employee.objects.select_related(
                    'position', 'subdivision', 'department'
                ).get(id=int(internship_leader_id))
            except (Employee.DoesNotExist, ValueError):
                pass

        # ШАГ 2: Получить настройки email
        try:
            email_settings = EmailSettings.get_settings(organization)
        except Exception as e:
            messages.error(request, f"Не удалось получить настройки email: {str(e)}")
            return redirect('directory:hiring:hiring_detail', pk=self.object.pk)

        # ШАГ 2.1: Проверить, активны ли настройки
        if not email_settings.is_active:
            messages.error(
                request,
                f"Email уведомления отключены для {organization.short_name_ru}. "
                f"Настройте email в админке: Email Settings."
            )
            return redirect('directory:hiring:hiring_detail', pk=self.object.pk)

        # ШАГ 2.2: Проверить, настроен ли SMTP
        if not email_settings.email_host:
            messages.error(
                request,
                f"SMTP сервер не настроен для {organization.short_name_ru}. "
                f"Укажите настройки в админке: Email Settings."
            )
            return redirect('directory:hiring:hiring_detail', pk=self.object.pk)

        # ШАГ 3: Сгенерировать выбранные документы
        from directory.document_generators.order_generator import generate_all_orders
        from directory.document_generators.protocol_generator import generate_knowledge_protocol
        from directory.document_generators.familiarization_generator import generate_familiarization_document
        from directory.document_generators.ot_card_generator import generate_personal_ot_card
        from directory.document_generators.journal_example_generator import generate_journal_example
        from directory.document_generators.siz_card_docx_generator import generate_siz_card_docx
        from directory.document_generators.vvodny_journal_generator import generate_vvodny_journal

        generator_map = {
            'all_orders': generate_all_orders,
            'knowledge_protocol': generate_knowledge_protocol,
            'doc_familiarization': generate_familiarization_document,
            'personal_ot_card': generate_personal_ot_card,
            'journal_example': generate_journal_example,
            'siz_card': generate_siz_card_docx,
            'vvodny_journal_template': generate_vvodny_journal,
        }

        # Генерируем только выбранные типы документов
        generated_files = []

        for doc_type in document_types:
            try:
                generator_func = generator_map.get(doc_type)
                if generator_func:
                    if doc_type == 'doc_familiarization':
                        result = generator_func(employee=employee, user=request.user, document_list=None)
                    elif doc_type == 'all_orders':
                        result = generator_func(
                            employee=employee, user=request.user,
                            internship_leader_override=internship_leader_override
                        )
                    else:
                        result = generator_func(employee=employee, user=request.user)

                    # Обрабатываем как список (для generate_all_orders) так и одиночный документ
                    if result:
                        if isinstance(result, list):
                            for doc in result:
                                if isinstance(doc, dict) and 'content' in doc and 'filename' in doc:
                                    generated_files.append((doc['content'], doc['filename']))
                                    logger.info(f"Сгенерирован документ: {doc['filename']}")
                        elif isinstance(result, dict) and 'content' in result and 'filename' in result:
                            generated_files.append((result['content'], result['filename']))
                            logger.info(f"Сгенерирован документ: {result['filename']}")
            except Exception as e:
                logger.error(f"Ошибка при генерации {doc_type}: {str(e)}", exc_info=True)
                messages.warning(request, f"Ошибка при генерации документа типа {doc_type}: {str(e)}")
                continue

        if not generated_files:
            messages.error(
                request,
                "Не удалось сгенерировать ни одного документа. "
                "Проверьте настройки шаблонов документов."
            )
            return redirect('directory:hiring:hiring_detail', pk=self.object.pk)

        logger.info(f"Сгенерировано {len(generated_files)} документов")

        # ШАГ 4: Собрать получателей
        if subdivision:
            recipients = collect_recipients_for_subdivision(
                subdivision=subdivision,
                organization=organization,
                notification_type='general'
            )
        else:
            recipients = email_settings.get_recipient_list()

        if not recipients:
            messages.error(
                request,
                mark_safe(
                    "Нет получателей для отправки. Настройте email получателей:<br>"
                    "1. Email подразделения (SubdivisionEmail)<br>"
                    "2. Email ответственных за ОТ (в карточке сотрудника)<br>"
                    "3. Общие получатели в Email Settings"
                )
            )
            return redirect('directory:hiring:hiring_detail', pk=self.object.pk)

        logger.info(f"Собрано {len(recipients)} получателей: {', '.join(recipients)}")

        # ШАГ 5: Получить шаблон письма
        template_data = email_settings.get_email_template('documents_priem')

        if not template_data:
            messages.error(
                request,
                "Шаблон письма 'documents_priem' не настроен для этой организации. "
                "Создайте шаблон в админке: Email Templates."
            )
            return redirect('directory:hiring:hiring_detail', pk=self.object.pk)

        subject_template, body_template = template_data

        # ШАГ 6: Подготовить переменные для шаблона
        template_vars = {
            'organization_name': organization.short_name_ru or organization.full_name_ru,
            'employee_name': employee.full_name_nominative,
            'position_name': self.object.position.position_name,
            'subdivision_name': subdivision.name if subdivision else "Без подразделения",
            'department_name': self.object.department.name if self.object.department else "Без отдела",
            'hiring_date': self.object.hiring_date.strftime('%d.%m.%Y'),
            'start_date': self.object.start_date.strftime('%d.%m.%Y'),
            'hiring_type': self.object.get_hiring_type_display(),
            'document_count': len(generated_files),
            'date': timezone.now().strftime('%d.%m.%Y'),
        }

        # ШАГ 7: Форматировать тему и тело письма
        try:
            subject = subject_template.format(**template_vars)
            html_message = body_template.format(**template_vars)
        except KeyError as e:
            messages.error(
                request,
                mark_safe(
                    f"Ошибка в шаблоне письма: переменная {e} не найдена.<br>"
                    f"Доступные переменные: {', '.join(template_vars.keys())}"
                )
            )
            return redirect('directory:hiring:hiring_detail', pk=self.object.pk)

        # ШАГ 8: Создать email с вложениями
        try:
            connection = email_settings.get_connection()
            from_email = email_settings.default_from_email or email_settings.email_host_user

            text_message = strip_tags(html_message)

            email = EmailMultiAlternatives(
                subject=subject,
                body=text_message,
                from_email=from_email,
                to=recipients,
                connection=connection
            )

            email.attach_alternative(html_message, "text/html")

            # ШАГ 9: Прикрепить сгенерированные документы
            for file_content, filename in generated_files:
                try:
                    email.attach(
                        filename,
                        file_content,
                        'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
                    )
                    logger.info(f"Прикреплен документ: {filename}")
                except Exception as e:
                    logger.error(f"Ошибка прикрепления документа {filename}: {str(e)}", exc_info=True)
                    continue

            # ШАГ 10: Отправить email
            email.send(fail_silently=False)

            logger.info(
                f"Документы приема отправлены для '{employee.full_name_nominative}'. "
                f"Получатели: {', '.join(recipients)}. Документов: {len(generated_files)}"
            )

            # Логируем успешную отправку в БД
            try:
                DocumentEmailSendLog.objects.create(
                    employee=employee,
                    hiring=self.object,
                    document_types=document_types,
                    recipients=recipients,
                    recipients_count=len(recipients),
                    documents_count=len(generated_files),
                    status='success',
                    email_subject=subject,
                    sent_by=request.user if request.user.is_authenticated else None
                )
            except Exception as log_error:
                logger.warning(f"Не удалось записать лог отправки: {str(log_error)}")

            messages.success(
                request,
                mark_safe(
                    f"✅ Документы приема успешно отправлены на {len(recipients)} адрес(ов):<br>"
                    f"<strong>{', '.join(recipients)}</strong><br>"
                    f"Отправлено документов: {len(generated_files)}"
                )
            )

        except Exception as e:
            logger.error(
                f"Ошибка отправки email для hiring_id={self.object.pk}: {str(e)}",
                exc_info=True
            )

            # Логируем неуспешную отправку в БД
            try:
                DocumentEmailSendLog.objects.create(
                    employee=employee,
                    hiring=self.object,
                    document_types=document_types,
                    recipients=recipients if 'recipients' in locals() else [],
                    recipients_count=len(recipients) if 'recipients' in locals() else 0,
                    documents_count=len(generated_files),
                    status='failed',
                    error_message=str(e),
                    email_subject=subject if 'subject' in locals() else '',
                    sent_by=request.user if request.user.is_authenticated else None
                )
            except Exception as log_error:
                logger.warning(f"Не удалось записать лог ошибки отправки: {str(log_error)}")

            messages.error(
                request,
                mark_safe(
                    f"❌ Ошибка при отправке email:<br>"
                    f"<code>{str(e)}</code><br>"
                    f"Проверьте настройки SMTP в Email Settings."
                )
            )

        return redirect('directory:hiring:hiring_detail', pk=self.object.pk)


class HiringCreateView(LoginRequiredMixin, CreateView):
    """
    Представление для создания новой записи о приеме на работу
    """
    model = EmployeeHiring
    # form_class = EmployeeHiringRecordForm  # Закомментируем эту строку, так как у нас нет этой формы
    fields = [
        'employee', 'hiring_date', 'start_date', 'hiring_type',
        'organization', 'subdivision', 'department', 'position',
        'notes', 'is_active'
    ]  # Вместо form_class используем fields
    template_name = 'directory/hiring/form.html'

    def get_form(self, form_class=None):
        form = super().get_form(form_class)
        # Добавляем атрибуты формы, которые были бы в EmployeeHiringRecordForm
        form.helper = FormHelper()
        form.helper.form_method = 'post'

        # Настраиваем виджеты для полей формы
        form.fields['hiring_date'].widget = forms.DateInput(attrs={'type': 'date', 'class': 'form-control'})
        form.fields['start_date'].widget = forms.DateInput(attrs={'type': 'date', 'class': 'form-control'})

        # Ограничиваем организации: по выбранной в шапке, иначе все доступные
        accessible = AccessControlHelper.get_accessible_organizations(self.request.user, self.request)
        org_id = self.request.session.get('selected_org_id')
        if org_id:
            try:
                restricted = accessible.filter(pk=int(org_id))
                form.fields['organization'].queryset = restricted if restricted.exists() else accessible
            except (ValueError, TypeError):
                form.fields['organization'].queryset = accessible
        else:
            form.fields['organization'].queryset = accessible

        return form

    def get_initial(self):
        initial = super().get_initial()
        org_id = self.request.session.get('selected_org_id')
        if org_id:
            try:
                initial['organization'] = int(org_id)
            except (ValueError, TypeError):
                pass
        return initial

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['title'] = _('Новый прием на работу')
        return context

    def form_valid(self, form):
        form.instance.created_by = self.request.user
        messages.success(self.request, _('Запись о приеме на работу успешно создана'))
        return super().form_valid(form)

    def get_success_url(self):
        return reverse_lazy('directory:hiring:hiring_detail', kwargs={'pk': self.object.pk})


class HiringUpdateView(LoginRequiredMixin, AccessControlObjectMixin, UpdateView):
    """
    Представление для редактирования записи о приеме на работу
    """
    model = EmployeeHiring
    # form_class = EmployeeHiringRecordForm  # Закомментируем эту строку, так как у нас нет этой формы
    fields = [
        'employee', 'hiring_date', 'start_date', 'hiring_type',
        'organization', 'subdivision', 'department', 'position',
        'notes', 'is_active'
    ]  # Вместо form_class используем fields
    template_name = 'directory/hiring/form.html'

    def get_form(self, form_class=None):
        form = super().get_form(form_class)
        # Добавляем атрибуты формы, которые были бы в EmployeeHiringRecordForm
        form.helper = FormHelper()
        form.helper.form_method = 'post'

        # Настраиваем виджеты для полей формы
        form.fields['hiring_date'].widget = forms.DateInput(attrs={'type': 'date', 'class': 'form-control'})
        form.fields['start_date'].widget = forms.DateInput(attrs={'type': 'date', 'class': 'form-control'})

        # Ограничиваем организации через AccessControlHelper
        form.fields['organization'].queryset = AccessControlHelper.get_accessible_organizations(
            self.request.user, self.request
        )

        return form

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['title'] = _('Редактирование записи о приеме на работу')
        return context

    def form_valid(self, form):
        messages.success(self.request, _('Запись о приеме на работу успешно обновлена'))
        return super().form_valid(form)

    def get_success_url(self):
        return reverse_lazy('directory:hiring:hiring_detail', kwargs={'pk': self.object.pk})


class HiringDeleteView(LoginRequiredMixin, AccessControlObjectMixin, DeleteView):
    """
    Представление для удаления записи о приеме на работу
    """
    model = EmployeeHiring
    template_name = 'directory/hiring/confirm_delete.html'
    success_url = reverse_lazy('directory:hiring:hiring_list')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['title'] = _('Удаление записи о приеме на работу')
        return context

    def delete(self, request, *args, **kwargs):
        messages.success(request, _('Запись о приеме на работу успешно удалена'))
        return super().delete(request, *args, **kwargs)


class HiringAssignTrainingView(LoginRequiredMixin, AccessControlObjectMixin, SingleObjectMixin, View):
    """
    🎓 Назначение обучения на производстве сотруднику прямо из записи о приёме.

    Позволяет создать курс обучения (ProductionTraining) и назначение
    (TrainingAssignment) для сотрудника, не заходя в админку.
    """
    model = EmployeeHiring

    def get(self, request, *args, **kwargs):
        from production_training.forms import AssignTrainingForm

        hiring = self.get_object()
        form = AssignTrainingForm(initial={'start_date': hiring.start_date}, employee=hiring.employee)
        return render(request, 'directory/hiring/assign_training.html', {
            'title': _('Назначить обучение'),
            'hiring': hiring,
            'employee': hiring.employee,
            'form': form,
        })

    def post(self, request, *args, **kwargs):
        from production_training.forms import AssignTrainingForm
        from production_training.models import ProductionTraining, TrainingAssignment

        hiring = self.get_object()
        employee = hiring.employee
        form = AssignTrainingForm(request.POST, employee=employee)

        if not form.is_valid():
            return render(request, 'directory/hiring/assign_training.html', {
                'title': _('Назначить обучение'),
                'hiring': hiring,
                'employee': employee,
                'form': form,
            })

        training_type = form.cleaned_data['training_type']
        profession = form.cleaned_data['profession']
        program = form.cleaned_data.get('program')
        qualification_grade = getattr(program, 'qualification_grade', None)
        start_date = form.cleaned_data['start_date']
        full_name_by = form.cleaned_data.get('full_name_by')
        education_level = form.cleaned_data.get('education_level')
        prior_qualification = form.cleaned_data.get('prior_qualification')
        work_schedule = form.cleaned_data.get('work_schedule')

        update_fields = []
        if full_name_by:
            employee.full_name_by = full_name_by
            update_fields.append('full_name_by')
        if education_level:
            employee.education_level = education_level
            update_fields.append('education_level')
        if prior_qualification:
            employee.prior_qualification = prior_qualification
            update_fields.append('prior_qualification')
        if work_schedule and work_schedule != employee.work_schedule:
            employee.work_schedule = work_schedule
            update_fields.append('work_schedule')
        if update_fields:
            employee.save(update_fields=update_fields)

        training = ProductionTraining.objects.filter(
            organization=employee.organization,
            subdivision=employee.subdivision,
            department=employee.department,
            training_type=training_type,
            profession=profession,
            program=program,
            qualification_grade=qualification_grade,
        ).first()
        if not training:
            training = ProductionTraining(
                organization=employee.organization,
                subdivision=employee.subdivision,
                department=employee.department,
                training_type=training_type,
                profession=profession,
                program=program,
                qualification_grade=qualification_grade,
            )
            training.save()

        TrainingAssignment.objects.create(
            training=training,
            employee=employee,
            current_position=employee.position,
            prior_qualification=prior_qualification or employee.prior_qualification,
            start_date=start_date,
        )

        messages.success(request, _('🎓 Обучение назначено сотруднику %(name)s') % {
            'name': employee.full_name_nominative
        })
        return redirect('directory:hiring:hiring_detail', pk=hiring.pk)


class CreateHiringFromEmployeeView(LoginRequiredMixin, FormView):
    """
    Представление для создания записи о приеме на основе существующего сотрудника
    """
    template_name = 'directory/hiring/create_from_employee.html'
    form_class = forms.Form  # Пустая форма, так как данные берутся из сотрудника

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        employee_id = self.kwargs.get('employee_id')
        employee = get_object_or_404(Employee.objects.active_for_operations(), id=employee_id)
        context['employee'] = employee
        context['title'] = _('Создание записи о приеме из сотрудника')
        return context

    def form_valid(self, form):
        employee_id = self.kwargs.get('employee_id')
        employee = get_object_or_404(Employee.objects.active_for_operations(), id=employee_id)

        try:
            hiring = create_hiring_from_employee(employee, self.request.user)
            messages.success(
                self.request,
                _('Запись о приеме на работу успешно создана на основе данных сотрудника')
            )
            return redirect('directory:hiring:hiring_detail', pk=hiring.pk)
        except Exception as e:
            logger.error(f"Ошибка при создании записи о приеме: {e}")
            messages.error(self.request, _('Произошла ошибка при создании записи о приеме'))
            return self.form_invalid(form)


@login_required
def preview_hiring_email(request, hiring_id):
    """
    AJAX endpoint для предпросмотра письма с документами приема.

    Возвращает JSON с информацией о письме:
    - recipients: список адресатов
    - subject: тема письма
    - body: тело письма (HTML)
    - document_names: список названий документов
    """
    if request.method != 'POST':
        return JsonResponse({'error': 'Требуется POST запрос'}, status=400)

    # Получить hiring и проверить права доступа
    hiring = get_object_or_404(EmployeeHiring, pk=hiring_id)

    if not AccessControlHelper.can_access_object(request.user, hiring):
        return JsonResponse({'error': 'Нет прав доступа'}, status=403)

    # Получить выбранные типы документов
    document_types = request.POST.getlist('document_types')

    if not document_types:
        return JsonResponse({'error': 'Не выбран ни один документ'}, status=400)

    employee = hiring.employee
    organization = hiring.organization
    subdivision = hiring.subdivision

    # Получить настройки email
    try:
        email_settings = EmailSettings.get_settings(organization)
    except Exception as e:
        return JsonResponse({'error': f'Ошибка настроек email: {str(e)}'}, status=500)

    if not email_settings.is_active:
        return JsonResponse({'error': 'Email уведомления отключены'}, status=400)

    # Собрать получателей
    if subdivision:
        recipients = collect_recipients_for_subdivision(
            subdivision=subdivision,
            organization=organization,
            notification_type='general'
        )
    else:
        recipients = email_settings.get_recipient_list()

    if not recipients:
        return JsonResponse({'error': 'Нет получателей для отправки'}, status=400)

    # Получить шаблон письма
    template_data = email_settings.get_email_template('documents_priem')

    if not template_data:
        return JsonResponse({'error': 'Шаблон письма не настроен'}, status=400)

    subject_template, body_template = template_data

    # Подготовить переменные для шаблона
    template_vars = {
        'organization_name': organization.short_name_ru or organization.full_name_ru,
        'employee_name': employee.full_name_nominative,
        'position_name': hiring.position.position_name,
        'subdivision_name': subdivision.name if subdivision else "Без подразделения",
        'department_name': hiring.department.name if hiring.department else "Без отдела",
        'hiring_date': hiring.hiring_date.strftime('%d.%m.%Y'),
        'start_date': hiring.start_date.strftime('%d.%m.%Y'),
        'hiring_type': hiring.get_hiring_type_display(),
        'document_count': len(document_types),  # Примерное количество
        'date': timezone.now().strftime('%d.%m.%Y'),
    }

    # Форматировать тему и тело
    try:
        subject = subject_template.format(**template_vars)
        html_body = body_template.format(**template_vars)
    except KeyError as e:
        return JsonResponse({'error': f'Ошибка в шаблоне: переменная {e} не найдена'}, status=500)

    # Получить названия документов
    document_names_map = {
        'all_orders': '📄 Все распоряжения',
        'knowledge_protocol': '📋 Протокол проверки знаний',
        'doc_familiarization': '✍️ Лист ознакомления с документами',
        'personal_ot_card': '🗂️ Личная карточка по охране труда',
        'journal_example': '📓 Пример заполнения журналов',
        'siz_card': '🧥 Карточка учета СИЗ',
        'vvodny_journal_template': '📺 Образец журнала вводного инструктажа',
    }

    document_names = [document_names_map.get(dt, dt) for dt in document_types]

    return JsonResponse({
        'success': True,
        'recipients': recipients,
        'subject': subject,
        'body': html_body,
        'document_names': document_names,
        'document_count': len(document_types)
    })


@login_required
def send_hiring_documents(request, hiring_id):
    """
    Отправляет документы приема на работу на email получателей подразделения.

    Генерирует документы на лету и отправляет их без сохранения в базу данных.
    Использует трёхуровневую систему сбора получателей:
    1. SubdivisionEmail - email адреса, настроенные для подразделения
    2. Employee.email - email ответственных за охрану труда
    3. EmailSettings - общие email адреса организации
    """
    # ШАГ 1: Получить hiring и связанные объекты
    hiring = get_object_or_404(EmployeeHiring, pk=hiring_id)
    employee = hiring.employee
    organization = hiring.organization
    subdivision = hiring.subdivision

    # ШАГ 2: Проверить права доступа
    if not AccessControlHelper.can_access_object(request.user, hiring):
        messages.error(request, "У вас нет прав доступа к этой записи о приеме")
        return redirect('directory:hiring:hiring_detail', pk=hiring_id)

    logger.info(
        f"Начало отправки документов приема для сотрудника '{employee.full_name_nominative}' "
        f"(hiring_id={hiring_id})"
    )

    # ШАГ 3: Получить настройки email
    try:
        email_settings = EmailSettings.get_settings(organization)
    except Exception as e:
        messages.error(request, f"Не удалось получить настройки email: {str(e)}")
        return redirect('directory:hiring:hiring_detail', pk=hiring_id)

    # ШАГ 3.1: Проверить, активны ли настройки
    if not email_settings.is_active:
        messages.error(
            request,
            f"Email уведомления отключены для {organization.short_name_ru}. "
            f"Настройте email в админке: Email Settings."
        )
        return redirect('directory:hiring:hiring_detail', pk=hiring_id)

    # ШАГ 3.2: Проверить, настроен ли SMTP
    if not email_settings.email_host:
        messages.error(
            request,
            f"SMTP сервер не настроен для {organization.short_name_ru}. "
            f"Укажите настройки в админке: Email Settings."
        )
        return redirect('directory:hiring:hiring_detail', pk=hiring_id)

    # ШАГ 4: Сгенерировать документы
    # Импортируем генераторы
    from directory.document_generators.order_generator import generate_all_orders
    from directory.document_generators.protocol_generator import generate_knowledge_protocol
    from directory.document_generators.familiarization_generator import generate_familiarization_document
    from directory.document_generators.ot_card_generator import generate_personal_ot_card
    from directory.document_generators.journal_example_generator import generate_journal_example
    from directory.document_generators.siz_card_docx_generator import generate_siz_card_docx

    # Генерируем все доступные типы документов
    generated_files = []
    
    try:
        # 1. Все распоряжения
        result = generate_all_orders(employee=employee, user=request.user)
        if result and isinstance(result, list):
            for doc in result:
                if isinstance(doc, dict) and 'content' in doc and 'filename' in doc:
                    generated_files.append((doc['content'], doc['filename']))
                    logger.info(f"Сгенерирован документ: {doc['filename']}")
    except Exception as e:
        logger.warning(f"Ошибка при генерации распоряжений: {str(e)}")

    try:
        # 2. Протокол проверки знаний
        result = generate_knowledge_protocol(employee=employee, user=request.user)
        if result and isinstance(result, dict) and 'content' in result and 'filename' in result:
            generated_files.append((result['content'], result['filename']))
            logger.info(f"Сгенерирован документ: {result['filename']}")
    except Exception as e:
        logger.warning(f"Ошибка при генерации протокола: {str(e)}")

    try:
        # 3. Ознакомление с документами
        result = generate_familiarization_document(employee=employee, user=request.user, document_list=None)
        if result and isinstance(result, dict) and 'content' in result and 'filename' in result:
            generated_files.append((result['content'], result['filename']))
            logger.info(f"Сгенерирован документ: {result['filename']}")
    except Exception as e:
        logger.warning(f"Ошибка при генерации ознакомления: {str(e)}")

    try:
        # 4. Личная карточка по ОТ
        result = generate_personal_ot_card(employee=employee, user=request.user)
        if result and isinstance(result, dict) and 'content' in result and 'filename' in result:
            generated_files.append((result['content'], result['filename']))
            logger.info(f"Сгенерирован документ: {result['filename']}")
    except Exception as e:
        logger.warning(f"Ошибка при генерации личной карточки: {str(e)}")

    try:
        # 5. Пример журнала
        result = generate_journal_example(employee=employee, user=request.user)
        if result and isinstance(result, dict) and 'content' in result and 'filename' in result:
            generated_files.append((result['content'], result['filename']))
            logger.info(f"Сгенерирован документ: {result['filename']}")
    except Exception as e:
        logger.warning(f"Ошибка при генерации журнала: {str(e)}")

    try:
        # 6. Карточка учета СИЗ
        result = generate_siz_card_docx(employee=employee, user=request.user)
        if result and isinstance(result, dict) and 'content' in result and 'filename' in result:
            generated_files.append((result['content'], result['filename']))
            logger.info(f"Сгенерирован документ: {result['filename']}")
    except Exception as e:
        logger.warning(f"Ошибка при генерации карточки СИЗ: {str(e)}")

    if not generated_files:
        messages.error(
            request,
            "Не удалось сгенерировать ни одного документа. "
            "Проверьте настройки шаблонов документов."
        )
        return redirect('directory:hiring:hiring_detail', pk=hiring_id)

    logger.info(f"Сгенерировано {len(generated_files)} документов")

    # ШАГ 5: Собрать получателей
    if subdivision:
        recipients = collect_recipients_for_subdivision(
            subdivision=subdivision,
            organization=organization,
            notification_type='general'
        )
    else:
        recipients = email_settings.get_recipient_list()

    if not recipients:
        messages.error(
            request,
            mark_safe(
                "Нет получателей для отправки. Настройте email получателей:<br>"
                "1. Email подразделения (SubdivisionEmail)<br>"
                "2. Email ответственных за ОТ (в карточке сотрудника)<br>"
                "3. Общие получатели в Email Settings"
            )
        )
        return redirect('directory:hiring:hiring_detail', pk=hiring_id)

    logger.info(f"Собрано {len(recipients)} получателей: {', '.join(recipients)}")

    # ШАГ 6: Получить шаблон письма
    template_data = email_settings.get_email_template('documents_priem')

    if not template_data:
        messages.error(
            request,
            "Шаблон письма 'documents_priem' не настроен для этой организации. "
            "Создайте шаблон в админке: Email Templates."
        )
        return redirect('directory:hiring:hiring_detail', pk=hiring_id)

    subject_template, body_template = template_data

    # ШАГ 7: Подготовить переменные для шаблона
    template_vars = {
        'organization_name': organization.short_name_ru or organization.full_name_ru,
        'employee_name': employee.full_name_nominative,
        'position_name': hiring.position.position_name,
        'subdivision_name': subdivision.name if subdivision else "Без подразделения",
        'department_name': hiring.department.name if hiring.department else "Без отдела",
        'hiring_date': hiring.hiring_date.strftime('%d.%m.%Y'),
        'start_date': hiring.start_date.strftime('%d.%m.%Y'),
        'hiring_type': hiring.get_hiring_type_display(),
        'document_count': len(generated_files),
        'date': timezone.now().strftime('%d.%m.%Y'),
    }

    # ШАГ 8: Форматировать тему и тело письма
    try:
        subject = subject_template.format(**template_vars)
        html_message = body_template.format(**template_vars)
    except KeyError as e:
        messages.error(
            request,
            mark_safe(
                f"Ошибка в шаблоне письма: переменная {e} не найдена.<br>"
                f"Доступные переменные: {', '.join(template_vars.keys())}"
            )
        )
        return redirect('directory:hiring:hiring_detail', pk=hiring_id)

    # ШАГ 9: Создать email с вложениями
    try:
        connection = email_settings.get_connection()
        from_email = email_settings.default_from_email or email_settings.email_host_user

        text_message = strip_tags(html_message)

        email = EmailMultiAlternatives(
            subject=subject,
            body=text_message,
            from_email=from_email,
            to=recipients,
            connection=connection
        )

        email.attach_alternative(html_message, "text/html")

        # ШАГ 10: Прикрепить сгенерированные документы
        for file_content, filename in generated_files:
            try:
                email.attach(
                    filename,
                    file_content,
                    'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
                )
                logger.info(f"Прикреплен документ: {filename}")
            except Exception as e:
                logger.error(f"Ошибка прикрепления документа {filename}: {str(e)}", exc_info=True)
                continue

        # ШАГ 11: Отправить email
        email.send(fail_silently=False)

        logger.info(
            f"Документы приема отправлены для '{employee.full_name_nominative}'. "
            f"Получатели: {', '.join(recipients)}. Документов: {len(generated_files)}"
        )

        messages.success(
            request,
            mark_safe(
                f"✅ Документы приема успешно отправлены на {len(recipients)} адрес(ов):<br>"
                f"<strong>{', '.join(recipients)}</strong><br>"
                f"Отправлено документов: {len(generated_files)}"
            )
        )

    except Exception as e:
        logger.error(
            f"Ошибка отправки email для hiring_id={hiring_id}: {str(e)}",
            exc_info=True
        )
        messages.error(
            request,
            mark_safe(
                f"❌ Ошибка при отправке email:<br>"
                f"<code>{str(e)}</code><br>"
                f"Проверьте настройки SMTP в Email Settings."
            )
        )

    return redirect('directory:hiring:hiring_detail', pk=hiring_id)
