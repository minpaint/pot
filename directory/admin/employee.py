# directory/admin/employee.py
from django.contrib import admin
from django.contrib import messages
from django.shortcuts import redirect, render
from django.urls import path, reverse
from django.http import HttpResponse, HttpResponseRedirect
from django.utils.html import format_html
from tablib import Dataset

from directory.models import Employee, Organization
from directory.models.commission import CommissionMember
from directory.models.siz_issued import SIZIssued
from directory.forms.employee import EmployeeForm
from directory.admin.mixins.tree_view import TreeViewMixin
from directory.resources.employee import EmployeeResource
import calendar
from datetime import date as _date


def _add_months(d, months):
    if not months:
        return None
    month = d.month - 1 + months
    year = d.year + month // 12
    month = month % 12 + 1
    day = min(d.day, calendar.monthrange(year, month)[1])
    return _date(year, month, day)


class SIZIssuedInline(admin.TabularInline):
    model = SIZIssued
    fk_name = 'employee'
    verbose_name = "Выданное СИЗ"
    verbose_name_plural = "🛡️ Выданные СИЗ"
    extra = 0
    can_delete = False
    show_change_link = True
    fields = ('siz_display', 'issue_date', 'quantity_display', 'condition', 'planned_return_display', 'status_display')
    readonly_fields = ('siz_display', 'issue_date', 'quantity_display', 'condition', 'planned_return_display', 'status_display')

    def has_add_permission(self, request, obj=None):
        return False

    def siz_display(self, obj):
        name = obj.siz.name
        if obj.siz.classification:
            name += f' ({obj.siz.classification})'
        return name
    siz_display.short_description = 'СИЗ'

    def quantity_display(self, obj):
        return f'{obj.quantity} {obj.siz.unit}'
    quantity_display.short_description = 'Кол-во'

    def planned_return_display(self, obj):
        from django.utils.html import format_html
        if obj.is_returned:
            return '—'
        if not obj.siz.wear_period:
            return 'До износа'
        planned = _add_months(obj.issue_date, obj.siz.wear_period)
        if not planned:
            return '—'
        today = _date.today()
        delta = (planned - today).days
        date_str = planned.strftime('%d.%m.%Y')
        if delta < 0:
            return format_html('<span style="color:#c0392b;font-weight:600;">⚠️ {} (просрочено {}д.)</span>', date_str, abs(delta))
        elif delta <= 30:
            return format_html('<span style="color:#856404;font-weight:600;">🔔 {} ({}д.)</span>', date_str, delta)
        return date_str
    planned_return_display.short_description = 'Плановая замена'

    def status_display(self, obj):
        from django.utils.html import format_html
        if obj.is_returned:
            return format_html('<span style="color:#999;">⚪ Возвращён</span>')
        return format_html('<span style="color:#1e7e34;font-weight:600;">🟢 Активно</span>')
    status_display.short_description = 'Статус'

    def get_queryset(self, request):
        return super().get_queryset(request).select_related('siz').order_by('is_returned', 'issue_date')


@admin.register(Employee)
class EmployeeAdmin(TreeViewMixin, admin.ModelAdmin):
    """
    👤 Админ-класс для модели Employee с оптимизированным отображением.
    Показывает только ключевые атрибуты: Ответственный по ОТ, Руководитель
    стажировки, Роль в комиссии, Статус.
    """
    form = EmployeeForm
    inlines = [SIZIssuedInline]

    change_list_template = "admin/directory/employee/change_list_tree.html"

    tree_settings = {
        'icons': {
            'organization': '🏢',
            'subdivision': '🏭',
            'department': '📂',
            'employee': '👤',
            'no_subdivision': '🏗️',
            'no_department': '📁'
        },
        'fields': {
            'name_field': 'name_with_position',
            'organization_field': 'organization',
            'subdivision_field': 'subdivision',
            'department_field': 'department'
        },
        'display_rules': {
            'hide_empty_branches': False,
            'hide_no_subdivision_no_department': False
        }
    }

    list_display = [
        'full_name_nominative',
        'organization',
        'subdivision',
        'department',
        'position',
        'contract_type',
        'status',
        'deletion_mark_display',
    ]
    # Фильтры отключены - используется компактный dropdown над деревом
    list_filter = []
    search_fields = [
        'full_name_nominative',
        'position__position_name'
    ]

    fieldsets = (
        ('Основная информация', {
            'fields': (
                'full_name_nominative',
                'full_name_by',
                'date_of_birth',
                'place_of_residence',
                'email',
                'organization',
                'subdivision',
                'department',
                'position',
                'contract_type',
                'status',
                'deletion_mark_display',
                'marked_for_deletion_at',
                'work_schedule',
                'hire_date',
                'start_date',
                'height',
                'clothing_size',
                'shoe_size',
                'is_contractor',
            )
        }),
        ('Образование', {
            'fields': (
                'education_level',
                'prior_qualification',
            ),
            'classes': ('collapse',)
        }),
    )
    readonly_fields = ('deletion_mark_display', 'marked_for_deletion_at')

    def changelist_view(self, request, extra_context=None):
        """
        Фильтрует по организации из глобального хэдера (сессия selected_org_id).
        """
        extra_context = extra_context or {}

        # Доступные организации по правам
        if request.user.is_superuser:
            accessible_orgs = Organization.objects.all()
        elif hasattr(request.user, 'profile'):
            accessible_orgs = request.user.profile.organizations.all()
        else:
            accessible_orgs = Organization.objects.none()

        # Читаем организацию из глобального хэдера (сессия)
        session_org_id = request.session.get('selected_org_id')
        selected_org_id = None
        if session_org_id and accessible_orgs.filter(id=session_org_id).exists():
            selected_org_id = session_org_id
        elif accessible_orgs.exists():
            selected_org_id = accessible_orgs.first().id
            request.session['selected_org_id'] = selected_org_id

        extra_context['selected_org_id'] = selected_org_id
        extra_context['show_tree'] = True

        # Параметры сортировки для шаблона
        sort_param = request.GET.get('sort', 'name')
        order_param = request.GET.get('order', 'asc')
        extra_context['sort'] = sort_param
        extra_context['order'] = order_param

        return super().changelist_view(request, extra_context)

    # Допустимые поля для сортировки
    SORT_FIELD_MAP = {
        'name': 'position__position_name',
        'safety': 'position__is_responsible_for_safety',
        'internship': 'position__can_be_internship_leader',
        'status': 'status',
    }

    def get_queryset(self, request):
        qs = super().get_queryset(request)

        # Фильтрация по правам доступа
        if not request.user.is_superuser and hasattr(request.user, 'profile'):
            allowed_orgs = request.user.profile.organizations.all()
            qs = qs.filter(organization__in=allowed_orgs)

        # Фильтрация по организации из глобального хэдера (сессия)
        org_id = request.session.get('selected_org_id')
        if org_id:
            qs = qs.filter(organization_id=org_id)

        # Сортировка по GET-параметрам
        sort_key = request.GET.get('sort', 'name')
        order = request.GET.get('order', 'asc')
        sort_field = self.SORT_FIELD_MAP.get(sort_key, 'full_name_nominative')
        if order == 'desc':
            sort_field = f'-{sort_field}'
        qs = qs.order_by(sort_field)

        return qs.select_related(
            'organization',
            'subdivision',
            'department',
            'position'
        ).prefetch_related(
            'commission_roles',
            'commission_roles__commission'
        )

    def get_form(self, request, obj=None, **kwargs):
        Form = super().get_form(request, obj, **kwargs)

        class FormWithUser(Form):
            def __init__(self2, *args, **inner_kwargs):
                inner_kwargs['user'] = request.user
                if not obj and not inner_kwargs.get('initial_org_id'):
                    selected_org_id = request.session.get('selected_org_id')
                    if selected_org_id:
                        try:
                            inner_kwargs['initial_org_id'] = int(selected_org_id)
                        except (ValueError, TypeError):
                            pass
                super().__init__(*args, **inner_kwargs)

        return FormWithUser

    def get_node_additional_data(self, obj):
        """
        Получает дополнительные данные для отображения в дереве.
        Сокращенная версия с фокусом на ключевых атрибутах.

        ОПТИМИЗИРОВАНО: Использует уже загруженные данные из prefetch_related
        вместо создания новых SQL-запросов для каждого сотрудника.
        """
        # Базовые данные о статусе
        additional_data = {
            'status': obj.status,
            'status_display': obj.get_status_display(),
            'status_emoji': self._get_status_emoji(obj.status),
            'marked_for_deletion': obj.marked_for_deletion,
        }

        # Атрибуты из позиции (должности)
        if obj.position:
            additional_data['is_responsible_for_safety'] = getattr(obj.position, 'is_responsible_for_safety', False)
            additional_data['can_be_internship_leader'] = getattr(obj.position, 'can_be_internship_leader', False)

        # Роли в комиссиях - ИСПОЛЬЗОВАТЬ УЖЕ ЗАГРУЖЕННЫЕ ДАННЫЕ из prefetch_related
        # Данные загружены в get_queryset() строки 134-136
        # Фильтруем на стороне Python вместо нового SQL-запроса
        commission_roles = [
            role for role in obj.commission_roles.all()
            if role.is_active
        ]

        # Для отображения в табличном виде сгруппируем роли
        additional_data['commission_roles'] = []
        for role in commission_roles:
            additional_data['commission_roles'].append({
                'commission_name': role.commission.name,
                'role': role.role,
                'role_display': role.get_role_display(),
                'role_emoji': self._get_commission_role_emoji(role.role)
            })

        return additional_data

    def _get_status_emoji(self, status):
        """Возвращает эмодзи для статуса сотрудника"""
        status_emojis = {
            'candidate': '📝',
            'active': '✅',
            'maternity_leave': '👶',
            'part_time': '💤',
            'fired': '🚫',
        }
        return status_emojis.get(status, '❓')

    @admin.display(description='Пометка удаления')
    def deletion_mark_display(self, obj):
        if obj.marked_for_deletion:
            if obj.marked_for_deletion_at:
                return format_html(
                    '<span style="color:#7a4b00;font-weight:600;">🗂 На удаление<br><small>{}</small></span>',
                    obj.marked_for_deletion_at.strftime('%d.%m.%Y %H:%M')
                )
            return format_html('<span style="color:#7a4b00;font-weight:600;">🗂 На удаление</span>')
        return '—'

    def _get_commission_role_emoji(self, role):
        """Возвращает эмодзи для роли в комиссии"""
        role_emojis = {
            'chairman': '🗳️',
            'secretary': '📝',
            'member': '👥'
        }
        return role_emojis.get(role, '❓')

    def import_view(self, request):
        """📥 Импорт сотрудников"""
        context = self.admin_site.each_context(request)

        if request.method == 'POST':
            if 'confirm' in request.POST:
                # Финальное подтверждение импорта
                dataset_data = request.session.get('employee_dataset')
                if not dataset_data:
                    messages.error(request, 'Данные для импорта не найдены. Загрузите файл заново.')
                    return redirect('admin:directory_employee_import')

                dataset = Dataset().load(dataset_data)
                resource = EmployeeResource()
                result = resource.import_data(dataset, dry_run=False)

                del request.session['employee_dataset']

                if result.has_errors():
                    # Выводим ошибки в консоль для отладки
                    print("="*80)
                    print("ОШИБКИ ИМПОРТА СОТРУДНИКОВ:")
                    print(f"Всего ошибок: {result.totals['error']}")
                    print(f"Invalid rows count: {len(result.invalid_rows)}")

                    for idx, row in enumerate(result.invalid_rows[:5]):
                        print(f"\n--- Строка {idx+1} ---")
                        print(f"Row object: {row}")
                        print(f"Row.__dict__: {row.__dict__ if hasattr(row, '__dict__') else 'N/A'}")
                        if hasattr(row, 'errors'):
                            for error in row.errors:
                                print(f"Error: {error.error}")
                                print(f"Traceback: {error.traceback}")

                    print(f"\nRow errors dict: {result.row_errors()}")
                    print("="*80)

                    messages.error(request, f'❌ Импорт завершен с ошибками! Создано: {result.totals["new"]}, ошибок: {result.totals["error"]}. Смотрите консоль сервера для деталей.')
                else:
                    messages.success(request, f'✅ Импорт завершен! Создано: {result.totals["new"]}, обновлено: {result.totals["update"]}')
                return redirect('admin:directory_employee_changelist')
            else:
                # Предпросмотр импорта
                import_file = request.FILES.get('import_file')
                if not import_file:
                    messages.error(request, 'Файл не выбран')
                    return redirect('admin:directory_employee_import')

                file_format = import_file.name.split('.')[-1].lower()
                if file_format not in ['xlsx', 'xls']:
                    messages.error(request, 'Поддерживаются только файлы XLSX и XLS')
                    return redirect('admin:directory_employee_import')

                try:
                    dataset = Dataset().load(import_file.read(), format=file_format)
                    resource = EmployeeResource()
                    result = resource.import_data(dataset, dry_run=True)

                    # Сохраняем данные в сессии для финального импорта
                    request.session['employee_dataset'] = dataset.export('json')

                    context.update({
                        'title': 'Предпросмотр импорта сотрудников',
                        'result': result,
                        'dataset': dataset,
                    })
                    return render(request, 'admin/directory/employee/import_preview.html', context)
                except Exception as e:
                    messages.error(request, f'Ошибка при обработке файла: {str(e)}')
                    return redirect('admin:directory_employee_import')

        context.update({
            'title': 'Импорт сотрудников',
            'subtitle': None,
        })
        return render(request, 'admin/directory/employee/import.html', context)

    def export_view(self, request):
        """📤 Экспорт сотрудников"""
        from directory.models import Employee

        # Фильтрация по организации (если указана)
        organization_id = request.GET.get('organization_id')

        if organization_id:
            queryset = Employee.objects.filter(organization_id=organization_id)
        else:
            queryset = Employee.objects.all()

        # Применяем права доступа
        if not request.user.is_superuser and hasattr(request.user, 'profile'):
            allowed_orgs = request.user.profile.organizations.all()
            queryset = queryset.filter(organization__in=allowed_orgs)

        queryset = queryset.select_related('organization', 'subdivision', 'department', 'position')

        resource = EmployeeResource()
        dataset = resource.export(queryset)

        response = HttpResponse(
            dataset.export('xlsx'),
            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
        response['Content-Disposition'] = 'attachment; filename="employees.xlsx"'
        return response

    # ========================================================================
    # ACTIONS
    # ========================================================================

    actions = ['action_assign_training', 'action_generate_hiring_docs', 'action_copy_employee']

    def action_generate_hiring_docs(self, request, queryset):
        """📄 Перейти к выбору документов для генерации при приёме"""
        ids = list(queryset.values_list('id', flat=True))
        if not ids:
            self.message_user(request, 'Выберите хотя бы одного сотрудника.', level=messages.WARNING)
            return
        request.session['bulk_hiring_docs_employee_ids'] = ids
        return HttpResponseRedirect(reverse('admin:directory_employee_bulk_hiring_docs'))

    action_generate_hiring_docs.short_description = '📄 Сгенерировать документы при приёме'

    def action_copy_employee(self, request, queryset):
        """📋 Открыть форму добавления нового сотрудника с данными выбранного."""
        if queryset.count() != 1:
            self.message_user(request, 'Выберите ровно одного сотрудника для копирования.', level=messages.WARNING)
            return

        employee = queryset.select_related('organization', 'subdivision', 'department', 'position').first()

        from urllib.parse import urlencode
        params = {}

        # Текстовые / выбираемые поля
        for field in ('full_name_nominative', 'full_name_by', 'place_of_residence',
                      'email', 'contract_type', 'status', 'work_schedule',
                      'height', 'clothing_size', 'shoe_size',
                      'education_level', 'prior_qualification'):
            value = getattr(employee, field, None)
            if value:
                params[field] = value

        # Дата рождения и даты трудоустройства
        for field in ('date_of_birth', 'hire_date', 'start_date'):
            value = getattr(employee, field, None)
            if value:
                params[field] = value.strftime('%d.%m.%Y')

        # FK-поля — передаём ID
        for field in ('organization', 'subdivision', 'department', 'position'):
            value = getattr(employee, f'{field}_id', None)
            if value:
                params[field] = value

        add_url = reverse('admin:directory_employee_add') + '?' + urlencode(params)
        return HttpResponseRedirect(add_url)

    action_copy_employee.short_description = '📋 Копировать сотрудника'

    def bulk_hiring_docs_view(self, request):
        """Промежуточный экран выбора документов для массовой генерации при приёме."""
        from django.shortcuts import render
        import io
        import zipfile
        from datetime import date
        from urllib.parse import quote

        from directory.models.document_template import DocumentTemplateType, DocumentGenerationLog
        from directory.document_generators.order_generator import generate_all_orders
        from directory.document_generators.protocol_generator import generate_knowledge_protocol
        from directory.document_generators.familiarization_generator import generate_familiarization_document
        from directory.document_generators.ot_card_generator import generate_personal_ot_card
        from directory.document_generators.journal_example_generator import generate_journal_example
        from directory.document_generators.vvodny_journal_generator import generate_vvodny_journal
        from directory.document_generators.siz_card_docx_generator import generate_siz_card_docx

        context = self.admin_site.each_context(request)

        employee_ids = request.session.get('bulk_hiring_docs_employee_ids', [])
        if not employee_ids:
            messages.error(request, 'Сотрудники не выбраны. Вернитесь к списку и выберите сотрудников.')
            return redirect('admin:directory_employee_changelist')

        employees = Employee.objects.filter(id__in=employee_ids).select_related(
            'organization', 'subdivision', 'department', 'position'
        ).order_by('full_name_nominative')

        doc_types = DocumentTemplateType.objects.filter(
            is_active=True, show_in_hiring=True
        ).exclude(code='periodic_protocol').order_by('name')

        if request.method == 'POST':
            selected_codes = request.POST.getlist('document_types')
            if not selected_codes:
                messages.error(request, 'Выберите хотя бы один тип документа.')
                context.update({
                    'title': 'Генерация документов при приёме',
                    'employees': employees,
                    'doc_types': doc_types,
                    'today_date': date.today().strftime('%Y-%m-%d'),
                })
                return render(request, 'admin/directory/employee/bulk_hiring_docs.html', context)

            # Параметры инструктажа для личной карточки ОТ
            override_instruction = request.POST.get('override_instruction') == 'on'
            if override_instruction:
                from datetime import datetime as dt
                instruction_date_raw = request.POST.get('instruction_date', '')
                instruction_type_override = request.POST.get('instruction_type', 'Первичный на рабочем месте')
                if instruction_date_raw:
                    try:
                        instruction_date_fixed = dt.strptime(instruction_date_raw, '%Y-%m-%d').strftime('%d.%m.%Y')
                    except ValueError:
                        instruction_date_fixed = instruction_date_raw
                else:
                    instruction_date_fixed = date.today().strftime('%d.%m.%Y')
                ot_card_custom_context = {
                    'instruction_date': instruction_date_fixed,
                    'instruction_type': instruction_type_override,
                }
            else:
                # По умолчанию: дата трудоустройства сотрудника, первичный инструктаж
                ot_card_custom_context = None  # будет заполняться per-employee ниже

            generator_map = {
                'all_orders': generate_all_orders,
                'knowledge_protocol': generate_knowledge_protocol,
                'doc_familiarization': generate_familiarization_document,
                'personal_ot_card': generate_personal_ot_card,
                'journal_example': generate_journal_example,
                'vvodny_journal_template': generate_vvodny_journal,
                'siz_card': generate_siz_card_docx,
            }
            # Документы, которые получают instruction_date (по умолчанию — hire_date сотрудника)
            JOURNAL_DOC_TYPES = {'personal_ot_card', 'journal_example', 'vvodny_journal_template'}

            zip_buffer = io.BytesIO()
            total_docs = 0
            errors = []

            with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zipf:
                for employee in employees:
                    parts = (employee.full_name_nominative or '').split()
                    folder = parts[0] if parts else f'сотрудник_{employee.pk}'

                    for doc_type in selected_codes:
                        generator_func = generator_map.get(doc_type)
                        if not generator_func:
                            continue
                        try:
                            if doc_type == 'doc_familiarization':
                                result = generator_func(employee=employee, user=request.user, document_list=None)
                            elif doc_type in JOURNAL_DOC_TYPES:
                                if override_instruction:
                                    ctx = ot_card_custom_context
                                else:
                                    hire_date_str = employee.hire_date.strftime('%d.%m.%Y') if employee.hire_date else date.today().strftime('%d.%m.%Y')
                                    ctx = {'instruction_date': hire_date_str, 'instruction_type': 'Первичный на рабочем месте'}
                                result = generator_func(employee=employee, user=request.user, custom_context=ctx)
                            else:
                                result = generator_func(employee=employee, user=request.user)
                            if not result:
                                continue
                            docs = result if isinstance(result, list) else [result]
                            for doc in docs:
                                if isinstance(doc, dict) and 'content' in doc and 'filename' in doc:
                                    zipf.writestr(f'{folder}/{doc["filename"]}', doc['content'])
                                    total_docs += 1
                        except Exception as e:
                            errors.append(f'{employee.full_name_nominative} ({doc_type}): {str(e)}')

                    try:
                        DocumentGenerationLog.objects.create(
                            employee=employee,
                            document_types=selected_codes,
                            created_by=request.user,
                        )
                    except Exception:
                        pass

            del request.session['bulk_hiring_docs_employee_ids']

            if total_docs == 0:
                messages.error(request, 'Не удалось сгенерировать ни одного документа.')
                return redirect('admin:directory_employee_changelist')

            if errors:
                messages.warning(
                    request,
                    f'⚠️ Ошибки ({len(errors)} шт.): {"; ".join(errors[:3])}{"..." if len(errors) > 3 else ""}',
                )

            zip_filename = f'Документы_при_приёме_{date.today().strftime("%Y%m%d")}.zip'
            response = HttpResponse(zip_buffer.getvalue(), content_type='application/zip')
            response['Content-Disposition'] = f"attachment; filename*=UTF-8''{quote(zip_filename)}"
            return response

        context.update({
            'title': 'Генерация документов при приёме',
            'employees': employees,
            'doc_types': doc_types,
            'today_date': date.today().strftime('%Y-%m-%d'),
        })
        return render(request, 'admin/directory/employee/bulk_hiring_docs.html', context)

    def action_assign_training(self, request, queryset):
        """
        🎓 Назначить обучение на производстве выбранным сотрудникам.

        Показывает промежуточную форму для выбора параметров обучения.
        """
        # Сохраняем выбранных сотрудников в сессии
        selected_ids = list(queryset.values_list('id', flat=True))

        if not selected_ids:
            self.message_user(request, 'Выберите хотя бы одного сотрудника', level=messages.WARNING)
            return

        # Перенаправляем на view с формой
        request.session['assign_training_employee_ids'] = selected_ids
        return HttpResponseRedirect(
            reverse('admin:directory_employee_assign_training')
        )

    action_assign_training.short_description = '🎓 Назначить обучение на производстве'

    def assign_training_view(self, request):
        """
        View для формы назначения обучения.
        """
        from production_training.forms import AssignTrainingForm
        from production_training.models import ProductionTraining, TrainingAssignment

        context = self.admin_site.each_context(request)

        # Получаем IDs сотрудников из сессии или POST
        employee_ids = request.session.get('assign_training_employee_ids', [])

        if request.method == 'POST':
            # Получаем IDs из hidden field
            ids_str = request.POST.get('employee_ids', '')
            if ids_str:
                employee_ids = [int(x) for x in ids_str.split(',') if x.isdigit()]

        if not employee_ids:
            messages.error(request, 'Сотрудники не выбраны. Вернитесь к списку и выберите сотрудников.')
            return redirect('admin:directory_employee_changelist')

        employees = Employee.objects.filter(id__in=employee_ids).select_related(
            'organization', 'subdivision', 'department', 'position'
        )

        if request.method == 'POST':
            form = AssignTrainingForm(request.POST)

            if form.is_valid():
                training_type = form.cleaned_data['training_type']
                profession = form.cleaned_data['profession']
                program = form.cleaned_data.get('program')
                qualification_grade = form.cleaned_data.get('qualification_grade')
                start_date = form.cleaned_data['start_date']
                full_name_by = form.cleaned_data.get('full_name_by')
                education_level = form.cleaned_data.get('education_level')
                prior_qualification = form.cleaned_data.get('prior_qualification')

                created_count = 0
                errors = []
                course_cache = {}

                for employee in employees:
                    try:
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
                        if update_fields:
                            employee.save(update_fields=update_fields)

                        key = (
                            employee.organization_id,
                            employee.subdivision_id,
                            employee.department_id,
                            training_type.id,
                            profession.id,
                            getattr(program, 'id', None),
                            getattr(qualification_grade, 'id', None),
                        )
                        training = course_cache.get(key)
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
                            course_cache[key] = training

                        assignment = TrainingAssignment(
                            training=training,
                            employee=employee,
                            current_position=employee.position,
                            prior_qualification=prior_qualification or employee.prior_qualification,
                            start_date=start_date,
                        )
                        assignment.save()
                        created_count += 1

                    except Exception as e:
                        errors.append(f'{employee.full_name_nominative}: {str(e)}')

                # Очищаем сессию
                if 'assign_training_employee_ids' in request.session:
                    del request.session['assign_training_employee_ids']

                if created_count > 0:
                    messages.success(
                        request,
                        f'✅ Создано {created_count} назначений на обучение'
                    )

                if errors:
                    messages.warning(
                        request,
                        f'⚠️ Ошибки при создании: {"; ".join(errors[:3])}{"..." if len(errors) > 3 else ""}'
                    )

                return redirect('admin:production_training_trainingassignment_changelist')

        else:
            form = AssignTrainingForm()

        context.update({
            'title': 'Назначить обучение на производстве',
            'form': form,
            'employees': employees,
            'employee_ids': ','.join(str(x) for x in employee_ids),
        })

        return render(request, 'admin/directory/employee/assign_training.html', context)

    def bulk_add_view(self, request):
        """📋 Массовый приём сотрудников"""
        from directory.forms.bulk_employee import BulkEmployeeAddForm
        from directory.models import StructuralSubdivision, Department, Position, EmployeeHiring
        from directory.utils.declension import decline_full_name
        from django.db import transaction

        context = self.admin_site.each_context(request)
        context['title'] = 'Массовый приём сотрудников'
        context['subtitle'] = None

        if request.method == 'POST':
            if 'confirm' in request.POST:
                # Этап 3: создание сотрудников
                session_data = request.session.get('bulk_employee_data')
                if not session_data:
                    messages.error(request, 'Данные сессии не найдены. Начните заново.')
                    return redirect('admin:directory_employee_bulk_add')

                from directory.models import Organization
                from datetime import date

                org = Organization.objects.get(id=session_data['org_id'])
                subdivision = StructuralSubdivision.objects.get(id=session_data['sub_id']) if session_data.get('sub_id') else None
                department = Department.objects.get(id=session_data['dept_id']) if session_data.get('dept_id') else None
                position = Position.objects.get(id=session_data['pos_id'])
                hire_date = date.fromisoformat(session_data['hire_date'])
                start_date = date.fromisoformat(session_data['start_date'])
                hiring_type = session_data['hiring_type']

                HIRING_TO_CONTRACT = {
                    'new': 'standard',
                    'transfer': 'transfer',
                    'return': 'return',
                    'contractor': 'contractor',
                    'part_time': 'part_time',
                }
                contract_type = HIRING_TO_CONTRACT.get(hiring_type, 'standard')

                created_count = 0
                error_list = []

                with transaction.atomic():
                    for name_data in session_data['names']:
                        try:
                            employee = Employee(
                                full_name_nominative=name_data['nominative'],
                                organization=org,
                                subdivision=subdivision,
                                department=department,
                                position=position,
                                hire_date=hire_date,
                                start_date=start_date,
                                contract_type=contract_type,
                                status='active',
                            )
                            employee.save()
                            EmployeeHiring.objects.create(
                                employee=employee,
                                hiring_date=hire_date,
                                start_date=start_date,
                                hiring_type=hiring_type,
                                organization=org,
                                subdivision=subdivision,
                                department=department,
                                position=position,
                                created_by=request.user,
                            )
                            created_count += 1
                        except Exception as e:
                            error_list.append(f'{name_data["nominative"]}: {str(e)}')

                del request.session['bulk_employee_data']

                if error_list:
                    messages.warning(
                        request,
                        f'Создано {created_count} сотрудников. '
                        f'Ошибки ({len(error_list)}): {"; ".join(error_list[:3])}'
                        f'{"..." if len(error_list) > 3 else ""}'
                    )
                else:
                    messages.success(request, f'✅ Успешно создано {created_count} сотрудников.')
                return redirect('admin:directory_employee_changelist')

            else:
                # Этап 2: предпросмотр
                form = BulkEmployeeAddForm(request.POST, user=request.user)
                if form.is_valid():
                    cd = form.cleaned_data
                    organization = cd['organization']

                    # Парсим список ФИО: убираем пустые строки и дубли
                    raw_names = cd['names_text'].splitlines()
                    names = []
                    seen = set()
                    for raw in raw_names:
                        name = raw.strip()
                        if name and name not in seen:
                            seen.add(name)
                            names.append(name)

                    # Пропускаем только тех, у кого совпадает ФИО + организация + должность
                    existing_names = set(
                        Employee.objects.filter(
                            organization=organization,
                            position=cd['position'],
                            full_name_nominative__in=names
                        ).values_list('full_name_nominative', flat=True)
                    )

                    to_create = []
                    to_skip = []
                    for name in names:
                        if name in existing_names:
                            to_skip.append(name)
                        else:
                            dative = decline_full_name(name, 'datv')
                            to_create.append({'nominative': name, 'dative': dative})

                    if not to_create:
                        messages.warning(
                            request,
                            'Все введённые сотрудники уже существуют в этой организации.'
                        )
                        context['form'] = form
                        return render(request, 'admin/directory/employee/bulk_add.html', context)

                    # Сохраняем параметры в сессию для подтверждения
                    sub = cd.get('subdivision')
                    dept = cd.get('department')
                    request.session['bulk_employee_data'] = {
                        'org_id': organization.id,
                        'sub_id': sub.id if sub else None,
                        'dept_id': dept.id if dept else None,
                        'pos_id': cd['position'].id,
                        'hire_date': cd['hire_date'].isoformat(),
                        'start_date': cd['start_date'].isoformat(),
                        'hiring_type': cd['hiring_type'],
                        'names': to_create,
                        'skipped': to_skip,
                    }

                    context.update({
                        'title': 'Предпросмотр: массовый приём сотрудников',
                        'to_create': to_create,
                        'to_skip': to_skip,
                        'organization': organization,
                        'subdivision': cd.get('subdivision'),
                        'department': cd.get('department'),
                        'position': cd['position'],
                        'hire_date': cd['hire_date'],
                        'start_date': cd['start_date'],
                        'hiring_type_display': dict(EmployeeHiring.HIRING_TYPE_CHOICES).get(
                            cd['hiring_type'], cd['hiring_type']
                        ),
                    })
                    return render(request, 'admin/directory/employee/bulk_add_preview.html', context)

        else:
            # Этап 1: показать форму
            initial = {}
            session_org_id = request.session.get('selected_org_id')
            if session_org_id:
                initial['organization'] = session_org_id
            form = BulkEmployeeAddForm(user=request.user, initial=initial)

        context['form'] = form
        return render(request, 'admin/directory/employee/bulk_add.html', context)

    def bulk_add_ajax_subdivisions(self, request):
        """AJAX: список подразделений для организации"""
        from django.http import JsonResponse
        from directory.models import StructuralSubdivision
        org_id = request.GET.get('org_id')
        if not org_id:
            return JsonResponse([], safe=False)
        qs = StructuralSubdivision.objects.filter(organization_id=org_id).order_by('name')
        return JsonResponse([{'id': s.id, 'name': s.name} for s in qs], safe=False)

    def bulk_add_ajax_departments(self, request):
        """AJAX: список отделов для подразделения"""
        from django.http import JsonResponse
        from directory.models import Department
        sub_id = request.GET.get('sub_id')
        if not sub_id:
            return JsonResponse([], safe=False)
        qs = Department.objects.filter(subdivision_id=sub_id).order_by('name')
        return JsonResponse([{'id': d.id, 'name': d.name} for d in qs], safe=False)

    def bulk_add_ajax_positions(self, request):
        """AJAX: список должностей с фильтрацией по иерархии"""
        from django.http import JsonResponse
        from django.db.models import Q
        from directory.models import Position
        org_id = request.GET.get('org_id')
        sub_id = request.GET.get('sub_id')
        dept_id = request.GET.get('dept_id')
        if not org_id:
            return JsonResponse([], safe=False)
        qs = Position.objects.filter(organization_id=org_id).order_by('position_name')
        if sub_id:
            qs = qs.filter(Q(subdivision_id=sub_id) | Q(subdivision__isnull=True))
        if dept_id:
            qs = qs.filter(Q(department_id=dept_id) | Q(department__isnull=True))
        return JsonResponse([{'id': p.id, 'name': p.position_name} for p in qs], safe=False)

    def restore_view(self, request, pk):
        """↩️ Восстановить сотрудника — снять пометку на удаление."""
        employee = Employee.objects.get(pk=pk)
        if employee.restore():
            messages.success(request, f'↩️ Сотрудник {employee.full_name_nominative} восстановлен.')
        else:
            messages.info(request, f'Сотрудник {employee.full_name_nominative} не был помеч��н на удаление.')
        return redirect('admin:directory_employee_changelist')

    def get_urls(self):
        """🔗 Добавляем кастомные URL для импорта/экспорта и назначения обучения"""
        urls = super().get_urls()
        custom_urls = [
            path('import/', self.admin_site.admin_view(self.import_view), name='directory_employee_import'),
            path('export/', self.admin_site.admin_view(self.export_view), name='directory_employee_export'),
            path('assign-training/', self.admin_site.admin_view(self.assign_training_view), name='directory_employee_assign_training'),
            path('bulk-add/', self.admin_site.admin_view(self.bulk_add_view), name='directory_employee_bulk_add'),
            path('bulk-hiring-docs/', self.admin_site.admin_view(self.bulk_hiring_docs_view), name='directory_employee_bulk_hiring_docs'),
            path('bulk-add/ajax/subdivisions/', self.admin_site.admin_view(self.bulk_add_ajax_subdivisions), name='directory_employee_bulk_add_subdivisions'),
            path('bulk-add/ajax/departments/', self.admin_site.admin_view(self.bulk_add_ajax_departments), name='directory_employee_bulk_add_departments'),
            path('bulk-add/ajax/positions/', self.admin_site.admin_view(self.bulk_add_ajax_positions), name='directory_employee_bulk_add_positions'),
            path('<int:pk>/restore/', self.admin_site.admin_view(self.restore_view), name='directory_employee_restore'),
        ]
        return custom_urls + urls
