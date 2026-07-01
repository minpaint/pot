from django.views import View
from django.views.generic import ListView, CreateView, UpdateView, DeleteView, FormView, DetailView
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.decorators import login_required
from django.urls import reverse_lazy, reverse
from django.http import JsonResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.views.decorators.http import require_GET
from django.template.loader import render_to_string
from django.contrib import messages
from django.utils.translation import gettext_lazy as _
from django.utils import timezone
from django.db.models import Q

from directory.models import Employee, StructuralSubdivision, Position, Organization, Department
from directory.forms import EmployeeForm
from directory.forms.employee_hiring import EmployeeHiringForm
from directory.utils.declension import decline_full_name
from directory.mixins import AccessControlMixin, AccessControlObjectMixin
from directory.utils.permissions import AccessControlHelper


class EmployeeListView(LoginRequiredMixin, AccessControlMixin, ListView):
    model = Employee
    template_name = 'directory/employees/list.html'
    context_object_name = 'employees'
    paginate_by = 20

    def get_queryset(self):
        # AccessControlMixin автоматически фильтрует по правам доступа
        queryset = super().get_queryset().visible()

        # Фильтр по выбранной организации из глобального селектора
        selected_org_id = self.request.session.get('selected_org_id')
        if selected_org_id:
            queryset = queryset.filter(organization_id=selected_org_id)

        # Фильтрация по подразделению
        subdivision = self.request.GET.get('subdivision')
        if subdivision:
            queryset = queryset.filter(subdivision_id=subdivision)

        # Фильтрация по должности
        position = self.request.GET.get('position')
        if position:
            queryset = queryset.filter(position_id=position)

        # Поиск по имени
        search = self.request.GET.get('search')
        if search:
            queryset = queryset.filter(full_name_nominative__icontains=search)

        return queryset.select_related('position', 'subdivision', 'organization', 'department')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['title'] = 'Сотрудники'

        # Используем AccessControlHelper для получения доступных подразделений и должностей
        context['subdivisions'] = AccessControlHelper.get_accessible_subdivisions(
            self.request.user, self.request
        )
        # Для должностей используем фильтр по доступным организациям
        accessible_orgs = AccessControlHelper.get_accessible_organizations(
            self.request.user, self.request
        )
        context['positions'] = Position.objects.filter(organization__in=accessible_orgs)

        return context


class EmployeeTreeView(LoginRequiredMixin, AccessControlMixin, ListView):
    """
    🌳 Древовидное представление сотрудников по организационной структуре
    ОПТИМИЗИРОВАНО для работы с 3000+ сотрудниками
    """
    model = Employee
    template_name = 'directory/employees/tree_view.html'
    context_object_name = 'employees'

    def get_queryset(self):
        # AccessControlMixin автоматически фильтрует по правам доступа
        queryset = super().get_queryset().visible()

        # Фильтр по выбранной организации из глобального селектора
        selected_org_id = self.request.session.get('selected_org_id')
        if selected_org_id:
            queryset = queryset.filter(organization_id=selected_org_id)

        # 🚀 ДЕФОЛТНЫЙ ФИЛЬТР: показываем только активных сотрудников
        # (исключаем кандидатов и уволенных для ускорения загрузки)
        if not self.request.GET.get('status'):
            queryset = queryset.tree_visible()  # Использует метод из EmployeeQuerySet

        # Фильтрация по должности
        position = self.request.GET.get('position')
        if position:
            queryset = queryset.filter(position_id=position)

        # Поиск по имени
        search = self.request.GET.get('search')
        if search:
            queryset = queryset.filter(full_name_nominative__icontains=search)

        # 🚀 ОПТИМИЗАЦИЯ: загружаем все связанные объекты одним запросом
        return queryset.select_related('position', 'subdivision', 'organization', 'department')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['title'] = 'Сотрудники'

        # Используем AccessControlHelper для получения доступных организаций, подразделений и отделов
        allowed_orgs = AccessControlHelper.get_accessible_organizations(
            self.request.user, self.request
        )
        allowed_subdivisions = AccessControlHelper.get_accessible_subdivisions(
            self.request.user, self.request
        )
        allowed_departments = AccessControlHelper.get_accessible_departments(
            self.request.user, self.request
        )

        # 🚀 ОПТИМИЗАЦИЯ: получаем всех сотрудников ОДНИМ запросом
        # Используем уже оптимизированный queryset из get_queryset()
        all_employees = list(self.get_queryset())

        # 🚀 ОПТИМИЗАЦИЯ: группируем сотрудников по ключам в памяти (быстрее, чем N запросов к БД)
        from collections import defaultdict

        # Группируем сотрудников по (org_id, sub_id, dept_id)
        employees_by_org = defaultdict(list)
        employees_by_sub = defaultdict(list)
        employees_by_dept = defaultdict(list)

        for emp in all_employees:
            org_id = emp.organization_id
            sub_id = emp.subdivision_id
            dept_id = emp.department_id

            if sub_id is None and dept_id is None:
                # Сотрудник на уровне организации
                employees_by_org[org_id].append(emp)
            elif dept_id is None:
                # Сотрудник на уровне подразделения (без отдела)
                employees_by_sub[(org_id, sub_id)].append(emp)
            else:
                # Сотрудник в отделе
                employees_by_dept[(org_id, sub_id, dept_id)].append(emp)

        # Создаем древовидную структуру данных
        tree_data = []

        for org in allowed_orgs:
            org_employees = employees_by_org.get(org.id, [])

            org_data = {
                'id': org.id,
                'name': org.short_name_ru or org.full_name_ru,
                'employees': org_employees,
                'subdivisions': []
            }

            # Получаем только доступные подразделения этой организации
            org_subdivisions = org.subdivisions.filter(id__in=allowed_subdivisions)

            for subdivision in org_subdivisions:
                sub_employees = employees_by_sub.get((org.id, subdivision.id), [])

                sub_data = {
                    'id': subdivision.id,
                    'name': subdivision.name,
                    'employees': sub_employees,
                    'departments': []
                }

                # Получаем только доступные отделы этого подразделения
                sub_departments = subdivision.departments.filter(id__in=allowed_departments)

                for department in sub_departments:
                    dept_employees = employees_by_dept.get((org.id, subdivision.id, department.id), [])

                    if dept_employees:
                        dept_data = {
                            'id': department.id,
                            'name': department.name,
                            'employees': dept_employees
                        }
                        sub_data['departments'].append(dept_data)

                # Добавляем подразделение только если есть сотрудники или отделы
                if sub_employees or sub_data['departments']:
                    org_data['subdivisions'].append(sub_data)

            # Добавляем организацию только если есть сотрудники или подразделения
            if org_employees or org_data['subdivisions']:
                tree_data.append(org_data)

        context['tree_data'] = tree_data

        # Фильтры - используем доступные организации
        context['positions'] = Position.objects.filter(organization__in=allowed_orgs)

        # Параметры фильтрации
        context['current_position'] = self.request.GET.get('position', '')
        context['search_query'] = self.request.GET.get('search', '')

        return context


class EmployeeCreateView(LoginRequiredMixin, CreateView):
    model = Employee
    form_class = EmployeeForm
    template_name = 'directory/employees/form.html'

    def get_success_url(self):
        return reverse('directory:employees:employee_profile', kwargs={'pk': self.object.pk})

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


@login_required
@require_GET
def employee_tree_children(request, parent_type, parent_id):
    """
    AJAX endpoint для подгрузки дочерних узлов дерева сотрудников.
    """
    employees_qs = Employee.objects.visible()
    employees_qs = AccessControlHelper.filter_queryset(employees_qs, request.user, request)

    if not request.GET.get('status'):
        employees_qs = employees_qs.tree_visible()

    position_id = request.GET.get('position')
    if position_id:
        employees_qs = employees_qs.filter(position_id=position_id)

    search = request.GET.get('search')
    if search:
        employees_qs = employees_qs.filter(full_name_nominative__icontains=search)

    subdivisions = StructuralSubdivision.objects.none()
    departments = Department.objects.none()
    employees = Employee.objects.none()

    allowed_subdivisions = AccessControlHelper.get_accessible_subdivisions(
        request.user, request
    )
    allowed_departments = AccessControlHelper.get_accessible_departments(
        request.user, request
    )

    if parent_type == 'org':
        employees = employees_qs.filter(
            organization_id=parent_id,
            subdivision__isnull=True,
            department__isnull=True
        )
        subdivisions = allowed_subdivisions.filter(organization_id=parent_id)
        departments = allowed_departments.filter(
            organization_id=parent_id,
            subdivision__isnull=True
        )
    elif parent_type == 'sub':
        employees = employees_qs.filter(
            subdivision_id=parent_id,
            department__isnull=True
        )
        departments = allowed_departments.filter(subdivision_id=parent_id)
    elif parent_type == 'dept':
        employees = employees_qs.filter(department_id=parent_id)
    else:
        return JsonResponse({'success': False, 'html': 'Неверный тип узла.'}, status=400)

    html = render_to_string(
        'directory/employees/_tree_children.html',
        {
            'employees': employees.select_related('position'),
            'subdivisions': subdivisions,
            'departments': departments,
        },
        request=request
    )

    return JsonResponse({'success': True, 'html': html})
    template_name = 'directory/employees/form.html'
    success_url = reverse_lazy('directory:employees:employee_list')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['title'] = 'Добавление сотрудника'
        return context


class EmployeeUpdateView(LoginRequiredMixin, AccessControlObjectMixin, UpdateView):
    model = Employee
    form_class = EmployeeForm
    template_name = 'directory/employees/form.html'

    def get_queryset(self):
        return Employee.objects.visible()

    def get_success_url(self):
        """Перенаправляем на профиль сотрудника после обновления"""
        return reverse('directory:employees:employee_profile', kwargs={'pk': self.object.pk})

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['title'] = 'Редактирование сотрудника'
        return context


class EmployeeDeleteView(LoginRequiredMixin, AccessControlObjectMixin, DeleteView):
    model = Employee
    template_name = 'directory/employees/confirm_delete.html'
    success_url = reverse_lazy('directory:employees:employee_list')

    def get_queryset(self):
        return Employee.objects.visible()

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['title'] = 'Удаление сотрудника'
        return context

    def post(self, request, *args, **kwargs):
        self.object = self.get_object()
        if self.object.mark_for_deletion():
            messages.success(
                request,
                f'Сотрудник {self.object.full_name_nominative} помечен на удаление и скрыт из рабочих разделов.'
            )
        else:
            messages.info(request, f'Сотрудник {self.object.full_name_nominative} уже помечен на удаление.')
        return redirect(self.get_success_url())


class BatchFireEmployeesView(LoginRequiredMixin, View):
    """Пакетное увольнение сотрудников. POST: employee_ids[] → JSON-ответ."""

    def post(self, request):
        employee_ids = request.POST.getlist('employee_ids')
        if not employee_ids:
            return JsonResponse({'success': False, 'error': 'Не выбраны сотрудники'}, status=400)

        employees = list(
            Employee.objects.visible()
            .filter(id__in=employee_ids)
        )
        employees = [e for e in employees if AccessControlHelper.can_access_object(request.user, e)]

        if not employees:
            return JsonResponse({'success': False, 'error': 'Нет доступных сотрудников'}, status=403)

        fired, already = [], []
        for emp in employees:
            if emp.mark_for_deletion():
                fired.append(emp.full_name_nominative)
            else:
                already.append(emp.full_name_nominative)

        return JsonResponse({'success': True, 'fired': fired, 'already': already})


class EmployeeProfileView(LoginRequiredMixin, AccessControlObjectMixin, DetailView):
    """
    👤 Представление для просмотра профиля сотрудника с возможностью
    выполнения дополнительных действий
    """
    model = Employee
    template_name = 'directory/employees/profile.html'
    context_object_name = 'employee'

    def get_queryset(self):
        return Employee.objects.visible()

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['title'] = f'Профиль сотрудника: {self.object.full_name_nominative}'

        # Проверяем, новый ли это сотрудник (для показа уведомления)
        context['is_new_employee'] = self.request.GET.get('new', False)

        # Проверяем, есть ли у сотрудника СИЗ
        if hasattr(self.object, 'position') and self.object.position:
            from directory.models.siz import SIZNorm
            context['has_siz_norms'] = SIZNorm.objects.filter(
                position=self.object.position
            ).exists()

        # Проверяем, есть ли у сотрудника выданные СИЗ
        context['has_issued_siz'] = hasattr(self.object, 'issued_siz') and self.object.issued_siz.exists()

        return context


class EmployeeHiringView(LoginRequiredMixin, FormView):
    """
    👥 Представление для страницы найма сотрудника

    Отображает единую форму найма сотрудника с сохранением логики
    ограничения по организациям из профиля пользователя.
    """
    template_name = 'directory/employees/hire.html'
    form_class = EmployeeHiringForm

    def get_form_kwargs(self):
        """
        🔑 Передаем текущего пользователя в форму
        для ограничения доступных организаций
        """
        kwargs = super().get_form_kwargs()
        kwargs['user'] = self.request.user
        return kwargs

    def get_context_data(self, **kwargs):
        """
        📊 Добавляем контекст для шаблона
        """
        context = super().get_context_data(**kwargs)
        context['title'] = '📝 Прием на работу'
        context['current_date'] = timezone.now().date()

        # Получаем недавно принятых сотрудников через AccessControlHelper
        accessible_orgs = AccessControlHelper.get_accessible_organizations(
            self.request.user, self.request
        )

        # Фильтруем сотрудников по доступным организациям
        recent_employees_query = Employee.objects.filter(
            organization__in=accessible_orgs
        ).visible().order_by('-id')[:5]

        context['recent_employees'] = recent_employees_query
        # Добавляем типы договоров для отображения в шаблоне
        context['contract_types'] = Employee.CONTRACT_TYPE_CHOICES

        return context

    def form_valid(self, form):
        """
        ✅ Обработка валидной формы с сохранением или предпросмотром
        """
        # Проверяем, нужен ли предпросмотр
        if 'preview' in self.request.POST:
            # Отображаем страницу предпросмотра с данными из формы
            return render(self.request, 'directory/preview.html', {
                'form': form,
                'data': form.cleaned_data
            })

        # Получаем данные из формы
        employee_data = form.cleaned_data

        # Сохраняем данные формы
        employee = form.save()

        # Добавляем сообщение об успешном найме
        messages.success(
            self.request,
            f"✅ Сотрудник {employee.full_name_nominative} успешно принят на работу"
        )

        # Перенаправляем на профиль сотрудника с указанием, что он новый
        return redirect(
            reverse('directory:employees:employee_profile', kwargs={'pk': employee.pk}) + '?new=true'
        )


def get_subdivisions(request):
    """AJAX представление для получения подразделений по организации"""
    organization_id = request.GET.get('organization')
    subdivisions = StructuralSubdivision.objects.filter(
        organization_id=organization_id
    ).values('id', 'name')
    return JsonResponse(list(subdivisions), safe=False)


def get_positions(request):
    """AJAX представление для получения должностей по подразделению"""
    subdivision_id = request.GET.get('subdivision')
    positions = Position.objects.filter(
        subdivision_id=subdivision_id
    ).values('id', 'position_name')  # Изменено с name на position_name
    return JsonResponse(list(positions), safe=False)


@require_GET
@login_required
def employee_info_api(request, employee_id):
    """
    🔍 API для получения детальной информации о сотруднике
    Используется во вкладке "По сотруднику" на странице карточек СИЗ
    """
    employee = get_object_or_404(Employee.objects.visible(), pk=employee_id)

    # Проверка прав доступа
    if not AccessControlHelper.can_access_object(request.user, employee):
        return JsonResponse({'error': 'Нет доступа к этому сотруднику'}, status=403)

    # Формируем ответ
    data = {
        'id': employee.id,
        'full_name_nominative': employee.full_name_nominative,
        'position_name': employee.position.position_name if employee.position else None,
        'subdivision_name': employee.position.department.subdivision.name if (
            employee.position and
            employee.position.department and
            employee.position.department.subdivision
        ) else None,
        'organization_name': employee.organization.short_name_ru if employee.organization else None,
    }

    return JsonResponse(data)
