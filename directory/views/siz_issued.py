# 📁 directory/views/siz_issued.py
import re
import json
import random
from decimal import Decimal, InvalidOperation
from django.views.generic import CreateView, DetailView, FormView, UpdateView
from django.contrib.auth.mixins import LoginRequiredMixin
from django.urls import reverse_lazy, reverse
from django.shortcuts import get_object_or_404, redirect
from django.http import JsonResponse, HttpResponse
from django.contrib import messages
from django.utils.decorators import method_decorator
from django.views.decorators.http import require_GET, require_POST
from django.contrib.auth.decorators import login_required
from django.utils import timezone
from django.template.loader import get_template
from io import BytesIO
from xhtml2pdf import pisa

from directory.models import Employee, SIZIssued, SIZ
from directory.forms.siz_issued import SIZIssueForm, SIZIssueMassForm, SIZIssueReturnForm
from directory.mixins import AccessControlMixin, AccessControlObjectMixin
from directory.utils.permissions import AccessControlHelper
from directory.utils.siz_sizes import get_employee_sizes


def determine_gender_from_patronymic(full_name):
    """
    Определяет пол человека по отчеству в полном имени.

    Args:
        full_name (str): Полное имя в формате "Фамилия Имя Отчество"

    Returns:
        str: "Мужской" или "Женский"
    """
    # Разбиваем полное имя на части
    name_parts = full_name.split()

    # Если имя состоит из 3 и более частей, предполагаем, что отчество - третья часть
    if len(name_parts) >= 3:
        patronymic = name_parts[2]
    else:
        # Если частей меньше 3, вернем мужской пол по умолчанию
        return "Мужской"

    # Проверяем окончание отчества
    # Русские отчества
    if re.search(r'(ич|ыч)$', patronymic, re.IGNORECASE):
        return "Мужской"
    elif re.search(r'(на|вна|чна)$', patronymic, re.IGNORECASE):
        return "Женский"
    # Тюркские отчества
    elif re.search(r'(оглы|улы|лы)$', patronymic, re.IGNORECASE):
        return "Мужской"
    elif re.search(r'(кызы|зы)$', patronymic, re.IGNORECASE):
        return "Женский"
    else:
        # Если не удалось определить по отчеству, возвращаем мужской пол по умолчанию
        return "Мужской"


def get_random_siz_sizes(gender):
    """
    Генерирует случайные размеры СИЗ в зависимости от пола.

    Args:
        gender (str): Пол сотрудника ("Мужской" или "Женский")

    Returns:
        dict: Словарь с размерами СИЗ (головной убор, перчатки, респиратор, противогаз)
    """
    if gender == "Мужской":
        # Мужские размеры
        headgear = random.randint(55, 59)  # Головной убор от 55 до 59
        gloves = random.randint(15, 19) / 2  # Перчатки от 7.5 до 9.5, кратные 0.5
        respirator = random.choice(["1", "2", "3"])  # Респиратор размеры 1, 2, 3
    else:
        # Женские размеры
        headgear = random.randint(53, 57)  # Головной убор от 53 до 57
        gloves = random.randint(13, 17) / 2  # Перчатки от 6.5 до 8.5, кратные 0.5
        respirator = random.choice(["1", "2", "3"])  # Респиратор размеры 1, 2, 3

    # Противогаз такого же размера, как и респиратор
    gas_mask = respirator

    return {
        'headgear': headgear,
        'gloves': gloves,
        'respirator': respirator,
        'gas_mask': gas_mask
    }


class SIZIssueFormView(LoginRequiredMixin, CreateView):
    """
    📝 Представление для выдачи СИЗ сотруднику
    """
    model = SIZIssued
    form_class = SIZIssueForm
    template_name = 'directory/siz_issued/issue_form.html'

    def get_success_url(self):
        """
        🔗 Возвращает URL для перенаправления после успешной выдачи СИЗ
        """
        return reverse('directory:siz:siz_personal_card', kwargs={'employee_id': self.object.employee.id})

    def get_form_kwargs(self):
        """
        📋 Передаем дополнительные параметры в форму
        """
        kwargs = super().get_form_kwargs()
        kwargs['user'] = self.request.user

        # Если в URL есть параметр employee_id, передаем его в форму
        employee_id = self.kwargs.get('employee_id')
        if employee_id:
            kwargs['employee_id'] = employee_id

        return kwargs

    def get_context_data(self, **kwargs):
        """
        📊 Добавляем дополнительные данные в контекст
        """
        context = super().get_context_data(**kwargs)
        context['title'] = 'Выдача СИЗ'

        # Если есть employee_id в URL, добавляем информацию о сотруднике
        employee_id = self.kwargs.get('employee_id')
        if employee_id:
            employee = get_object_or_404(Employee, id=employee_id)
            context['employee'] = employee

            siz_norm_ids = set()

            # Получаем нормы СИЗ для должности сотрудника
            if employee.position:
                from directory.models.siz import SIZNorm
                norms = SIZNorm.objects.filter(
                    position=employee.position
                ).select_related('siz')

                # Группируем нормы по условиям
                context['base_norms'] = norms.filter(condition='')

                condition_groups = {}
                for norm in norms.exclude(condition=''):
                    if norm.condition not in condition_groups:
                        condition_groups[norm.condition] = []
                    condition_groups[norm.condition].append(norm)

                context['condition_groups'] = [
                    {'name': condition, 'norms': norms}
                    for condition, norms in condition_groups.items()
                ]

                siz_norm_ids = set(norms.values_list('siz_id', flat=True))

            # Список всех СИЗ для группового выбора (нормативные помечены)
            from directory.models.siz import SIZNorm
            all_siz = SIZ.objects.order_by('name', 'classification')
            context['all_siz_choices'] = [
                {
                    'id': s.pk,
                    'label': f"{s.name} ({s.classification})" if s.classification else s.name,
                    'is_norm': s.pk in siz_norm_ids,
                }
                for s in all_siz
            ]
            # Datalist условий
            context['condition_list'] = list(
                SIZNorm.objects.exclude(condition='')
                .values_list('condition', flat=True)
                .distinct().order_by('condition')[:200]
            )
            context['today'] = timezone.now().date().strftime('%Y-%m-%d')

        return context

    def form_valid(self, form):
        """
        ✅ Обработка валидной формы
        """
        # Сохраняем объект
        response = super().form_valid(form)

        # Добавляем сообщение об успешной выдаче
        messages.success(
            self.request,
            f"✅ СИЗ '{self.object.siz.name}' успешно выдано сотруднику {self.object.employee.full_name_nominative}"
        )

        return response


@login_required
@require_POST
def issue_selected_siz(request, employee_id):
    """
    📝 Массовая выдача выбранных норм СИЗ сотруднику из личной карточки.
    """
    employee = get_object_or_404(Employee, id=employee_id)
    selected_norm_ids = request.POST.getlist('selected_norms')

    if not selected_norm_ids:
        messages.warning(request, "Не выбрано ни одного СИЗ для выдачи")
        return redirect('directory:siz:siz_personal_card', employee_id=employee_id)

    # Дата выдачи из формы (иначе сегодня)
    issue_date_str = request.POST.get('issue_date', '')
    try:
        from datetime import datetime as _dt
        issue_date = _dt.strptime(issue_date_str, '%Y-%m-%d').date()
    except ValueError:
        issue_date = timezone.now().date()

    from directory.models.siz import SIZNorm
    norms = SIZNorm.objects.filter(id__in=selected_norm_ids).select_related('siz')

    issued_count = 0
    skipped_count = 0
    for norm in norms:
        existing = SIZIssued.objects.filter(
            employee=employee,
            siz=norm.siz,
            is_returned=False
        ).exists()

        if existing:
            skipped_count += 1
            continue

        SIZIssued.objects.create(
            employee=employee,
            siz=norm.siz,
            quantity=norm.quantity,
            issue_date=issue_date,
            condition=norm.condition,
            received_signature=True,
        )
        issued_count += 1

    if issued_count > 0:
        messages.success(
            request,
            f"✅ Выдано {issued_count} наименований СИЗ сотруднику {employee.full_name_nominative}"
            + (f" (пропущено дублей: {skipped_count})" if skipped_count else "")
        )
    else:
        messages.info(request, "ℹ️ Ни одно СИЗ не было выдано — возможно, выбранные уже в использовании.")

    return redirect('directory:siz:siz_personal_card', employee_id=employee_id)


@login_required
@require_POST
def issue_group_siz(request, employee_id):
    """
    📦 Массовая групповая выдача СИЗ сотруднику.
    Принимает JSON-список групп (каждая: siz_ids, condition, quantity, cost).
    """
    employee = get_object_or_404(Employee, id=employee_id)

    try:
        groups = json.loads(request.POST.get('groups_json', '[]'))
    except (json.JSONDecodeError, ValueError):
        messages.error(request, "Ошибка при обработке данных групп СИЗ")
        return redirect('directory:siz:siz_issue_for_employee', employee_id=employee_id)

    issue_date_str = request.POST.get('group_issue_date', '')
    try:
        from datetime import datetime as dt
        issue_date = dt.strptime(issue_date_str, '%Y-%m-%d').date()
    except ValueError:
        issue_date = timezone.now().date()

    issued_count = 0
    for group in groups:
        siz_ids = group.get('siz_ids', [])
        condition = group.get('condition', '')
        try:
            quantity = max(1, int(group.get('quantity', 1)))
        except (ValueError, TypeError):
            quantity = 1
        cost = None
        cost_str = str(group.get('cost', '')).strip()
        if cost_str:
            try:
                cost = Decimal(cost_str)
            except InvalidOperation:
                cost = None

        for siz_id in siz_ids:
            try:
                siz_obj = SIZ.objects.get(id=siz_id)
            except SIZ.DoesNotExist:
                continue
            SIZIssued.objects.create(
                employee=employee,
                siz=siz_obj,
                issue_date=issue_date,
                quantity=quantity,
                condition=condition,
                cost=cost,
                received_signature=True,
            )
            issued_count += 1

    if issued_count > 0:
        messages.success(
            request,
            f"✅ Выдано {issued_count} наименований СИЗ сотруднику {employee.full_name_nominative}"
        )
    else:
        messages.warning(request, "Ни одно СИЗ не было выдано — проверьте заполнение групп")

    return redirect('directory:siz:siz_personal_card', employee_id=employee_id)


class SIZPersonalCardView(LoginRequiredMixin, AccessControlObjectMixin, DetailView):
    """
    👤 Представление для отображения личной карточки учета СИЗ сотрудника
    """
    model = Employee
    template_name = 'directory/siz_issued/personal_card.html'
    context_object_name = 'employee'

    def get_object(self, queryset=None):
        """
        🔍 Получаем объект сотрудника по его ID с проверкой прав доступа
        """
        # Получаем объект через стандартный метод
        obj = Employee.objects.get(id=self.kwargs.get('employee_id'))

        # AccessControlObjectMixin автоматически проверит права доступа
        # через переопределенный метод get_object в родительском классе
        if not AccessControlHelper.can_access_object(self.request.user, obj):
            from django.core.exceptions import PermissionDenied
            raise PermissionDenied("У вас нет доступа к этому сотруднику")

        return obj

    def get_context_data(self, **kwargs):
        """
        📊 Добавляем дополнительные данные в контекст
        """
        context = super().get_context_data(**kwargs)
        context['title'] = f'Личная карточка учета СИЗ - {self.object.full_name_nominative}'

        # Получаем все выданные сотруднику СИЗ
        issued_items = SIZIssued.objects.filter(
            employee=self.object
        ).select_related('siz').order_by('-issue_date', '-id')

        import calendar as _cal
        from datetime import date as _date

        def _add_months(d, months):
            month = d.month - 1 + months
            year = d.year + month // 12
            month = month % 12 + 1
            day = min(d.day, _cal.monthrange(year, month)[1])
            return _date(year, month, day)

        today = timezone.now().date()
        issued_with_dates = []
        for item in issued_items:
            planned = None
            is_overdue = is_soon = False
            if not item.is_returned and item.siz.wear_period and item.siz.wear_period > 0:
                planned = _add_months(item.issue_date, item.siz.wear_period)
                delta = (planned - today).days
                is_overdue = delta < 0
                is_soon = 0 <= delta <= 30
            issued_with_dates.append({
                'item': item,
                'planned_return': planned,
                'is_overdue': is_overdue,
                'is_soon': is_soon,
            })

        context['issued_with_dates'] = issued_with_dates
        context['today'] = today.strftime('%Y-%m-%d')

        # Получаем нормы СИЗ для должности сотрудника
        if self.object.position:
            from directory.models.siz import SIZNorm
            import logging
            logger = logging.getLogger(__name__)

            logger.info(f"Получение норм СИЗ для сотрудника ID={self.object.id}: {self.object.full_name_nominative}")
            logger.info(f"Должность: {self.object.position.position_name} (ID={self.object.position.id})")
            logger.info(f"Организация: {self.object.position.organization}")

            # Сначала пытаемся получить нормы для конкретной должности
            norms = SIZNorm.objects.filter(
                position=self.object.position
            ).select_related('siz')

            logger.info(f"Найдено норм СИЗ для должности: {norms.count()}")

            # Если нормы не найдены, берём из эталонных норм (ProfessionSIZNorm) по названию профессии
            if not norms.exists():
                logger.info("Нормы не найдены для конкретной должности, ищем в эталонных нормах...")
                from directory.models.siz import ProfessionSIZNorm

                norms = ProfessionSIZNorm.objects.filter(
                    profession_name__iexact=self.object.position.position_name
                ).select_related('siz')

                if norms.exists():
                    logger.info(f"Найдено {norms.count()} эталонных норм для профессии '{self.object.position.position_name}'")
                    context['norms_from_reference'] = True
                else:
                    logger.warning(f"Эталонные нормы для профессии '{self.object.position.position_name}' не найдены")

            # Базовые нормы (без условий)
            context['base_norms'] = norms.filter(condition='')
            logger.info(f"Базовых норм (без условий): {context['base_norms'].count()}")

            # Нормы по условиям
            conditions = list(set(norm.condition for norm in norms if norm.condition))
            condition_groups = []

            for condition in conditions:
                condition_norms = [norm for norm in norms if norm.condition == condition]
                if condition_norms:
                    condition_groups.append({
                        'name': condition,
                        'norms': condition_norms
                    })

            context['condition_groups'] = condition_groups
            logger.info(f"Групп норм с условиями: {len(condition_groups)}")

        # Определяем пол по отчеству и добавляем в контекст
        gender = determine_gender_from_patronymic(self.object.full_name_nominative)
        context['gender'] = gender

        # Генерируем случайные размеры СИЗ и добавляем в контекст
        context['siz_sizes'] = get_random_siz_sizes(gender)
        employee_sizes = get_employee_sizes(self.object, gender)
        context['employee_height'] = employee_sizes['height']
        context['employee_clothing_size'] = employee_sizes['clothing_size']
        context['employee_shoe_size'] = employee_sizes['shoe_size']

        return context


class SIZIssueReturnView(LoginRequiredMixin, AccessControlObjectMixin, UpdateView):
    """
    🔄 Представление для возврата выданного СИЗ
    """
    model = SIZIssued
    form_class = SIZIssueReturnForm
    template_name = 'directory/siz_issued/return_form.html'
    pk_url_kwarg = 'siz_issued_id'

    def get_success_url(self):
        """
        🔗 Возвращает URL для перенаправления после успешного возврата СИЗ
        """
        return reverse('directory:siz:siz_personal_card', kwargs={'employee_id': self.object.employee.id})

    def get_context_data(self, **kwargs):
        """
        📊 Добавляем дополнительные данные в контекст
        """
        context = super().get_context_data(**kwargs)
        context['title'] = 'Возврат СИЗ'
        context['employee'] = self.object.employee
        context['siz_name'] = self.object.siz.name
        context['issue_date'] = self.object.issue_date

        return context

    def form_valid(self, form):
        """
        ✅ Обработка валидной формы
        """
        # Сохраняем объект
        response = super().form_valid(form)

        # Добавляем сообщение об успешном возврате
        messages.success(
            self.request,
            f"✅ СИЗ '{self.object.siz.name}' успешно возвращено"
        )

        return response


@login_required
@require_GET
def employee_siz_issued_list(request, employee_id):
    """
    📋 Получение списка выданных СИЗ для конкретного сотрудника

    Используется для API и формирования оборотной стороны личной карточки.

    Args:
        request: HttpRequest объект
        employee_id: ID сотрудника

    Returns:
        JsonResponse с данными о выданных СИЗ
    """
    employee = get_object_or_404(Employee, pk=employee_id)

    # Получаем все СИЗ, выданные сотруднику
    issued_items = SIZIssued.objects.filter(
        employee=employee
    ).select_related('siz').order_by('-issue_date')

    # Формируем данные для JSON
    result = {
        'employee_id': employee.id,
        'employee_name': employee.full_name_nominative,
        'position': employee.position.position_name if employee.position else "",
        'organization': employee.organization.short_name_ru,
        'issued_items': []
    }

    # Добавляем информацию о каждом выданном СИЗ
    for item in issued_items:
        item_data = {
            'id': item.id,
            'siz_name': item.siz.name,
            'siz_classification': item.siz.classification,
            'issue_date': item.issue_date.strftime('%d.%m.%Y'),
            'quantity': item.quantity,
            'wear_percentage': item.wear_percentage,
            'is_returned': item.is_returned,
            'return_date': item.return_date.strftime('%d.%m.%Y') if item.return_date else None,
            'notes': item.notes,
            'condition': item.condition
        }
        result['issued_items'].append(item_data)

    return JsonResponse(result)

