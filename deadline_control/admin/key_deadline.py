# deadline_control/admin/key_deadline.py
from datetime import datetime
from io import StringIO
from django.contrib import admin
from django.contrib import messages
from django.core.management import call_command
from django.shortcuts import redirect
from django.utils import timezone
from django.utils.html import format_html
from django.db.models import Count, Q

from deadline_control.models import (
    KeyDeadlineCategory,
    KeyDeadlineItem,
    OrganizationKeyDeadline,
    KeyDeadlineSendLog,
)


@admin.register(KeyDeadlineCategory)
class KeyDeadlineCategoryAdmin(admin.ModelAdmin):
    """
    Админ-панель для категорий ключевых сроков (справочник)

    Категории общие для всех организаций, с эталонной периодичностью.
    Мероприятия редактируются через OrganizationKeyDeadlineAdmin.
    """
    list_display = ['icon', 'name', 'periodicity_display', 'items_count', 'overdue_count']
    search_fields = ['name']

    fieldsets = (
        ('Основная информация', {
            'fields': ('name', 'periodicity_months', 'icon')
        }),
    )

    def periodicity_display(self, obj):
        """Периодичность в месяцах"""
        if obj.periodicity_months:
            return format_html('<span>{} мес.</span>', obj.periodicity_months)
        return '-'
    periodicity_display.short_description = "Периодичность"
    periodicity_display.admin_order_field = 'periodicity_months'

    def items_count(self, obj):
        """Количество мероприятий в категории"""
        count = obj.items.count()
        return format_html('<span>{}</span>', count)
    items_count.short_description = "Всего мероприятий"

    def overdue_count(self, obj):
        """Количество просроченных мероприятий"""
        count = sum(1 for item in obj.items.filter(is_active=True) if item.is_overdue())
        if count > 0:
            return format_html('<span style="color:red; font-weight:bold;">🚨 {}</span>', count)
        return format_html('<span style="color:green;">✅ 0</span>')
    overdue_count.short_description = "Просроченных"


class KeyDeadlineItemInline(admin.TabularInline):
    """
    📅 Инлайн для управления ключевыми сроками организации
    """
    model = KeyDeadlineItem
    extra = 3
    fields = [
        'category',
        'name',
        'current_date',
        'next_date',
        'status_display',
        'periodicity_months',
        'responsible_person',
        'is_active'
    ]
    readonly_fields = ['next_date', 'status_display']

    verbose_name = "Ключевой срок"
    verbose_name_plural = "Мероприятия"

    def status_display(self, obj):
        """Отображение статуса мероприятия"""
        if not obj.pk or not obj.next_date:
            return '-'

        days = obj.days_until_next()
        if days is None:
            return '-'

        if days < 0:
            # Просрочено - красный
            return format_html(
                '<span style="color: red; font-weight: bold;">⚠️ Просрочено на {} дн.</span>',
                abs(days)
            )
        elif days <= 14:
            # Скоро - оранжевый
            return format_html(
                '<span style="color: orange; font-weight: bold;">⏰ Осталось {} дн.</span>',
                days
            )
        else:
            # Норма - зелёный
            return format_html(
                '<span style="color: green;">✅ Через {} дн.</span>',
                days
            )
    status_display.short_description = "Статус"


@admin.register(OrganizationKeyDeadline)
class OrganizationKeyDeadlineAdmin(admin.ModelAdmin):
    """
    📅 Ключевые сроки - управление мероприятиями по организациям

    Показывает список организаций с возможностью управления их ключевыми сроками.
    При клике на организацию открывается форма с инлайном мероприятий.
    """
    list_display = [
        'short_name_ru',
        'active_items_count',
        'overdue_items_count',
        'send_notifications_button'
    ]
    search_fields = ['short_name_ru', 'full_name_ru']
    inlines = [KeyDeadlineItemInline]
    list_per_page = 50

    # Скрываем кнопки добавления/удаления организаций
    def get_model_perms(self, request):
        """Разрешения для модели"""
        return {
            'add': False,  # Не создаём организации через этот админ
            'change': True,
            'delete': False,
            'view': True,
        }

    def get_queryset(self, request):
        """
        Фильтрация по организациям пользователя + сортировка по просроченным
        """
        qs = super().get_queryset(request)

        # Фильтрация по организациям пользователя
        if not request.user.is_superuser and hasattr(request.user, 'profile'):
            allowed_orgs = request.user.profile.organizations.all()
            qs = qs.filter(pk__in=allowed_orgs)

        # Аннотация для сортировки
        qs = qs.prefetch_related('key_deadline_items')

        return qs

    def get_ordering(self, request):
        """
        Сортировка: сначала организации с просроченными мероприятиями
        """
        # Сортировка будет выполняться в методе changelist_view
        # через кастомный QuerySet
        return ['short_name_ru']

    def active_items_count(self, obj):
        """Количество активных мероприятий"""
        count = obj.key_deadline_items.filter(is_active=True).count()
        return format_html('<span>{}</span>', count)
    active_items_count.short_description = "Активных мероприятий"

    def overdue_items_count(self, obj):
        """Количество просроченных мероприятий"""
        items = obj.key_deadline_items.filter(is_active=True)
        count = sum(1 for item in items if item.is_overdue())
        if count > 0:
            return format_html('<span style="color:red; font-weight:bold;">🚨 {}</span>', count)
        return format_html('<span style="color:green;">✅ 0</span>')
    overdue_items_count.short_description = "Просроченных"

    def send_notifications_button(self, obj):
        """Кнопка для отправки уведомлений по ключевым срокам"""
        return format_html(
            '<a class="button" href="{}?action=send_notifications" '
            'style="padding:4px 10px; white-space: nowrap;">📧 Отправить</a>',
            f'/admin/deadline_control/organizationkeydeadline/{obj.pk}/change/'
        )
    send_notifications_button.short_description = "Уведомления"

    def change_view(self, request, object_id, form_url='', extra_context=None):
        """
        Обработка кастомного действия отправки уведомлений
        """
        if request.GET.get('action') == 'send_notifications':
            organization = self.get_object(request, object_id)
            if organization:
                self._send_key_deadline_notifications(request, organization)
                return redirect(
                    f'/admin/deadline_control/organizationkeydeadline/{object_id}/change/'
                )

        return super().change_view(request, object_id, form_url, extra_context)

    def _send_key_deadline_notifications(self, request, organization):
        """Запускает рассылку уведомлений по ключевым срокам для организации"""
        started_at = timezone.now()
        buffer = StringIO()

        try:
            call_command(
                'send_key_deadline_notifications',
                organization=organization.id,
                stdout=buffer,
            )

            # Обновляем логи, созданные в рамках этого запуска
            KeyDeadlineSendLog.objects.filter(
                organization=organization,
                created_at__gte=started_at
            ).update(
                initiated_by=request.user,
                notification_type='manual'
            )

            messages.success(
                request,
                f'✅ Уведомления по ключевым срокам отправлены для {organization.short_name_ru}'
            )

            output = buffer.getvalue().strip()
            if output:
                # Показываем вывод команды
                lines = output.split('\n')
                for line in lines:
                    if line.strip():
                        messages.info(request, line)

        except Exception as exc:
            messages.error(
                request,
                f'❌ Не удалось отправить уведомления: {exc}'
            )

    def changelist_view(self, request, extra_context=None):
        """
        Переопределяем для кастомной сортировки по просроченным
        """
        response = super().changelist_view(request, extra_context)

        # Получаем changelist из ответа
        try:
            cl = response.context_data['cl']
            queryset = cl.queryset

            # Сортируем: сначала с просроченными, потом по названию
            orgs_with_overdue = []
            orgs_without_overdue = []

            for org in queryset:
                items = org.key_deadline_items.filter(is_active=True)
                overdue_count = sum(1 for item in items if item.is_overdue())

                if overdue_count > 0:
                    orgs_with_overdue.append((overdue_count, org))
                else:
                    orgs_without_overdue.append(org)

            # Сортируем проблемные по количеству просроченных (больше = первые)
            orgs_with_overdue.sort(key=lambda x: x[0], reverse=True)

            # Собираем финальный список
            sorted_orgs = [org for _, org in orgs_with_overdue] + orgs_without_overdue

            # Подменяем queryset
            cl.queryset = sorted_orgs
            cl.result_list = sorted_orgs

        except (AttributeError, KeyError):
            pass

        return response

    class Media:
        css = {
            'all': ('admin/css/changelists.css',)
        }
