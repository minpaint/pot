from django.views.generic import TemplateView
from django.views import View
from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import render, redirect
from django.http import HttpResponseRedirect
from django.contrib import messages
from django.db.models import Prefetch, Q
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from django.utils import timezone
from datetime import timedelta
from urllib.parse import urlparse
import logging

from directory.models import (
    Organization,
    StructuralSubdivision,
    Department,
    Employee,
    Position
)
from directory.utils.permissions import AccessControlHelper

logger = logging.getLogger(__name__)


class HomePageView(LoginRequiredMixin, TemplateView):
    """
    🏠 Главная страница с древовидным списком сотрудников

    Отображает иерархическую структуру организаций, подразделений,
    отделов и сотрудников с возможностью выбора через чекбоксы.
    """
    template_name = 'directory/home.html'

    def get_context_data(self, **kwargs):
        """📊 Получение данных для шаблона"""
        context = super().get_context_data(**kwargs)
        context['title'] = '🏠 Главная'

        # 🔍 Получаем доступные организации пользователя
        user = self.request.user

        # Если суперпользователь — показываем все организации; иначе по правам доступа
        if user.is_superuser:
            accessible_orgs = Organization.objects.all()
        else:
            # ВАЖНО: Очищаем кеш перед получением организаций, чтобы избежать проблем с устаревшими данными
            if hasattr(self.request, '_user_orgs_cache'):
                delattr(self.request, '_user_orgs_cache')
            accessible_orgs = AccessControlHelper.get_accessible_organizations(user, self.request)

        # 📋 Определяем выбранную организацию из GET-параметра
        org_id_param = self.request.GET.get('org', '')
        selected_org_id = None

        if org_id_param:
            try:
                org_id = int(org_id_param)
                # Проверка доступа к организации
                if accessible_orgs.filter(id=org_id).exists():
                    selected_org_id = org_id
                    logger.info(f"User {user.username} viewing org_id={selected_org_id}")
            except (ValueError, TypeError):
                pass  # Игнорируем невалидный параметр

        # 🎯 Автоподстановка при единственной доступной организации
        if selected_org_id is None and accessible_orgs.count() == 1:
            selected_org_id = accessible_orgs.first().id
            logger.info(f"User {user.username} auto-selected org_id={selected_org_id}")

        # 💾 Сохранить выбор в сессии для UX
        try:
            if selected_org_id:
                self.request.session['selected_org_id'] = selected_org_id
            elif hasattr(self.request, 'session') and 'selected_org_id' in self.request.session:
                # Попытка восстановить последний выбор
                last_org_id = self.request.session.get('selected_org_id')
                if accessible_orgs.filter(id=last_org_id).exists():
                    selected_org_id = last_org_id
                    logger.info(f"User {user.username} restored org_id={selected_org_id} from session")
        except Exception as e:
            # Если сессия недоступна, просто продолжаем без восстановления
            logger.warning(f"Session not available: {e}")

        # 📊 Добавляем данные о выборе организации в контекст
        context['org_options'] = accessible_orgs
        context['selected_org_id'] = selected_org_id
        context['show_tree'] = selected_org_id is not None

        # 🚫 Если организация не выбрана, не строим дерево
        if not context['show_tree']:
            context['organizations'] = []
            context['candidate_employees'] = Employee.objects.none()
            context['statuses'] = Employee.EMPLOYEE_STATUS_CHOICES
            context['selected_status'] = ''
            context['show_fired'] = False
            context['is_paginated'] = False
            return context

        # ✅ Фильтруем организации по выбранной
        allowed_orgs = accessible_orgs.filter(id=selected_org_id)

        # 🔍 Добавляем поддержку поиска сотрудников
        search_query = self.request.GET.get('search', '')
        selected_status = self.request.GET.get('status', '')
        show_fired = self.request.GET.get('show_fired') == 'true'

        # 👤 Получаем список кандидатов для отдельного блока (только из выбранной организации)
        candidate_employees = Employee.objects.filter(
            status='candidate',
            organization_id=selected_org_id
        ).select_related('position')

        # Если есть поиск, применяем его и к кандидатам
        if search_query:
            candidate_employees = candidate_employees.filter(
                Q(full_name_nominative__icontains=search_query) |
                Q(position__position_name__icontains=search_query)
            )

        # Добавляем кандидатов в контекст
        context['candidate_employees'] = candidate_employees
        context['statuses'] = Employee.EMPLOYEE_STATUS_CHOICES
        context['selected_status'] = selected_status
        context['show_fired'] = show_fired

        if search_query:
            # Для поиска сначала получаем все организации
            all_organizations = allowed_orgs

            # Фильтруем сотрудников по поисковому запросу
            # Исключаем кандидатов и уволенных (если show_fired не включено)
            employee_filter = Q(full_name_nominative__icontains=search_query) | Q(
                position__position_name__icontains=search_query)
            status_filter = ~Q(status='candidate')
            if not show_fired:
                status_filter &= ~Q(status='fired')

            # Статус фильтр из UI
            if selected_status:
                status_filter &= Q(status=selected_status)

            filtered_employees = Employee.objects.filter(status_filter & employee_filter).select_related(
                'organization', 'subdivision', 'department', 'position'
            )

            # Собираем ID организаций, подразделений и отделов с найденными сотрудниками
            org_ids = set(filtered_employees.values_list('organization_id', flat=True))
            sub_ids = set(e.subdivision_id for e in filtered_employees if e.subdivision_id)
            dept_ids = set(e.department_id for e in filtered_employees if e.department_id)

            # Формируем список организаций только с найденными сотрудниками
            allowed_orgs = allowed_orgs.filter(id__in=org_ids)

            # Сохраняем поисковый запрос и результаты поиска для шаблона
            context['search_query'] = search_query
            context['search_results'] = True
            context['filtered_employees'] = filtered_employees
            context['total_found'] = filtered_employees.count()

        # 📝 Подготавливаем данные для древовидной структуры
        organizations = []

        # 📊 Для каждой организации получаем древовидную структуру
        for org in allowed_orgs:
            # 📋 Получаем подразделения организации
            subdivisions = StructuralSubdivision.objects.filter(
                organization=org
            ).prefetch_related(
                Prefetch(
                    'departments',
                    queryset=Department.objects.all()
                )
            )

            # 👥 Получаем сотрудников без подразделения (напрямую в организации),
            # исключая кандидатов и уволенных (если show_fired не включено)
            org_employees_filter = Q(organization=org, subdivision__isnull=True) & ~Q(status='candidate')
            if not show_fired:
                org_employees_filter &= ~Q(status='fired')

            if selected_status:
                org_employees_filter &= Q(status=selected_status)

            org_employees = Employee.objects.filter(org_employees_filter).select_related('position')

            # Если есть поисковый запрос, фильтруем сотрудников
            if search_query:
                org_employees = org_employees.filter(
                    Q(full_name_nominative__icontains=search_query) |
                    Q(position__position_name__icontains=search_query)
                )

            # 🏢 Формируем структуру организации
            org_data = {
                'id': org.id,
                'name': org.full_name_ru,
                'short_name': org.short_name_ru,
                'employees': list(org_employees),
                'subdivisions': []
            }

            # 🏭 Для каждого подразделения получаем отделы и сотрудников
            for subdivision in subdivisions:
                # 👥 Сотрудники подразделения без отдела
                # исключая кандидатов и уволенных (если show_fired не включено)
                sub_employees_filter = Q(subdivision=subdivision, department__isnull=True) & ~Q(status='candidate')
                if not show_fired:
                    sub_employees_filter &= ~Q(status='fired')

                if selected_status:
                    sub_employees_filter &= Q(status=selected_status)

                sub_employees = Employee.objects.filter(sub_employees_filter).select_related('position')

                # Если есть поисковый запрос, фильтруем сотрудников
                if search_query:
                    sub_employees = sub_employees.filter(
                        Q(full_name_nominative__icontains=search_query) |
                        Q(position__position_name__icontains=search_query)
                    )

                # 🏭 Формируем структуру подразделения
                sub_data = {
                    'id': subdivision.id,
                    'name': subdivision.name,
                    'employees': list(sub_employees),
                    'departments': []
                }

                # 📂 Для каждого отдела получаем сотрудников
                for department in subdivision.departments.all():
                    # 👥 Сотрудники отдела
                    # исключая кандидатов и уволенных (если show_fired не включено)
                    dept_employees_filter = Q(department=department) & ~Q(status='candidate')
                    if not show_fired:
                        dept_employees_filter &= ~Q(status='fired')

                    if selected_status:
                        dept_employees_filter &= Q(status=selected_status)

                    dept_employees = Employee.objects.filter(dept_employees_filter).select_related('position')

                    # Если есть поисковый запрос, фильтруем сотрудников
                    if search_query:
                        dept_employees = dept_employees.filter(
                            Q(full_name_nominative__icontains=search_query) |
                            Q(position__position_name__icontains=search_query)
                        )

                    # 📂 Формируем структуру отдела
                    dept_data = {
                        'id': department.id,
                        'name': department.name,
                        'employees': list(dept_employees)
                    }

                    sub_data['departments'].append(dept_data)

                # Добавляем подразделение только если в нем есть сотрудники (учитывая поиск)
                if search_query:
                    if sub_employees.count() > 0 or any(len(dept['employees']) > 0 for dept in sub_data['departments']):
                        org_data['subdivisions'].append(sub_data)
                else:
                    org_data['subdivisions'].append(sub_data)

            # Добавляем организацию, если она не пустая в контексте поиска
            if not search_query or org_employees.count() > 0 or any(
                    len(sub['employees']) > 0 for sub in org_data['subdivisions']):
                organizations.append(org_data)

        # 📄 Добавляем пагинацию организаций
        page = self.request.GET.get('page', 1)
        paginator = Paginator(organizations, 5)  # По 5 организаций на страницу

        try:
            organizations_page = paginator.page(page)
        except PageNotAnInteger:
            organizations_page = paginator.page(1)
        except EmptyPage:
            organizations_page = paginator.page(paginator.num_pages)

        context['organizations'] = organizations_page
        context['paginator'] = paginator
        context['is_paginated'] = paginator.num_pages > 1

        return context


class SetOrganizationView(LoginRequiredMixin, View):
    """
    🏢 POST-view для установки выбранной организации в сессию.
    Используется глобальным селектором в хэдере.
    """

    def post(self, request, *args, **kwargs):
        org_id_raw = request.POST.get('org_id')
        next_url = request.POST.get('next', '/')

        # Защита от open redirect: разрешаем только path (без домена)
        parsed = urlparse(next_url)
        if parsed.netloc:
            next_url = '/'

        if org_id_raw:
            try:
                org_id = int(org_id_raw)
                accessible_orgs = AccessControlHelper.get_accessible_organizations(request.user, request)
                if accessible_orgs.filter(id=org_id).exists():
                    request.session['selected_org_id'] = org_id
                    logger.info(f"User {request.user.username} selected org_id={org_id} via header")
            except (ValueError, TypeError):
                pass

        return HttpResponseRedirect(next_url)


class IntroductoryBriefingView(LoginRequiredMixin, TemplateView):
    """
    📺 Страница вводного инструктажа с обучающим видео.
    """
    template_name = 'directory/introductory_briefing.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['title'] = 'Вводный инструктаж'
        return context
