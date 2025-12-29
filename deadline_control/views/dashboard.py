# deadline_control/views/dashboard.py
from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import TemplateView
from django.db.models import Q, Count
from django.utils import timezone
from datetime import timedelta

from deadline_control.models import Equipment, KeyDeadlineCategory, KeyDeadlineItem
from deadline_control.models.medical_norm import EmployeeMedicalExamination
from directory.utils.permissions import AccessControlHelper


class DashboardView(LoginRequiredMixin, TemplateView):
    """
    Главная страница приложения Контроль сроков с обзором всех истекающих сроков
    """
    template_name = 'deadline_control/dashboard.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        user = self.request.user
        today = timezone.now().date()
        warning_date = today + timedelta(days=14)

        # Получаем доступные организации через AccessControlHelper
        accessible_orgs = AccessControlHelper.get_accessible_organizations(user, self.request)

        # Фильтр по конкретной организации из GET-параметра
        org_id = self.request.GET.get('org')
        selected_org = None
        if org_id:
            from directory.models import Organization
            try:
                selected_org = Organization.objects.get(pk=org_id)
                # ВАЖНО: Проверяем права доступа через AccessControlHelper
                if not user.is_superuser and selected_org not in accessible_orgs:
                    # Пользователь пытается получить доступ к организации, к которой у него нет прав
                    selected_org = None
                else:
                    context['selected_org'] = selected_org
            except Organization.DoesNotExist:
                pass

        # ========== ОБОРУДОВАНИЕ ==========
        equipment_qs = Equipment.objects.select_related('organization', 'subdivision', 'department')

        # КРИТИЧНО: Применяем фильтрацию по правам ВСЕГДА через AccessControlHelper
        equipment_qs = AccessControlHelper.filter_queryset(equipment_qs, user, self.request)

        # Дополнительная фильтрация по выбранной организации (если указана)
        if selected_org:
            equipment_qs = equipment_qs.filter(organization=selected_org)

        # Просроченное ТО
        overdue_equipment = []
        # Скоро ТО (в течение 14 дней)
        upcoming_equipment = []

        for eq in equipment_qs:
            if eq.next_maintenance_date:
                if eq.next_maintenance_date < today:
                    overdue_equipment.append(eq)
                elif eq.next_maintenance_date <= warning_date:
                    upcoming_equipment.append(eq)

        # ========== КЛЮЧЕВЫЕ СРОКИ ==========
        # Категории теперь справочник, работаем напрямую с мероприятиями
        items_qs = KeyDeadlineItem.objects.filter(is_active=True).select_related('category', 'organization')

        # КРИТИЧНО: Применяем фильтрацию по правам ВСЕГДА через AccessControlHelper
        items_qs = AccessControlHelper.filter_queryset(items_qs, user, self.request)

        # Дополнительная фильтрация по выбранной организации (если указана)
        if selected_org:
            items_qs = items_qs.filter(organization=selected_org)

        overdue_deadlines = []
        upcoming_deadlines = []

        for item in items_qs:
            if item.next_date:
                if item.next_date < today:
                    overdue_deadlines.append(item)
                elif item.next_date <= warning_date:
                    upcoming_deadlines.append(item)

        # ========== МЕДИЦИНСКИЕ ОСМОТРЫ ==========
        # Получаем сотрудников, должность которых требует прохождения медосмотров
        from directory.models import Employee
        from deadline_control.models import MedicalExaminationNorm
        from django.db.models import Q

        # Находим все уникальные названия профессий из эталонных норм
        position_names_with_norms = MedicalExaminationNorm.objects.values_list(
            'position_name', flat=True
        ).distinct()

        # Находим сотрудников, чья должность требует медосмотров
        employees_qs = Employee.objects.exclude(
            status__in=['candidate', 'fired']
        ).filter(
            Q(position__medical_factors__isnull=False) |  # Есть переопределения
            Q(position__position_name__in=position_names_with_norms)  # Есть в эталонах
        )

        # КРИТИЧНО: Фильтрация по правам доступа через AccessControlHelper
        employees_qs = AccessControlHelper.filter_queryset(employees_qs, user, self.request)

        # Дополнительная фильтрация по выбранной организации (если указана)
        if selected_org:
            employees_qs = employees_qs.filter(organization=selected_org)

        # Prefetch для оптимизации запросов
        employees_qs = employees_qs.select_related(
            'organization',
            'position'
        ).prefetch_related(
            'medical_examinations__harmful_factor',
            'position__medical_factors__harmful_factor'
        ).distinct()  # ВАЖНО: distinct() в конце, после всех JOIN-ов

        overdue_medical = []
        upcoming_medical = []

        # Группируем по сотрудникам, используя get_medical_status()
        for employee in employees_qs:
            medical_status = employee.get_medical_status()

            if not medical_status or medical_status['status'] == 'no_date':
                # Нет медосмотров или нет даты - пропускаем для дашборда
                continue

            # Добавляем статус к объекту сотрудника для использования в шаблоне
            employee.medical_status_info = medical_status

            # Распределяем по категориям
            status = medical_status['status']
            if status == 'expired':
                overdue_medical.append(employee)
            elif status == 'upcoming':
                upcoming_medical.append(employee)

        # ========== СТАТИСТИКА ==========
        context.update({
            # Оборудование
            'total_equipment': equipment_qs.count(),
            'overdue_equipment': overdue_equipment,
            'overdue_equipment_count': len(overdue_equipment),
            'upcoming_equipment': upcoming_equipment,
            'upcoming_equipment_count': len(upcoming_equipment),

            # Ключевые сроки
            'total_deadlines': items_qs.count(),
            'overdue_deadlines': overdue_deadlines,
            'overdue_deadlines_count': len(overdue_deadlines),
            'upcoming_deadlines': upcoming_deadlines,
            'upcoming_deadlines_count': len(upcoming_deadlines),

            # Медицинские осмотры
            'total_medical': employees_qs.count(),
            'overdue_medical': overdue_medical,
            'overdue_medical_count': len(overdue_medical),
            'upcoming_medical': upcoming_medical,
            'upcoming_medical_count': len(upcoming_medical),

            # Общее
            'total_overdue': len(overdue_equipment) + len(overdue_deadlines) + len(overdue_medical),
            'total_upcoming': len(upcoming_equipment) + len(upcoming_deadlines) + len(upcoming_medical),

            # Список доступных организаций для фильтрации
            'accessible_organizations': accessible_orgs,
        })

        return context
