# deadline_control/admin/email_settings.py

from django.contrib import admin
from django.utils.html import format_html
from django.core.mail import send_mail
from django.contrib import messages
from deadline_control.models import EmailSettings
from directory.admin.mixins.org_filter import apply_session_org_filter


@admin.register(EmailSettings)
class EmailSettingsAdmin(admin.ModelAdmin):
    """Админка для настроек SMTP"""

    list_display = (
        "organization",
        "email_host",
        "email_port",
        "email_host_user",
        "status_badge",
        "recipient_count",
        "test_email_button",
    )
    list_filter = ("is_active", "email_use_tls", "email_use_ssl")
    search_fields = ("organization__short_name_ru", "organization__full_name_ru", "email_host", "email_host_user")

    fieldsets = (
        ('Организация', {
            'fields': ('organization',)
        }),
        ('🔌 SMTP Сервер', {
            'fields': (
                'email_host',
                'email_port',
                ('email_use_tls', 'email_use_ssl'),
            ),
            'description': '<strong>Популярные SMTP серверы:</strong><br>'
                          '• Gmail: smtp.gmail.com, порт 587, TLS<br>'
                          '• Яндекс: smtp.yandex.ru, порт 465, SSL<br>'
                          '• Mail.ru: smtp.mail.ru, порт 465, SSL<br>'
                          '• Office365: smtp.office365.com, порт 587, TLS'
        }),
        ('🔐 Аутентификация', {
            'fields': (
                'email_host_user',
                'email_host_password',
                'default_from_email',
            ),
            'description': '<strong>⚠️ Важно для Gmail:</strong><br>'
                          '1. Включите двухфакторную аутентификацию<br>'
                          '2. Создайте "Пароль приложения": '
                          '<a href="https://myaccount.google.com/apppasswords" target="_blank">https://myaccount.google.com/apppasswords</a><br>'
                          '3. Используйте этот 16-символьный пароль (не пароль от аккаунта!)'
        }),
        ('📬 Получатели уведомлений', {
            'fields': (
                'recipient_emails',
                'instruction_journal_recipients',
            ),
            'description': '<strong>Настройка получателей уведомлений</strong><br>'
                          '• <strong>Общие получатели:</strong> медосмотры и другие уведомления на уровне организации<br>'
                          '• <strong>Журналы инструктажей:</strong> специализированные получатели для рассылки образцов '
                          '(если пусто - используются ТОЛЬКО получатели из подразделений: SubdivisionEmail + ответственные за ОТ, '
                          '<strong>БЕЗ</strong> общих получателей)<br>'
                          '<em>Каждый email адрес указывается с новой строки.</em><br><br>'
                          '<strong>💡 Совет:</strong> Оставьте поле "Журналы инструктажей" пустым, если хотите избежать массовой '
                          'рассылки на общие адреса (HR, директор) при отправке образцов для всех подразделений.'
        }),
        ('🚀 Настройки массовой рассылки', {
            'fields': (
                'email_delay_seconds',
                'max_retry_attempts',
                'connection_timeout',
            ),
            'description': '<strong>⚡ Оптимизация массовой отправки email</strong><br>'
                          '• <strong>Задержка между письмами:</strong> пауза для защиты от блокировки SMTP провайдером '
                          '(Gmail/Yandex: рекомендуется 1-2 сек, лимит 500 писем/день)<br>'
                          '• <strong>Макс. попыток повтора:</strong> количество автоматических повторных попыток при временных ошибках '
                          '(рекомендуется 3)<br>'
                          '• <strong>Таймаут соединения:</strong> максимальное время ожидания ответа от SMTP сервера '
                          '(рекомендуется 30 сек)<br><br>'
                          '<strong>📊 Производительность:</strong> С этими настройками отправка 100 писем займёт ~1.7 мин '
                          'вместо 4 мин (ускорение в 2.45×) + защита от бана провайдера.'
        }),
        ('⚙️ Дополнительные настройки', {
            'fields': (
                'is_active',
                'email_backend',
            ),
            'classes': ('collapse',),
        }),
    )

    def status_badge(self, obj):
        """Бейдж статуса активности"""
        if obj.is_active:
            return format_html(
                '<span style="background:#4caf50;color:white;padding:4px 12px;border-radius:6px;font-weight:600;">✓ Активно</span>'
            )
        return format_html(
            '<span style="background:#9e9e9e;color:white;padding:4px 12px;border-radius:6px;font-weight:600;">✗ Отключено</span>'
        )

    status_badge.short_description = "Статус"

    def recipient_count(self, obj):
        """Количество получателей"""
        count = len(obj.get_recipient_list())
        if count > 0:
            return format_html(
                '<span style="background:#2196f3;color:white;padding:2px 8px;border-radius:6px;font-weight:600;">{} адр.</span>',
                count
            )
        return format_html(
            '<span style="background:#ff9800;color:white;padding:2px 8px;border-radius:6px;font-weight:600;">Не указаны</span>'
        )

    recipient_count.short_description = "Получатели"

    def test_email_button(self, obj):
        """Кнопка для отправки тестового письма"""
        if obj.is_active and obj.email_host:
            return format_html(
                '<a class="button" href="{}?action=test_email" style="padding:4px 12px;">Тест email</a>',
                f'/admin/deadline_control/emailsettings/{obj.pk}/change/'
            )
        return "—"

    test_email_button.short_description = "Действия"

    def get_queryset(self, request):
        """Фильтруем по организациям пользователя"""
        qs = super().get_queryset(request)
        if not request.user.is_superuser and hasattr(request.user, 'profile'):
            allowed_orgs = request.user.profile.organizations.all()
            qs = qs.filter(organization__in=allowed_orgs)
        qs = apply_session_org_filter(request, qs)
        return qs.select_related('organization')

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        """Показываем только организации, доступные пользователю"""
        if db_field.name == "organization":
            if not request.user.is_superuser and hasattr(request.user, 'profile'):
                kwargs["queryset"] = request.user.profile.organizations.all()
        return super().formfield_for_foreignkey(db_field, request, **kwargs)

    def change_view(self, request, object_id, form_url='', extra_context=None):
        """Обработка кастомных действий через GET параметры"""
        from django.shortcuts import redirect
        from django.urls import reverse

        # Проверяем, есть ли кастомное действие в GET параметрах
        if "action" in request.GET and request.GET["action"] == "test_email":
            # Получаем объект
            obj = self.get_object(request, object_id)
            if obj:
                # Выполняем действие
                self.send_test_email(request, obj)
                # Перенаправляем обратно на changelist
                return redirect(reverse('admin:deadline_control_emailsettings_changelist'))

        # Вызываем стандартный change_view
        return super().change_view(request, object_id, form_url, extra_context)

    def send_test_email(self, request, obj):
        """Отправка тестового письма"""
        if not obj.is_active:
            messages.error(request, "❌ Email настройки отключены. Включите их перед тестированием.")
            return

        if not obj.email_host:
            messages.error(request, "❌ SMTP сервер не указан.")
            return

        # Получаем список получателей
        recipients = obj.get_recipient_list()
        if not recipients:
            messages.warning(
                request,
                "⚠️ Получатели не указаны. Отправляю тестовое письмо на адрес администратора."
            )
            recipients = [request.user.email] if request.user.email else []

        if not recipients:
            messages.error(request, "❌ Не указаны получатели и у вас нет email адреса в профиле.")
            return

        try:
            # Получаем подключение с настройками организации
            connection = obj.get_connection()

            # Отправляем тестовое письмо
            send_mail(
                subject=f'🧪 Тест настроек Email - {obj.organization.short_name_ru}',
                message=f'''Это тестовое письмо для проверки настроек SMTP.

Организация: {obj.organization.full_name_ru}
SMTP сервер: {obj.email_host}:{obj.email_port}
Отправитель: {obj.default_from_email or obj.email_host_user}

Если вы получили это письмо - настройки работают корректно! ✅

---
OT-online Система управления охраной труда
''',
                from_email=obj.default_from_email or obj.email_host_user,
                recipient_list=recipients,
                connection=connection,
                fail_silently=False,
            )

            messages.success(
                request,
                f'✅ Тестовое письмо успешно отправлено на {len(recipients)} адрес(ов): {", ".join(recipients)}'
            )

        except Exception as e:
            messages.error(
                request,
                f'❌ Ошибка при отправке тестового письма: {str(e)}'
            )

    def save_model(self, request, obj, form, change):
        """Сохранение модели с дополнительной валидацией"""
        try:
            obj.full_clean()
            super().save_model(request, obj, form, change)
            if not change:  # Только при создании
                messages.info(
                    request,
                    '💡 Настройки созданы. Не забудьте проверить их с помощью кнопки "Тест email".'
                )
        except Exception as e:
            messages.error(request, f'Ошибка при сохранении: {str(e)}')
