# directory/views/documents/ot_card_mass_generation.py
"""
📋 Массовая генерация личных карточек по охране труда
Древовидный выбор сотрудников: Организация → Подразделение → Отдел → Сотрудники
"""
import io
import re
import zipfile
import logging
from datetime import datetime, date

from django.views.generic import TemplateView
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST
from django.http import HttpResponse
from django.db.models import Q

from directory.models import Employee, Organization
from directory.utils.permissions import AccessControlHelper
from directory.document_generators.ot_card_generator import generate_personal_ot_card

logger = logging.getLogger(__name__)

# Виды инструктажей (без вводного - он проводится всегда при приёме)
INSTRUCTION_TYPE_CHOICES = [
    ('Повторный', 'Повторный'),
    ('Внеплановый', 'Внеплановый'),
    ('Целевой', 'Целевой'),
]

SESSION_KEY = 'selected_org_id'


class OTCardMassGenerationView(LoginRequiredMixin, TemplateView):
    """
    📋 Личные карточки по ОТ - массовая генерация
    Древовидный выбор сотрудников по паттерну PeriodicProtocolView.
    """
    template_name = 'directory/ot_card/mass_generation.html'

    def get_employees_queryset(self, org_id):
        """Получаем активных сотрудников с должностью для организации"""
        return Employee.objects.active_for_operations().filter(
            position__isnull=False,
            organization_id=org_id,
        ).select_related(
            'organization', 'subdivision', 'department', 'position'
        ).order_by(
            'subdivision__name',
            'department__name',
            'full_name_nominative'
        )

    def build_tree_structure(self, employees):
        """
        Строит древовидную структуру: Организация → Подразделение → Отдел → Сотрудники.
        """
        tree = {}

        for emp in employees:
            org = emp.organization
            sub = emp.subdivision
            dept = emp.department

            if org not in tree:
                tree[org] = {
                    'name': org.short_name_ru,
                    'items': [],
                    'subdivisions': {}
                }

            if not sub:
                tree[org]['items'].append(emp)
                continue

            if sub not in tree[org]['subdivisions']:
                tree[org]['subdivisions'][sub] = {
                    'name': sub.name,
                    'items': [],
                    'departments': {}
                }

            if not dept:
                tree[org]['subdivisions'][sub]['items'].append(emp)
                continue

            if dept not in tree[org]['subdivisions'][sub]['departments']:
                tree[org]['subdivisions'][sub]['departments'][dept] = {
                    'name': dept.name,
                    'items': []
                }

            tree[org]['subdivisions'][sub]['departments'][dept]['items'].append(emp)

        return tree

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user

        # Доступные организации
        if user.is_superuser:
            accessible_orgs = Organization.objects.all()
        else:
            accessible_orgs = AccessControlHelper.get_accessible_organizations(user, self.request)

        # Фильтруем: только организации с активными сотрудниками с должностью
        org_ids_with_employees = Employee.objects.active_for_operations().filter(
            position__isnull=False,
            organization__in=accessible_orgs,
        ).values_list('organization_id', flat=True).distinct()
        accessible_orgs = accessible_orgs.filter(id__in=org_ids_with_employees)

        # Определяем выбранную организацию
        org_id_param = self.request.GET.get('org', '')
        selected_org_id = None

        if org_id_param:
            try:
                org_id = int(org_id_param)
                if accessible_orgs.filter(id=org_id).exists():
                    selected_org_id = org_id
            except (ValueError, TypeError):
                pass

        # Автовыбор если одна организация
        if selected_org_id is None and accessible_orgs.count() == 1:
            selected_org_id = accessible_orgs.first().id

        # Session: сохранение / восстановление
        try:
            if selected_org_id:
                self.request.session[SESSION_KEY] = selected_org_id
            elif hasattr(self.request, 'session') and SESSION_KEY in self.request.session:
                last_org_id = self.request.session.get(SESSION_KEY)
                if accessible_orgs.filter(id=last_org_id).exists():
                    selected_org_id = last_org_id
        except Exception as e:
            logger.warning(f"Session not available: {e}")

        # Контекст
        context['title'] = 'Личные карточки по охране труда'
        context['instruction_types'] = INSTRUCTION_TYPE_CHOICES
        context['default_date'] = date.today().strftime('%Y-%m-%d')

        if selected_org_id and accessible_orgs.count() == 1:
            context['org_options'] = accessible_orgs.filter(id=selected_org_id)
        else:
            context['org_options'] = accessible_orgs
        context['selected_org_id'] = selected_org_id
        context['show_tree'] = selected_org_id is not None
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

        employees = list(self.get_employees_queryset(selected_org_id))
        context['tree'] = self.build_tree_structure(employees)
        context['employees_count'] = len(employees)

        return context


@login_required
@require_POST
def generate_ot_cards_bulk(request):
    """
    📋 Асинхронная генерация ZIP-архива с личными карточками по ОТ.
    Ставит задачу в очередь → редиректит на страницу прогресса.
    """
    from directory.models import GenerationJob
    from directory.generation_tasks import run_ot_card_bulk_job
    from django.contrib import messages
    from django.shortcuts import redirect
    from django.urls import reverse

    employee_ids = request.POST.getlist('employee_ids')
    if not employee_ids:
        return HttpResponse("Не выбрано ни одного сотрудника", status=400)

    instruction_date_raw = (
        request.POST.get('date_povtorny')
        or request.POST.get('instruction_date')
        or ''
    )
    instruction_type = request.POST.get('instruction_type') or 'Повторный'
    instruction_reason = request.POST.get('instruction_reason') or ''

    # Форматируем дату для хранения в params
    instruction_date_display = ''
    if instruction_date_raw:
        try:
            instruction_date_display = datetime.strptime(instruction_date_raw, '%Y-%m-%d').strftime('%d.%m.%Y')
        except ValueError:
            instruction_date_display = instruction_date_raw

    # Берём название организации для заголовка
    first_emp = Employee.objects.filter(id__in=employee_ids[:1]).select_related('organization').first()
    org_name = first_emp.organization.short_name_ru if first_emp and first_emp.organization else ''

    job = GenerationJob.objects.create(
        user=request.user,
        job_type='ot_card_bulk',
        status='pending',
        title=f'Личные карточки по ОТ — {org_name} ({len(employee_ids)} чел.)',
        params={
            'employee_ids': [int(i) for i in employee_ids],
            'instruction_date': instruction_date_display,
            'instruction_type': instruction_type,
            'instruction_reason': instruction_reason,
        },
        progress_total=len(employee_ids),
    )

    run_ot_card_bulk_job.enqueue(job.id)

    messages.success(
        request,
        f'Задача генерации карточек ОТ поставлена в очередь ({len(employee_ids)} сотр.). '
        f'Файл появится на странице статуса.'
    )
    return redirect(reverse('directory:generation_job_detail', args=[job.id]))
