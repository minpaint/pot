# deadline_control/models/medical_send_log.py

from django.db import models
from django.contrib.auth import get_user_model
from django.utils import timezone

User = get_user_model()


class MedicalNotificationSendLog(models.Model):
    """
    🏥 Лог массовой рассылки уведомлений о медицинских осмотрах.

    Хранит общую информацию о рассылке:
    - Кто и когда запустил
    - Для какой организации
    - Статистика по медосмотрам (без даты, просроченные, предстоящие)
    - Общая статистика (успешно/ошибки/пропуски)
    """

    STATUS_CHOICES = [
        ('in_progress', 'В процессе'),
        ('completed', 'Завершено успешно'),
        ('partial', 'Завершено частично'),
        ('failed', 'Ошибка'),
    ]

    NOTIFICATION_TYPE_CHOICES = [
        ('scheduled', '⏰ Плановая рассылка'),
        ('manual', '👤 Ручная отправка'),
    ]

    organization = models.ForeignKey(
        'directory.Organization',
        on_delete=models.CASCADE,
        related_name='medical_notification_logs',
        verbose_name="Организация"
    )

    initiated_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='initiated_medical_notifications',
        verbose_name="Инициатор",
        help_text="NULL для автоматических рассылок по расписанию"
    )

    # Тип уведомления
    notification_type = models.CharField(
        max_length=20,
        choices=NOTIFICATION_TYPE_CHOICES,
        default='scheduled',
        verbose_name="Тип уведомления"
    )

    # Статистика медосмотров
    no_date_count = models.IntegerField(
        default=0,
        verbose_name="Без даты МО",
        help_text="Количество сотрудников без даты медосмотра"
    )

    expired_count = models.IntegerField(
        default=0,
        verbose_name="Просроченные МО",
        help_text="Количество сотрудников с просроченным медосмотром"
    )

    upcoming_count = models.IntegerField(
        default=0,
        verbose_name="Предстоящие МО",
        help_text="Количество сотрудников с предстоящим медосмотром"
    )

    # Статистика отправки
    successful_count = models.IntegerField(
        default=0,
        verbose_name="Успешных отправок"
    )

    failed_count = models.IntegerField(
        default=0,
        verbose_name="Ошибок отправки"
    )

    skipped_count = models.IntegerField(
        default=0,
        verbose_name="Пропущено",
        help_text="Пропущено (нет получателей или данных)"
    )

    # Шаблон email (опционально)
    email_template = models.ForeignKey(
        'EmailTemplate',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='medical_notification_logs',
        verbose_name="Шаблон письма",
        help_text="Использованный шаблон email (если применим)"
    )

    # Статус и метаданные
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='in_progress',
        verbose_name="Статус"
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Дата запуска"
    )

    updated_at = models.DateTimeField(
        auto_now=True,
        verbose_name="Дата обновления"
    )

    class Meta:
        verbose_name = "🏥 Медосмотры"
        verbose_name_plural = "🏥 Медосмотры"
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['organization', '-created_at']),
            models.Index(fields=['initiated_by', '-created_at']),
            models.Index(fields=['status']),
            models.Index(fields=['notification_type']),
        ]

    def __str__(self):
        notification_label = dict(self.NOTIFICATION_TYPE_CHOICES).get(
            self.notification_type, self.notification_type
        )
        return (
            f"{self.organization.short_name_ru} - "
            f"{notification_label} - "
            f"{self.created_at.strftime('%d.%m.%Y %H:%M')}"
        )

    def get_total_employees(self):
        """Возвращает общее количество сотрудников в уведомлении"""
        return self.no_date_count + self.expired_count + self.upcoming_count

    def get_total_processed(self):
        """Возвращает общее количество обработанных отправок"""
        return self.successful_count + self.failed_count + self.skipped_count

    def get_success_rate(self):
        """Возвращает процент успешности"""
        total = self.get_total_processed()
        if total == 0:
            return 0
        return round((self.successful_count / total) * 100, 1)


class MedicalNotificationSendDetail(models.Model):
    """
    📋 Деталь отправки медицинского уведомления для организации.

    Для медицинских уведомлений:
    - Один detail на организацию (не по подразделениям)
    - Агрегированная статистика
    - Без вложений
    """

    STATUS_CHOICES = [
        ('success', '✅ Отправлено'),
        ('failed', '❌ Ошибка'),
        ('skipped', '⏭️ Пропущено'),
    ]

    SKIP_REASON_CHOICES = [
        ('no_recipients', 'Нет получателей'),
        ('no_data', 'Нет данных для отправки'),
        ('template_not_found', 'Не найден шаблон письма'),
        ('email_send_failed', 'Ошибка отправки email'),
    ]

    send_log = models.ForeignKey(
        MedicalNotificationSendLog,
        on_delete=models.CASCADE,
        related_name='details',
        verbose_name="Лог рассылки"
    )

    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        verbose_name="Статус"
    )

    # Информация о получателях
    recipients = models.TextField(
        default='[]',
        verbose_name="Получатели (JSON)",
        help_text='JSON список email адресов: ["a@test.com", "b@test.com"]'
    )

    recipients_count = models.IntegerField(
        default=0,
        verbose_name="Количество получателей"
    )

    # Статистика для этой отправки
    employees_total = models.IntegerField(
        default=0,
        verbose_name="Всего сотрудников",
        help_text="Общее количество сотрудников в уведомлении"
    )

    no_date_count = models.IntegerField(
        default=0,
        verbose_name="Без даты МО"
    )

    expired_count = models.IntegerField(
        default=0,
        verbose_name="Просроченные МО"
    )

    upcoming_count = models.IntegerField(
        default=0,
        verbose_name="Предстоящие МО"
    )

    # Информация об отправке
    email_subject = models.CharField(
        max_length=500,
        blank=True,
        default='',
        verbose_name="Тема письма"
    )

    # Информация об ошибке/пропуске
    skip_reason = models.CharField(
        max_length=50,
        blank=True,
        default='',
        choices=SKIP_REASON_CHOICES,
        verbose_name="Причина пропуска"
    )

    error_message = models.TextField(
        blank=True,
        default='',
        verbose_name="Текст ошибки"
    )

    # Метаданные
    sent_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Дата отправки",
        help_text="Дата и время фактической отправки письма"
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Дата создания"
    )

    class Meta:
        verbose_name = "📋 Деталь рассылки медицинского уведомления"
        verbose_name_plural = "📋 Детали рассылок медицинских уведомлений"
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['send_log', 'status']),
        ]

    def __str__(self):
        status_icon = dict(self.STATUS_CHOICES).get(self.status, self.status)
        return f"Отправка медуведомления - {status_icon}"

    def get_recipients_list(self):
        """Возвращает список получателей из JSON"""
        import json
        try:
            return json.loads(self.recipients)
        except:
            return []

    def get_skip_reason_display_custom(self):
        """Возвращает красивое отображение причины пропуска"""
        if self.skip_reason:
            return dict(self.SKIP_REASON_CHOICES).get(self.skip_reason, self.skip_reason)
        return self.error_message if self.error_message else '—'
