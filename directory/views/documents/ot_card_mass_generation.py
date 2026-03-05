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
        return Employee.objects.filter(
            status='active',
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
        org_ids_with_employees = Employee.objects.filter(
            status='active',
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
    📋 Генерация ZIP-архива с личными карточками по ОТ для выбранных сотрудников
    """
    employee_ids = request.POST.getlist('employee_ids')
    instruction_date = (
        request.POST.get('date_povtorny')
        or request.POST.get('instruction_date')
        or ''
    )
    instruction_type = request.POST.get('instruction_type') or 'Повторный'
    instruction_reason = request.POST.get('instruction_reason') or ''

    if not employee_ids:
        return HttpResponse("Не выбрано ни одного сотрудника", status=400)

    # Форматируем дату
    instruction_date_display = ''
    if instruction_date:
        try:
            instruction_date_display = datetime.strptime(instruction_date, '%Y-%m-%d').strftime('%d.%m.%Y')
        except ValueError:
            instruction_date_display = instruction_date

    # Контекст для шаблона DOCX
    custom_context = {
        'instruction_date': instruction_date_display,
        'instruction_type': instruction_type,
        'instruction_reason': instruction_reason,
    }

    # Получаем сотрудников
    employees = Employee.objects.filter(
        id__in=employee_ids,
        status='active',
        position__isnull=False,
    ).select_related(
        'position', 'organization', 'subdivision', 'department'
    ).order_by(
        'subdivision__name', 'department__name', 'full_name_nominative'
    )

    # Создаём ZIP-архив в памяти
    zip_buffer = io.BytesIO()

    with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
        generated_count = 0
        errors = []

        for employee in employees:
            try:
                result = generate_personal_ot_card(
                    employee,
                    user=request.user,
                    custom_context=custom_context,
                )
            except Exception as e:
                errors.append(f"Ошибка генерации для {employee.full_name_nominative}: {e}")
                logger.error(f"Ошибка генерации карточки ОТ для {employee.full_name_nominative}: {e}")
                continue

            if result and 'content' in result:
                # Определяем папку в ZIP
                if employee.subdivision:
                    folder = re.sub(r'[<>:"/\\|?*]', '_', employee.subdivision.name)
                else:
                    org_name = employee.organization.short_name_ru or employee.organization.full_name_ru
                    folder = re.sub(r'[<>:"/\\|?*]', '_', org_name) + ' (без подразделения)'

                safe_employee = re.sub(r'[<>:"/\\|?*]', '_', employee.full_name_nominative)
                safe_position = re.sub(r'[<>:"/\\|?*]', '_', employee.position.position_name)
                file_path = f"{folder}/{safe_employee}_{safe_position}.docx"
                zip_file.writestr(file_path, result['content'])
                generated_count += 1
                logger.info(f"Добавлена карточка ОТ: {file_path}")
            else:
                errors.append(f"Ошибка генерации для {employee.full_name_nominative}: результат пустой")

        # Добавляем файл со сводкой
        summary = f"""Массовая генерация личных карточек по охране труда
Дата генерации: {datetime.now().strftime('%d.%m.%Y %H:%M')}
Вид инструктажа: {instruction_type}
Дата инструктажа: {instruction_date_display or 'не указана'}
{f'Причина: {instruction_reason}' if instruction_reason else ''}
Сгенерировано карточек: {generated_count}

"""
        if errors:
            summary += "Ошибки:\n" + "\n".join(errors)

        zip_file.writestr("_summary.txt", summary.encode('utf-8'))

    # Отправляем архив пользователю
    zip_buffer.seek(0)
    response = HttpResponse(zip_buffer.read(), content_type='application/zip')

    filename = f"Личные_карточки_ОТ_{datetime.now().strftime('%Y%m%d_%H%M%S')}.zip"
    response['Content-Disposition'] = f'attachment; filename="{filename}"'

    logger.info(f"Массовая генерация карточек ОТ завершена. Создано файлов: {generated_count}")

    return response
