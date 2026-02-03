# deadline_control/models/key_deadline_send_log.py

from django.db import models
from django.contrib.auth import get_user_model
from django.utils import timezone

User = get_user_model()


class KeyDeadlineSendLog(models.Model):
    """
    ⚙️ Лог массовой рассылки уведомлений о ключевых мероприятиях.

    Хранит общую информацию о рассылке:
    - Кто и когда запустил
    - Для какой организации
    - Статистика по категориям и мероприятиям
    - Общая статистика (успешно/ошибки/пропуски)
    """

    STATUS_CHOICES = [
        ('in_progress', 'В процессе'),
        ('completed', 'Завершено успешно'),
        ('partial', 'Завершено частично'),
        ('failed', 'Ошибка'),
    ]

    NOTIFICATION_TYPE_CHOICES = [
        ('scheduled', '🕐 Плановая рассылка'),
        ('manual', '👤 Ручная отправка'),
    ]

    organization = models.ForeignKey(
        'directory.Organization',
        on_delete=models.CASCADE,
        related_name='key_deadline_logs',
        verbose_name="Организация"
    )

    initiated_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='initiated_key_deadline_sends',
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

    # Статистика категорий и мероприятий
    total_categories = models.IntegerField(
        default=0,
        verbose_name="Всего категорий",
        help_text="Общее количество активных категорий в организации"
    )

    overdue_items_count = models.IntegerField(
        default=0,
        verbose_name="Просроченных мероприятий",
        help_text="Количество просроченных мероприятий"
    )

    upcoming_items_count = models.IntegerField(
        default=0,
        verbose_name="Предстоящих мероприятий",
        help_text="Количество предстоящих мероприятий (в течение 30 дней)"
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
        related_name='key_deadline_logs',
        verbose_name="Шаблон письма",
        help_text="Использованный шаблон email (если применим)"
    )

    # Информация о получателях
    recipients = models.TextField(
        default='[]',
        verbose_name="Получатели (JSON)",
        help_text='JSON список email адресов'
    )

    recipients_count = models.IntegerField(
        default=0,
        verbose_name="Количество получателей"
    )

    # Информация об отправке
    email_subject = models.CharField(
        max_length=500,
        blank=True,
        default='',
        verbose_name="Тема письма"
    )

    error_message = models.TextField(
        blank=True,
        default='',
        verbose_name="Текст ошибки"
    )

    # Статус и метаданные
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='in_progress',
        verbose_name="Статус"
    )

    sent_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Дата отправки",
        help_text="Дата и время фактической отправки письма"
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
        verbose_name = "⚙️ Ключевые события"
        verbose_name_plural = "⚙️ Ключевые события"
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

    def get_total_items(self):
        """Возвращает общее количество мероприятий в уведомлении"""
        return self.overdue_items_count + self.upcoming_items_count

    def get_total_processed(self):
        """Возвращает общее количество обработанных отправок"""
        return self.successful_count + self.failed_count + self.skipped_count

    def get_success_rate(self):
        """Возвращает процент успешности"""
        total = self.get_total_processed()
        if total == 0:
            return 0
        return round((self.successful_count / total) * 100, 1)

    def get_recipients_list(self):
        """Возвращает список получателей из JSON"""
        import json
        try:
            return json.loads(self.recipients)
        except:
            return []
