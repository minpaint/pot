# directory/views/documents/protocol.py

from django import forms
from django.views.generic import FormView, TemplateView
from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import get_object_or_404, redirect
from django.contrib import messages
from django.urls import reverse
from django.http import HttpResponse
from django.db.models import Q
from django.utils.text import slugify
import logging
from io import BytesIO
from zipfile import ZipFile

from directory.models import Employee, Organization
from directory.document_generators.protocol_generator import generate_knowledge_protocol, generate_periodic_protocol
from directory.document_generators.certificate_generator_rowwise import generate_safety_certificates_rowwise as generate_safety_certificates
from directory.utils import (
    find_appropriate_commission,
    get_commission_members_formatted,
    is_employee_commission_member,
)
from directory.utils.permissions import AccessControlHelper

# Настройка логирования
logger = logging.getLogger(__name__)


class ProtocolForm(forms.Form):
    """
    Форма для указания параметров протокола проверки знаний.
    Без возможности выбора комиссии (комиссия определяется автоматически).
    """
    ticket_number = forms.IntegerField(
        label="Номер билета",
        min_value=1,
        required=True,
        widget=forms.NumberInput(attrs={'class': 'form-control'})
    )

    test_result = forms.ChoiceField(
        label="Результат проверки знаний",
        choices=[
            ('прошел', 'Прошел'),
            ('не прошел', 'Не прошел')
        ],
        required=True,
        initial='прошел',
        widget=forms.Select(attrs={'class': 'form-control'})
    )

    def __init__(self, *args, **kwargs):
        employee = kwargs.pop('employee', None)
        super().__init__(*args, **kwargs)

        # Устанавливаем номер билета по умолчанию на основе ID сотрудника
        if employee and employee.id:
            self.fields['ticket_number'].initial = employee.id % 20 + 1


class KnowledgeProtocolCreateView(LoginRequiredMixin, FormView):
    """
    Представление для создания протокола проверки знаний
    с автоматическим выбором комиссии.
    """
    template_name = 'directory/documents/protocol_form.html'
    form_class = ProtocolForm

    def get_employee(self):
        """Получает сотрудника из параметров URL"""
        employee_id = self.kwargs.get('employee_id')
        return get_object_or_404(Employee.objects.active_for_operations(), id=employee_id)

    def get_form_kwargs(self):
        """Передаем сотрудника в форму"""
        kwargs = super().get_form_kwargs()
        kwargs['employee'] = self.get_employee()
        return kwargs

    def get_context_data(self, **kwargs):
        """Добавляет данные о сотруднике и комиссии в контекст"""
        context = super().get_context_data(**kwargs)
        employee = self.get_employee()

        context['employee'] = employee
        context['title'] = f'Протокол проверки знаний: {employee.full_name_nominative}'

        # Находим подходящую комиссию автоматически
        commission = find_appropriate_commission(employee)

        if commission:
            context['commission'] = commission

            if is_employee_commission_member(employee, commission):
                context['warning_message'] = (
                    "Сотрудник входит в состав комиссии. "
                    "Протокол проверки знаний для него не формируется."
                )
                return context

            # Получаем и форматируем участников комиссии для предпросмотра
            commission_data = get_commission_members_formatted(commission)
            context['commission_data'] = commission_data

            # Проверяем полноту состава комиссии
            has_chairman = bool(commission_data.get('chairman'))
            has_secretary = bool(commission_data.get('secretary'))
            has_members = len(commission_data.get('members', [])) > 0

            # Если состав неполный, выводим предупреждение
            if not (has_chairman and has_secretary and has_members):
                missing = []
                if not has_chairman:
                    missing.append('председатель')
                if not has_secretary:
                    missing.append('секретарь')
                if not has_members:
                    missing.append('члены комиссии')

                context['warning_message'] = f"Внимание! В комиссии отсутствуют: {', '.join(missing)}."
        else:
            context['warning_message'] = "Не найдена подходящая комиссия для сотрудника."

        # Добавляем информацию о выбранных ранее типах документов (если есть)
        if 'selected_document_types' in self.request.session:
            context['selected_document_types'] = self.request.session['selected_document_types']

        return context

    def form_valid(self, form):
        """Обрабатывает отправку формы"""
        employee = self.get_employee()
        ticket_number = form.cleaned_data['ticket_number']
        test_result = form.cleaned_data['test_result']

        # Находим подходящую комиссию автоматически
        commission = find_appropriate_commission(employee)

        if not commission:
            messages.error(self.request, 'Не найдена подходящая комиссия для сотрудника')
            return self.form_invalid(form)

        if is_employee_commission_member(employee, commission):
            messages.error(
                self.request,
                'Сотрудник входит в состав комиссии и не может принимать знания сам у себя'
            )
            return self.form_invalid(form)

        # Получаем данные о комиссии
        commission_data = get_commission_members_formatted(commission)

        # Проверяем полноту состава комиссии
        has_chairman = bool(commission_data.get('chairman'))
        has_secretary = bool(commission_data.get('secretary'))
        has_members = len(commission_data.get('members', [])) > 0

        if not (has_chairman and has_secretary and has_members):
            missing = []
            if not has_chairman:
                missing.append('председатель')
            if not has_secretary:
                missing.append('секретарь')
            if not has_members:
                missing.append('члены комиссии')

            messages.warning(
                self.request,
                f"В комиссии '{commission.name}' отсутствуют: {', '.join(missing)}. "
                f"Протокол будет создан с неполным составом комиссии."
            )

        # Создаем контекст для передачи в генератор протокола
        custom_context = {
            'commission_name': commission_data.get('commission_name', ''),
            'ticket_number': ticket_number,
            'test_result': test_result,
        }

        # Добавляем информацию о председателе
        chairman = commission_data.get('chairman', {})
        if chairman:
            custom_context.update({
                'chairman_name': chairman.get('name', ''),
                'chairman_position': chairman.get('position', ''),
                'chairman_name_initials': chairman.get('name_initials', ''),
                'chairman_formatted': chairman.get('formatted', '')
            })

        # Добавляем информацию о секретаре
        secretary = commission_data.get('secretary', {})
        if secretary:
            custom_context.update({
                'secretary_name': secretary.get('name', ''),
                'secretary_position': secretary.get('position', ''),
                'secretary_name_initials': secretary.get('name_initials', ''),
                'secretary_formatted': secretary.get('formatted', '')
            })

        # Добавляем информацию о членах комиссии
        members = commission_data.get('members', [])
        custom_context['commission_members'] = [m.get('formatted', '') for m in members]

        # Добавляем полную информацию о всех участниках для шаблона
        custom_context['members_formatted'] = commission_data.get('members_formatted', [])

        # Генерируем протокол - функция возвращает словарь
        generated_doc = generate_knowledge_protocol(
            employee=employee,
            user=self.request.user,
            custom_context=custom_context
        )

        if generated_doc:
            response = HttpResponse(
                generated_doc['content'],
                content_type='application/vnd.openxmlformats-officedocument.wordprocessingml.document'
            )
            from urllib.parse import quote
            filename_encoded = quote(generated_doc['filename'])
            response['Content-Disposition'] = f'attachment; filename="{generated_doc["filename"]}"; filename*=UTF-8\'\'{filename_encoded}'

            messages.success(self.request, 'Протокол проверки знаний успешно сгенерирован')
            return response
        else:
            messages.error(self.request, 'Ошибка при генерации протокола проверки знаний')
            return self.form_invalid(form)



class PeriodicProtocolView(LoginRequiredMixin, TemplateView):
    """
    Карточка периодической проверки знаний с выбором сотрудников и скачиванием протокола.
    Использует древовидное представление: Организация → Подразделение → Отдел.
    """
    template_name = 'directory/documents/periodic_protocol_tree.html'

    def get_base_queryset(self):
        qs = Employee.objects.active_for_operations().select_related(
            'organization', 'subdivision', 'department', 'position'
        )
        qs = AccessControlHelper.filter_queryset(qs, self.request.user, self.request)
        qs = qs.filter(position__isnull=False).filter(
            Q(position__internship_period_days__gt=0) |
            Q(position__is_responsible_for_safety=True) |
            Q(position__drives_company_vehicle=True) |
            Q(position__height_group_1=True) |
            Q(position__height_group_2=True) |
            Q(position__height_group_3=True)
        )
        return qs.order_by(
            'organization__short_name_ru',
            'subdivision__name',
            'department__name',
            'full_name_nominative'
        )

    def build_tree_structure(self, employees):
        """
        Строит древовидную структуру: Организация → Подразделение → Отдел → Сотрудники.

        Возвращает словарь вида:
        {
            organization: {
                'name': str,
                'items': [employees without subdivision],
                'subdivisions': {
                    subdivision: {
                        'name': str,
                        'items': [employees without department],
                        'departments': {
                            department: {
                                'name': str,
                                'items': [employees]
                            }
                        }
                    }
                }
            }
        }
        """
        tree = {}

        for emp in employees:
            org = emp.organization
            sub = emp.subdivision
            dept = emp.department

            # Инициализируем организацию
            if org not in tree:
                tree[org] = {
                    'name': org.short_name_ru,
                    'items': [],
                    'subdivisions': {}
                }

            # Если нет подразделения, добавляем сотрудника напрямую к организации
            if not sub:
                tree[org]['items'].append(emp)
                continue

            # Инициализируем подразделение
            if sub not in tree[org]['subdivisions']:
                tree[org]['subdivisions'][sub] = {
                    'name': sub.name,
                    'items': [],
                    'departments': {}
                }

            # Если нет отдела, добавляем сотрудника к подразделению
            if not dept:
                tree[org]['subdivisions'][sub]['items'].append(emp)
                continue

            # Инициализируем отдел
            if dept not in tree[org]['subdivisions'][sub]['departments']:
                tree[org]['subdivisions'][sub]['departments'][dept] = {
                    'name': dept.name,
                    'items': []
                }

            # Добавляем сотрудника к отделу
            tree[org]['subdivisions'][sub]['departments'][dept]['items'].append(emp)

        return tree

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        user = self.request.user

        if user.is_superuser:
            accessible_orgs = Organization.objects.all()
        else:
            if hasattr(self.request, '_user_orgs_cache'):
                delattr(self.request, '_user_orgs_cache')
            accessible_orgs = AccessControlHelper.get_accessible_organizations(user, self.request)

        org_id_param = self.request.GET.get('org', '') or self.request.session.get('selected_org_id', '')
        selected_org_id = None

        if org_id_param:
            try:
                org_id = int(org_id_param)
                if accessible_orgs.filter(id=org_id).exists():
                    selected_org_id = org_id
                    logger.info(
                        f"User {user.username} viewing org_id={selected_org_id} in periodic protocol"
                    )
            except (ValueError, TypeError):
                pass

        if selected_org_id is None and accessible_orgs.count() == 1:
            selected_org_id = accessible_orgs.first().id
            logger.info(
                f"User {user.username} auto-selected org_id={selected_org_id} in periodic protocol"
            )

        try:
            if selected_org_id:
                self.request.session['selected_org_id'] = selected_org_id
        except Exception as e:
            logger.warning(f"Session not available: {e}")

        if selected_org_id and accessible_orgs.count() == 1:
            context['org_options'] = accessible_orgs.filter(id=selected_org_id)
        else:
            context['org_options'] = accessible_orgs
        context['selected_org_id'] = selected_org_id
        context['show_tree'] = selected_org_id is not None
        context['title'] = 'Периодическая проверка знаний'
        context['tree_settings'] = {
            'icons': {
                'organization': '🏢',
                'subdivision': '🏭',
                'department': '📂',
                'employee': '👤'
            }
        }

        if not context['show_tree']:
            context['tree'] = {}
            return context

        employees = list(self.get_base_queryset().filter(organization_id=selected_org_id))
        context['tree'] = self.build_tree_structure(employees)

        return context

    def post(self, request, *args, **kwargs):
        from directory.models import GenerationJob
        from directory.generation_tasks import run_periodic_protocol_job

        employees_qs = self.get_base_queryset()
        action = request.POST.get('action')
        scope_type = request.POST.get('scope_type')
        scope_id = request.POST.get('scope_id')

        if scope_type and scope_id:
            try:
                scope_id_int = int(scope_id)
            except (TypeError, ValueError):
                messages.error(request, "Некорректный идентификатор раздела")
                return redirect(request.path)

            if scope_type == 'org':
                employees_qs = employees_qs.filter(organization_id=scope_id_int)
            elif scope_type == 'sub':
                employees_qs = employees_qs.filter(subdivision_id=scope_id_int)
            elif scope_type == 'dept':
                employees_qs = employees_qs.filter(department_id=scope_id_int)
        else:
            selected_ids = request.POST.getlist('employee_ids')
            if selected_ids:
                employees_qs = employees_qs.filter(id__in=selected_ids)

        employees = sorted(
            employees_qs,
            key=lambda e: (not (e.position and e.position.is_responsible_for_safety))
        )
        if not employees:
            if scope_type:
                messages.error(request, "Нет сотрудников для выбранного раздела")
            else:
                messages.error(request, "Нет выбранных сотрудников для протокола")
            return redirect(request.path)

        employee_ids = [e.id for e in employees]

        # Определяем тип задачи и grouping_name
        grouping_name = None
        if action in {'scope_protocol', 'scope_certificates'}:
            if scope_type == 'org':
                grouping_name = employees[0].organization.short_name_ru if employees[0].organization else "Организация"
            elif scope_type == 'sub':
                grouping_name = employees[0].subdivision.name if employees[0].subdivision else "Подразделение"
            elif scope_type == 'dept':
                grouping_name = employees[0].department.name if employees[0].department else "Отдел"
            job_type = 'periodic_protocol' if action == 'scope_protocol' else 'periodic_certificates'
        elif action == 'certificates_org':
            job_type = 'periodic_certificates'
        elif action == 'certificates_by_subdivision':
            job_type = 'periodic_certificates_by_sub'
        elif action == 'download_by_subdivision':
            job_type = 'periodic_protocol_by_sub'
        else:
            job_type = 'periodic_protocol'

        title_map = dict(GenerationJob.JOB_TYPE_CHOICES)
        org = employees[0].organization
        org_name = org.short_name_ru if org else ''
        title = f'{title_map.get(job_type, job_type)} — {org_name} ({len(employees)} чел.)'

        check_type = request.POST.get('check_type', 'периодическая') or 'периодическая'
        height_only = request.POST.get('height_only') == '1'

        job = GenerationJob.objects.create(
            user=request.user,
            job_type=job_type,
            status='pending',
            title=title,
            params={
                'employee_ids': employee_ids,
                'grouping_name': grouping_name,
                'check_type': check_type,
                'height_only': height_only,
            },
            progress_total=len(employees),
        )

        run_periodic_protocol_job.enqueue(job.id)

        messages.success(
            request,
            f'Задача генерации поставлена в очередь ({len(employees)} сотр.). '
            f'Страница с прогрессом откроется автоматически.'
        )
        return redirect('directory:generation_job_detail', pk=job.id)
