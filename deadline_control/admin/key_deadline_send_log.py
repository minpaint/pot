# deadline_control/admin/key_deadline_send_log.py

from django.contrib import admin
from django.utils.html import format_html
from django.urls import reverse
from deadline_control.models import KeyDeadlineSendLog
from directory.admin.mixins.org_filter import apply_session_org_filter
import json


@admin.register(KeyDeadlineSendLog)
class KeyDeadlineSendLogAdmin(admin.ModelAdmin):
    """
    Админка для просмотра логов массовой рассылки уведомлений о ключевых мероприятиях
    """

    list_display = [
        'id',
        'organization',
        'created_at_display',
        'notification_type_badge',
        'initiated_by',
        'items_statistics_badge',
        'status_badge',
        'view_details_button',
    ]

    list_filter = [
        'status',
        'notification_type',
        'organization',
        'initiated_by',
        'created_at',
    ]

    search_fields = [
        'organization__short_name_ru',
        'organization__full_name_ru',
        'initiated_by__username',
        'initiated_by__email',
    ]

    readonly_fields = [
        'organization',
        'initiated_by',
        'notification_type',
        'overdue_items_count',
        'upcoming_items_count',
        'successful_count',
        'failed_count',
        'skipped_count',
        'status',
        'created_at',
        'updated_at',
        'sent_at',
        'email_template',
        'email_subject',
        'recipients_display',
        'error_message_display',
        'statistics_summary',
        'success_rate_display',
    ]

    fieldsets = (
        ('Основная информация', {
            'fields': (
                'organization',
                'initiated_by',
                'notification_type',
                'created_at',
                'updated_at',
                'status',
            )
        }),
        ('Статистика мероприятий', {
            'fields': (
                'overdue_items_count',
                'upcoming_items_count',
            )
        }),
        ('Отправка письма', {
            'fields': (
                'email_template',
                'email_subject',
                'recipients_display',
                'sent_at',
            )
        }),
        ('Результаты отправки', {
            'fields': (
                'successful_count',
                'failed_count',
                'skipped_count',
                'success_rate_display',
                'error_message_display',
                'statistics_summary',
            )
        }),
    )

    def has_add_permission(self, request):
        """Запрещаем создание вручную"""
        return False

    def has_delete_permission(self, request, obj=None):
        """Разрешаем удаление только суперпользователю"""
        return request.user.is_superuser

    def created_at_display(self, obj):
        """Дата запуска в читаемом формате"""
        return obj.created_at.strftime('%d.%m.%Y %H:%M')

    created_at_display.short_description = "Дата запуска"
    created_at_display.admin_order_field = 'created_at'

    def notification_type_badge(self, obj):
        """Бейдж типа уведомления"""
        colors = {
            'scheduled': '#2196f3',
            'manual': '#9c27b0',
        }

        icons = {
            'scheduled': '🕐',
            'manual': '👤',
        }

        color = colors.get(obj.notification_type, '#9e9e9e')
        icon = icons.get(obj.notification_type, '❓')
        label = obj.get_notification_type_display()

        return format_html(
            '<span style="background:{};color:white;padding:4px 8px;border-radius:6px;font-weight:600;font-size:11px;">{} {}</span>',
            color, icon, label
        )

    notification_type_badge.short_description = "Тип"
    notification_type_badge.admin_order_field = 'notification_type'

    def items_statistics_badge(self, obj):
        """Бейдж со статистикой мероприятий"""
        total = obj.overdue_items_count + obj.upcoming_items_count
        return format_html(
            '<div style="font-size:11px;">'
            '<span style="background:#2196f3;color:white;padding:2px 6px;border-radius:3px;margin-right:2px;">📊 {}</span>'
            '<span style="background:#f44336;color:white;padding:2px 6px;border-radius:3px;margin-right:2px;">🚨 {}</span>'
            '<span style="background:#ff9800;color:white;padding:2px 6px;border-radius:3px;">🕐 {}</span>'
            '</div>',
            total,
            obj.overdue_items_count,
            obj.upcoming_items_count
        )

    items_statistics_badge.short_description = "Мероприятия"

    def status_badge(self, obj):
        """Бейдж статуса"""
        colors = {
            'in_progress': '#2196f3',
            'completed': '#4caf50',
            'partial': '#ff9800',
            'failed': '#f44336',
        }

        icons = {
            'in_progress': '🔄',
            'completed': '✅',
            'partial': '⚠️',
            'failed': '❌',
        }

        color = colors.get(obj.status, '#9e9e9e')
        icon = icons.get(obj.status, '❓')
        label = obj.get_status_display()

        return format_html(
            '<span style="background:{};color:white;padding:6px 12px;border-radius:6px;font-weight:600;font-size:12px;">{} {}</span>',
            color, icon, label
        )

    status_badge.short_description = "Статус"

    def view_details_button(self, obj):
        """Кнопка для просмотра деталей"""
        url = reverse('admin:deadline_control_keydeadlinesendlog_change', args=[obj.pk])
        return format_html(
            '<a class="button" href="{}" style="padding:6px 12px;">📊 Детали</a>',
            url
        )

    view_details_button.short_description = "Действия"

    def recipients_display(self, obj):
        """Отображение получателей"""
        recipients = obj.get_recipients_list()
        if not recipients:
            return format_html('<span style="color:#999;">Нет получателей</span>')

        count = len(recipients)
        if count == 0:
            return format_html('<span style="color:#999;">0</span>')

        # Показываем количество и раскрывающийся список
        recipients_html = '<br>'.join([f'• {email}' for email in recipients])
        return format_html(
            '<div style="font-size:13px;">'
            '<strong>Всего: {} адрес(ов)</strong><br>'
            '<details style="margin-top:8px;"><summary style="cursor:pointer;">Показать список</summary>'
            '<div style="margin-top:8px;font-size:11px;padding:8px;background:#f5f5f5;border-radius:4px;">{}</div>'
            '</details>'
            '</div>',
            count,
            recipients_html
        )

    recipients_display.short_description = "Получатели"

    def error_message_display(self, obj):
        """Отображение сообщения об ошибке"""
        if not obj.error_message:
            return format_html('<span style="color:#4caf50;">✅ Нет ошибок</span>')

        # Сокращаем длинные ошибки
        error = obj.error_message[:300]
        if len(obj.error_message) > 300:
            error += '...'

        return format_html(
            '<div style="color:#f44336;font-size:12px;padding:8px;background:#ffebee;border-radius:4px;border-left:3px solid #f44336;">{}</div>',
            error
        )

    error_message_display.short_description = "Ошибка"

    def statistics_summary(self, obj):
        """Детальная статистика"""
        total = obj.get_total_processed()
        total_items = obj.get_total_items()
        success_rate = obj.get_success_rate()

        return format_html(
            '<div style="font-size:14px;line-height:1.8;">'\
            '<strong>Мероприятия:</strong><br>'\
            '🚨 Просроченных: <span style="color:#f44336;font-weight:600;">{}</span><br>'\
            '🕐 Предстоящих: <span style="color:#ff9800;font-weight:600;">{}</span><br>'\
            '📋 Всего мероприятий: {}<br>'\
            '<br>'\
            '<strong>Отправки:</strong><br>'\
            'Всего обработано: {}<br>'\
            '<strong>Успешно:</strong> <span style="color:#4caf50;font-weight:600;">{}</span><br>'\
            '<strong>Ошибок:</strong> <span style="color:#f44336;font-weight:600;">{}</span><br>'\
            '<strong>Пропущено:</strong> <span style="color:#ff9800;font-weight:600;">{}</span><br>'\
            '<strong>Процент успеха:</strong> <span style="color:#2196f3;font-weight:600;">{}%</span>'\
            '</div>',
            obj.overdue_items_count,
            obj.upcoming_items_count,
            total_items,
            total,
            obj.successful_count,
            obj.failed_count,
            obj.skipped_count,
            success_rate
        )

    statistics_summary.short_description = "Сводка"

    def success_rate_display(self, obj):
        """Процент успешности"""
        rate = obj.get_success_rate()
        color = '#4caf50' if rate >= 80 else '#ff9800' if rate >= 50 else '#f44336'

        return format_html(
            '<span style="color:{};font-weight:600;font-size:16px;">{}%</span>',
            color, rate
        )

    success_rate_display.short_description = "Процент успеха"

    def get_queryset(self, request):
        """Фильтруем по организациям пользователя"""
        qs = super().get_queryset(request)
        if not request.user.is_superuser and hasattr(request.user, 'profile'):
            allowed_orgs = request.user.profile.organizations.all()
            qs = qs.filter(organization__in=allowed_orgs)
        qs = apply_session_org_filter(request, qs)
        return qs.select_related('organization', 'initiated_by')
