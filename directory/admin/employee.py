# directory/admin/employee.py
from django.contrib import admin
from django.contrib import messages
from django.shortcuts import redirect, render
from django.urls import path, reverse
from django.http import HttpResponse, HttpResponseRedirect
from tablib import Dataset

from directory.models import Employee, Organization
from directory.models.commission import CommissionMember
from directory.forms.employee import EmployeeForm
from directory.admin.mixins.tree_view import TreeViewMixin
from directory.resources.employee import EmployeeResource


@admin.register(Employee)
class EmployeeAdmin(TreeViewMixin, admin.ModelAdmin):
    """
    👤 Админ-класс для модели Employee с оптимизированным отображением.
    Показывает только ключевые атрибуты: Ответственный по ОТ, Руководитель 
    стажировки, Роль в комиссии, Статус.
    """
    form = EmployeeForm

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
                'qualification_document_number',
                'qualification_document_date',
            ),
            'classes': ('collapse',)
        }),
    )

    def changelist_view(self, request, extra_context=None):
        """
        Используем стандартный list_filter (organization__id__exact).
        Если фильтр не задан, автоподставляем первую доступную организацию для ограничения дерева.
        """
        extra_context = extra_context or {}

        # Доступные организации по правам
        if request.user.is_superuser:
            accessible_orgs = Organization.objects.all()
        elif hasattr(request.user, 'profile'):
            accessible_orgs = request.user.profile.organizations.all()
        else:
            accessible_orgs = Organization.objects.none()

        org_param = request.GET.get('organization__id__exact')
        selected_org_id = None
        if org_param and org_param.isdigit():
            org_id = int(org_param)
            if accessible_orgs.filter(id=org_id).exists():
                selected_org_id = org_id

        # Если фильтр не задан — автоподставляем первую доступную и редиректим
        if selected_org_id is None and accessible_orgs.exists():
            first_id = accessible_orgs.first().id
            params = request.GET.copy()
            params['organization__id__exact'] = str(first_id)
            url = f"{request.path}?{params.urlencode()}"
            return HttpResponseRedirect(url)

        # Передаем список всех доступных организаций для dropdown фильтра
        from django.db.models import Count
        org_options = accessible_orgs.annotate(
            employee_count=Count('employees')
        ).order_by('-employee_count')

        extra_context['org_options'] = org_options
        extra_context['selected_org_id'] = selected_org_id
        extra_context['show_tree'] = True

        return super().changelist_view(request, extra_context)

    def get_queryset(self, request):
        qs = super().get_queryset(request)

        # Фильтрация по правам доступа
        if not request.user.is_superuser and hasattr(request.user, 'profile'):
            allowed_orgs = request.user.profile.organizations.all()
            qs = qs.filter(organization__in=allowed_orgs)

        # Фильтрация по выбранной организации из dropdown
        org_param = request.GET.get('organization__id__exact')
        if org_param and org_param.isdigit():
            qs = qs.filter(organization_id=int(org_param))

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
            'part_time': '⌛',
            'fired': '🚫',
        }
        return status_emojis.get(status, '❓')

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

    actions = ['action_assign_training']

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
        from production_training.models import ProductionTraining

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
                qualification_document_number = form.cleaned_data.get('qualification_document_number')
                qualification_document_date = form.cleaned_data.get('qualification_document_date')

                created_count = 0
                errors = []

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
                        if qualification_document_number:
                            employee.qualification_document_number = qualification_document_number
                            update_fields.append('qualification_document_number')
                        if qualification_document_date:
                            employee.qualification_document_date = qualification_document_date
                            update_fields.append('qualification_document_date')
                        if update_fields:
                            employee.save(update_fields=update_fields)

                        # Создаём карточку обучения для каждого сотрудника
                        training = ProductionTraining(
                            organization=employee.organization,
                            employee=employee,
                            subdivision=employee.subdivision,
                            department=employee.department,
                            current_position=employee.position,
                            training_type=training_type,
                            profession=profession,
                            program=program,
                            qualification_grade=qualification_grade,
                            start_date=start_date,
                            status='draft',
                        )

                        # Подставляем эталонные роли из организации
                        if employee.organization:
                            org = employee.organization
                            if hasattr(org, 'default_theory_consultant') and org.default_theory_consultant:
                                training.theory_consultant = org.default_theory_consultant
                            if hasattr(org, 'default_commission_chairman') and org.default_commission_chairman:
                                training.commission_chairman = org.default_commission_chairman
                            if hasattr(org, 'default_instructor') and org.default_instructor:
                                training.instructor = org.default_instructor

                        # save() автоматически рассчитает все даты
                        training.save()
                        created_count += 1

                    except Exception as e:
                        errors.append(f'{employee.full_name_nominative}: {str(e)}')

                # Очищаем сессию
                if 'assign_training_employee_ids' in request.session:
                    del request.session['assign_training_employee_ids']

                if created_count > 0:
                    messages.success(
                        request,
                        f'✅ Создано {created_count} карточек обучения'
                    )

                if errors:
                    messages.warning(
                        request,
                        f'⚠️ Ошибки при создании: {"; ".join(errors[:3])}{"..." if len(errors) > 3 else ""}'
                    )

                return redirect('admin:production_training_productiontraining_changelist')

        else:
            form = AssignTrainingForm()

        context.update({
            'title': 'Назначить обучение на производстве',
            'form': form,
            'employees': employees,
            'employee_ids': ','.join(str(x) for x in employee_ids),
        })

        return render(request, 'admin/directory/employee/assign_training.html', context)

    def get_urls(self):
        """🔗 Добавляем кастомные URL для импорта/экспорта и назначения обучения"""
        urls = super().get_urls()
        custom_urls = [
            path('import/', self.admin_site.admin_view(self.import_view), name='directory_employee_import'),
            path('export/', self.admin_site.admin_view(self.export_view), name='directory_employee_export'),
            path('assign-training/', self.admin_site.admin_view(self.assign_training_view), name='directory_employee_assign_training'),
        ]
        return custom_urls + urls
