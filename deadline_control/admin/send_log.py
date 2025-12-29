# deadline_control/admin/send_log.py

from django.contrib import admin
from django.utils.html import format_html
from django.urls import reverse
from deadline_control.models import InstructionJournalSendLog, InstructionJournalSendDetail
import json


class InstructionJournalSendDetailInline(admin.TabularInline):
    """
    Inline для отображения деталей отправки по каждому подразделению
    """
    model = InstructionJournalSendDetail
    extra = 0
    can_delete = False

    fields = [
        'subdivision',
        'status_badge',
        'recipients_display',
        'employees_count',
        'error_display',
        'sent_at',
    ]
    readonly_fields = [
        'subdivision',
        'status_badge',
        'recipients_display',
        'employees_count',
        'error_display',
        'sent_at',
    ]

    def status_badge(self, obj):
        """Бейдж статуса с иконкой"""
        colors = {
            'success': '#4caf50',
            'failed': '#f44336',
            'skipped': '#ff9800',
        }

        icons = {
            'success': '✅',
            'failed': '❌',
            'skipped': '⏭️',
        }

        color = colors.get(obj.status, '#9e9e9e')
        icon = icons.get(obj.status, '❓')
        label = obj.get_status_display()

        return format_html(
            '<span style="background:{};color:white;padding:4px 8px;border-radius:6px;font-weight:600;">{} {}</span>',
            color, icon, label
        )

    status_badge.short_description = "Статус"

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
            '<details><summary style="cursor:pointer;"><strong>{} адрес(ов)</strong></summary><div style="margin-top:8px;font-size:11px;">{}</div></details>',
            count,
            recipients_html
        )

    recipients_display.short_description = "Получатели"

    def error_display(self, obj):
        """Отображение ошибки или причины пропуска"""
        if obj.status == 'success':
            return '—'

        if obj.skip_reason:
            reason_text = obj.get_skip_reason_display_custom()
            return format_html(
                '<span style="color:#ff9800;font-weight:600;">{}</span>',
                reason_text
            )

        if obj.error_message:
            # Сокращаем длинные ошибки
            error = obj.error_message[:200]
            if len(obj.error_message) > 200:
                error += '...'
            return format_html(
                '<span style="color:#f44336;">{}</span>',
                error
            )

        return '—'

    error_display.short_description = "Ошибка / Причина"


@admin.register(InstructionJournalSendLog)
class InstructionJournalSendLogAdmin(admin.ModelAdmin):
    """
    Админка для просмотра логов массовой рассылки образцов журналов инструктажей
    """

    list_display = [
        'id',
        'organization',
        'created_at_display',
        'initiated_by',
        'briefing_date',
        'statistics_badge',
        'status_badge',
        'view_details_button',
    ]

    list_filter = [
        'status',
        'organization',
        'initiated_by',
        'created_at',
        'briefing_date',
    ]

    search_fields = [
        'organization__short_name_ru',
        'organization__full_name_ru',
        'initiated_by__username',
        'initiated_by__email',
        'briefing_reason',
    ]

    readonly_fields = [
        'organization',
        'initiated_by',
        'briefing_date',
        'briefing_type',
        'briefing_reason',
        'total_subdivisions',
        'successful_count',
        'failed_count',
        'skipped_count',
        'status',
        'created_at',
        'updated_at',
        'statistics_summary',
        'success_rate_display',
    ]

    fieldsets = (
        ('Основная информация', {
            'fields': (
                'organization',
                'initiated_by',
                'created_at',
                'updated_at',
                'status',
            )
        }),
        ('Параметры инструктажа', {
            'fields': (
                'briefing_date',
                'briefing_type',
                'briefing_reason',
            )
        }),
        ('Статистика', {
            'fields': (
                'total_subdivisions',
                'successful_count',
                'failed_count',
                'skipped_count',
                'success_rate_display',
                'statistics_summary',
            )
        }),
    )

    inlines = [InstructionJournalSendDetailInline]

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

    def statistics_badge(self, obj):
        """Бейдж со статистикой"""
        return format_html(
            '<span style="background:#4caf50;color:white;padding:4px 8px;border-radius:4px;margin-right:4px;">✅ {}</span>'
            '<span style="background:#f44336;color:white;padding:4px 8px;border-radius:4px;margin-right:4px;">❌ {}</span>'
            '<span style="background:#ff9800;color:white;padding:4px 8px;border-radius:4px;">⏭️ {}</span>',
            obj.successful_count,
            obj.failed_count,
            obj.skipped_count
        )

    statistics_badge.short_description = "Статистика"

    def status_badge(self, obj):
        """Бейдж статуса"""
        colors = {
            'in_progress': '#2196f3',
            'completed': '#4caf50',
            'partial': '#ff9800',
            'failed': '#f44336',
        }

        icons = {
            'in_progress': '⏳',
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
        url = reverse('admin:deadline_control_instructionjournalsendlog_change', args=[obj.pk])
        return format_html(
            '<a class="button" href="{}" style="padding:6px 12px;">📊 Детали</a>',
            url
        )

    view_details_button.short_description = "Действия"

    def statistics_summary(self, obj):
        """Детальная статистика"""
        total = obj.get_total_processed()
        success_rate = obj.get_success_rate()

        return format_html(
            '<div style="font-size:14px;line-height:1.8;">'
            '<strong>Всего обработано:</strong> {} подразделений<br>'
            '<strong>Успешно:</strong> <span style="color:#4caf50;font-weight:600;">{}</span><br>'
            '<strong>Ошибок:</strong> <span style="color:#f44336;font-weight:600;">{}</span><br>'
            '<strong>Пропущено:</strong> <span style="color:#ff9800;font-weight:600;">{}</span><br>'
            '<strong>Процент успеха:</strong> <span style="color:#2196f3;font-weight:600;">{}%</span>'
            '</div>',
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
        return qs.select_related('organization', 'initiated_by')
