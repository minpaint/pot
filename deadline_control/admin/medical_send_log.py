# deadline_control/admin/medical_send_log.py

from django.contrib import admin
from django.utils.html import format_html
from django.urls import reverse, path
from django.shortcuts import render, redirect
from django.contrib import messages
from django.core.management import call_command
from io import StringIO
from deadline_control.models import MedicalNotificationSendLog, MedicalNotificationSendDetail
from directory.models import Organization
from directory.admin.mixins.org_filter import apply_session_org_filter
import json


class MedicalNotificationSendDetailInline(admin.TabularInline):
    """
    Inline для отображения деталей отправки медицинских уведомлений
    """
    model = MedicalNotificationSendDetail
    extra = 0
    can_delete = False

    fields = [
        'status_badge',
        'recipients_display',
        'employees_statistics',
        'error_display',
        'sent_at',
    ]
    readonly_fields = [
        'status_badge',
        'recipients_display',
        'employees_statistics',
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
            'skipped': '⏩',
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

    def employees_statistics(self, obj):
        """Статистика сотрудников"""
        return format_html(
            '<div style="font-size:12px;">'
            '📊 Всего: <strong>{}</strong><br>'
            '📋 Без даты: <span style="color:#2196f3;">{}</span><br>'
            '🚨 Просроченные: <span style="color:#f44336;">{}</span><br>'
            '🕐 Предстоящие: <span style="color:#ff9800;">{}</span>'
            '</div>',
            obj.employees_total,
            obj.no_date_count,
            obj.expired_count,
            obj.upcoming_count
        )

    employees_statistics.short_description = "Статистика"

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


@admin.register(MedicalNotificationSendLog)
class MedicalNotificationSendLogAdmin(admin.ModelAdmin):
    """
    Админка для просмотра логов массовой рассылки медицинских уведомлений
    """

    list_display = [
        'id',
        'organization',
        'created_at_display',
        'notification_type_badge',
        'initiated_by',
        'employees_statistics_badge',
        'status_badge',
        'view_details_button',
        'send_new_button',
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
        'no_date_count',
        'expired_count',
        'upcoming_count',
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
                'notification_type',
                'created_at',
                'updated_at',
                'status',
            )
        }),
        ('Статистика медосмотров', {
            'fields': (
                'no_date_count',
                'expired_count',
                'upcoming_count',
            )
        }),
        ('Статистика отправки', {
            'fields': (
                'successful_count',
                'failed_count',
                'skipped_count',
                'success_rate_display',
                'statistics_summary',
            )
        }),
    )

    inlines = [MedicalNotificationSendDetailInline]

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

    def employees_statistics_badge(self, obj):
        """Бейдж со статистикой сотрудников"""
        return format_html(
            '<div style="font-size:11px;">'
            '<span style="background:#2196f3;color:white;padding:2px 6px;border-radius:3px;margin-right:2px;">📋 {}</span>'
            '<span style="background:#f44336;color:white;padding:2px 6px;border-radius:3px;margin-right:2px;">🚨 {}</span>'
            '<span style="background:#ff9800;color:white;padding:2px 6px;border-radius:3px;">🕐 {}</span>'
            '</div>',
            obj.no_date_count,
            obj.expired_count,
            obj.upcoming_count
        )

    employees_statistics_badge.short_description = "Сотрудники"

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
        url = reverse('admin:deadline_control_medicalnotificationsendlog_change', args=[obj.pk])
        return format_html(
            '<a class="button" href="{}" style="padding:6px 12px;">📊 Детали</a>',
            url
        )

    view_details_button.short_description = "Действия"

    def statistics_summary(self, obj):
        """Детальная статистика"""
        total = obj.get_total_processed()
        total_employees = obj.get_total_employees()
        success_rate = obj.get_success_rate()

        return format_html(
            '<div style="font-size:14px;line-height:1.8;">'\
            '<strong>Сотрудники:</strong><br>'\
            '📊 Всего: {} сотрудников<br>'\
            '📋 Без даты МО: <span style="color:#2196f3;font-weight:600;">{}</span><br>'\
            '🚨 Просроченные МО: <span style="color:#f44336;font-weight:600;">{}</span><br>'\
            '🕐 Предстоящие МО: <span style="color:#ff9800;font-weight:600;">{}</span><br>'\
            '<br>'\
            '<strong>Отправки:</strong><br>'\
            'Всего обработано: {}<br>'\
            '<strong>Успешно:</strong> <span style="color:#4caf50;font-weight:600;">{}</span><br>'\
            '<strong>Ошибок:</strong> <span style="color:#f44336;font-weight:600;">{}</span><br>'\
            '<strong>Пропущено:</strong> <span style="color:#ff9800;font-weight:600;">{}</span><br>'\
            '<strong>Процент успеха:</strong> <span style="color:#2196f3;font-weight:600;">{}%</span>'\
            '</div>',
            total_employees,
            obj.no_date_count,
            obj.expired_count,
            obj.upcoming_count,
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

    def get_urls(self):
        """Добавляем кастомный URL для запуска рассылки"""
        urls = super().get_urls()
        custom_urls = [
            path(
                'send_notifications/',
                self.admin_site.admin_view(self.send_notifications_view),
                name='deadline_control_medical_send_notifications'
            ),
        ]
        return custom_urls + urls

    def send_new_button(self, obj=None):
        """Кнопка для запуска новой рассылки"""
        url = reverse('admin:deadline_control_medical_send_notifications')
        return format_html(
            '<a class="button" href="{}" style="padding:6px 12px;background:#4caf50;">📧 Новая рассылка</a>',
            url
        )
    send_new_button.short_description = "Запуск"

    def changelist_view(self, request, extra_context=None):
        """Добавляем кнопку запуска рассылки в контекст"""
        extra_context = extra_context or {}
        extra_context['send_notifications_url'] = reverse('admin:deadline_control_medical_send_notifications')
        return super().changelist_view(request, extra_context)

    def send_notifications_view(self, request):
        """View для ручного запуска рассылки уведомлений о медосмотрах"""
        # Проверка прав доступа
        if not request.user.has_perm('deadline_control.add_medicalnotificationsendlog'):
            messages.error(request, "У вас нет прав для запуска рассылки уведомлений")
            return redirect('admin:deadline_control_medicalnotificationsendlog_changelist')

        # Получаем организации, доступные пользователю
        if request.user.is_superuser:
            organizations = Organization.objects.all()
        elif hasattr(request.user, 'profile'):
            organizations = request.user.profile.organizations.all()
        else:
            organizations = Organization.objects.none()

        if not organizations.exists():
            messages.error(request, "Нет доступных организаций для отправки уведомлений")
            return redirect('admin:deadline_control_medicalnotificationsendlog_changelist')

        # GET запрос - показываем форму
        if request.method == 'GET':
            context = {
                'title': 'Запуск рассылки уведомлений о медосмотрах',
                'organizations': organizations,
                'opts': self.model._meta,
                'has_view_permission': self.has_view_permission(request),
            }
            return render(
                request,
                'admin/deadline_control/medical_send_log/send_notifications.html',
                context
            )

        # POST запрос - запускаем отправку
        if request.method == 'POST':
            organization_id = request.POST.get('organization')
            test_mode = request.POST.get('test_mode') == 'on'
            test_emails = request.POST.get('test_emails', '').strip()

            # Валидация
            if not organization_id:
                messages.error(request, "Не выбрана организация")
                return redirect('admin:deadline_control_medical_send_notifications')

            try:
                organization = organizations.get(id=organization_id)
            except Organization.DoesNotExist:
                messages.error(request, "Организация не найдена или недоступна")
                return redirect('admin:deadline_control_medical_send_notifications')

            if test_mode and not test_emails:
                messages.error(request, "В тестовом режиме необходимо указать email адреса")
                return redirect('admin:deadline_control_medical_send_notifications')

            # Запускаем команду
            try:
                # Подготовка параметров
                cmd_args = ['--organization', str(organization.id)]
                if test_mode and test_emails:
                    cmd_args.extend(['--emails', test_emails])

                # Захватываем вывод команды
                out = StringIO()
                call_command('send_medical_notifications', *cmd_args, stdout=out)

                # Обновляем последний созданный лог
                last_log = MedicalNotificationSendLog.objects.filter(
                    organization=organization
                ).order_by('-created_at').first()

                if last_log:
                    # Помечаем как ручную отправку
                    last_log.notification_type = 'manual'
                    last_log.initiated_by = request.user
                    last_log.save()

                    # Формируем сообщение на основе статуса
                    if last_log.status == 'completed':
                        messages.success(
                            request,
                            f'✅ Рассылка успешно выполнена для {organization.short_name_ru}. '
                            f'Отправлено: {last_log.successful_count}, '
                            f'Ошибок: {last_log.failed_count}, '
                            f'Пропущено: {last_log.skipped_count}'
                        )
                    elif last_log.status == 'partial':
                        messages.warning(
                            request,
                            f'⚠️ Рассылка выполнена частично для {organization.short_name_ru}. '
                            f'Успешно: {last_log.successful_count}, '
                            f'Ошибок: {last_log.failed_count}'
                        )
                    else:
                        messages.error(
                            request,
                            f'❌ Рассылка завершилась с ошибками для {organization.short_name_ru}. '
                            f'Проверьте детали в логе.'
                        )

                    # Перенаправляем на страницу просмотра лога
                    return redirect('admin:deadline_control_medicalnotificationsendlog_change', last_log.pk)
                else:
                    messages.warning(
                        request,
                        'Команда выполнена, но лог не найден. Проверьте настройки email.'
                    )
                    return redirect('admin:deadline_control_medicalnotificationsendlog_changelist')

            except Exception as e:
                messages.error(
                    request,
                    f'❌ Ошибка при запуске рассылки: {str(e)}'
                )
                return redirect('admin:deadline_control_medical_send_notifications')
