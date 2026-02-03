# deadline_control/models/equipment_send_log.py
"""
📧 Модели для логирования отправки журналов осмотра оборудования
"""
from django.db import models
from django.contrib.auth.models import User
from django.utils.translation import gettext_lazy as _


class EquipmentJournalSendLog(models.Model):
    """
    📧 Лог массовой рассылки журналов осмотра оборудования.

    Хранит информацию о рассылке:
    - Кто и когда запустил
    - Для какой организации
    - Тип оборудования
    - Дата осмотра
    - Общая статистика
    """

    STATUS_CHOICES = [
        ('in_progress', 'В процессе'),
        ('completed', 'Завершено успешно'),
        ('partial', 'Завершено частично'),
        ('failed', 'Ошибка'),
    ]

    organization = models.ForeignKey(
        'directory.Organization',
        on_delete=models.CASCADE,
        verbose_name="Организация",
        related_name='equipment_journal_send_logs'
    )

    initiated_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        verbose_name="Инициатор отправки",
        related_name='equipment_journal_send_logs'
    )

    # Параметры журнала
    equipment_type = models.ForeignKey(
        'EquipmentType',
        on_delete=models.CASCADE,
        verbose_name="Тип оборудования",
        related_name='journal_send_logs'
    )

    inspection_date = models.DateField(
        verbose_name="Дата осмотра",
        help_text="Дата, указанная в журнале осмотра"
    )

    # Статистика
    total_subdivisions = models.IntegerField(
        default=0,
        verbose_name="Всего подразделений"
    )

    successful_count = models.IntegerField(
        default=0,
        verbose_name="Успешно отправлено"
    )

    failed_count = models.IntegerField(
        default=0,
        verbose_name="Ошибок отправки"
    )

    skipped_count = models.IntegerField(
        default=0,
        verbose_name="Пропущено"
    )

    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='in_progress',
        verbose_name="Статус"
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Дата создания"
    )

    updated_at = models.DateTimeField(
        auto_now=True,
        verbose_name="Дата обновления"
    )

    class Meta:
        verbose_name = "📧 Журнал оборудования (рассылка)"
        verbose_name_plural = "📧 Журналы оборудования (рассылки)"
        ordering = ['-created_at']
        db_table = 'deadline_control_equipment_journal_send_log'

    def __str__(self):
        return f"Рассылка журналов {self.equipment_type.name} от {self.created_at.strftime('%d.%m.%Y %H:%M')}"

    def get_total_processed(self):
        """Возвращает общее количество обработанных подразделений"""
        return self.successful_count + self.failed_count + self.skipped_count

    def get_success_rate(self):
        """Возвращает процент успешности"""
        total = self.get_total_processed()
        if total == 0:
            return 0
        return round((self.successful_count / total) * 100, 1)


class EquipmentJournalSendDetail(models.Model):
    """
    📋 Деталь отправки журнала для конкретного подразделения.

    Хранит подробную информацию об отправке для одного подразделения:
    - Статус отправки
    - Список получателей
    - Количество оборудования
    - Причина пропуска (если пропущено)
    - Текст ошибки (если ошибка)
    """

    STATUS_CHOICES = [
        ('success', '✅ Отправлено'),
        ('failed', '❌ Ошибка'),
        ('skipped', '⏩ Пропущено'),
    ]

    SKIP_REASON_CHOICES = [
        ('no_recipients', 'Нет получателей'),
        ('no_equipment', 'Нет оборудования данного типа'),
        ('doc_generation_failed', 'Ошибка генерации документа'),
        ('template_not_found', 'Не найден шаблон письма'),
        ('email_send_failed', 'Ошибка отправки email'),
    ]

    send_log = models.ForeignKey(
        EquipmentJournalSendLog,
        on_delete=models.CASCADE,
        related_name='details',
        verbose_name="Лог рассылки"
    )

    subdivision = models.ForeignKey(
        'directory.StructuralSubdivision',
        on_delete=models.CASCADE,
        verbose_name="Подразделение",
        related_name='equipment_journal_send_details'
    )

    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        verbose_name="Статус"
    )

    # Информация о получателях и оборудовании
    recipients = models.TextField(
        default='[]',
        verbose_name="Получатели (JSON)",
        help_text="Список email адресов в формате JSON"
    )

    recipients_count = models.IntegerField(
        default=0,
        verbose_name="Количество получателей"
    )

    equipment_count = models.IntegerField(
        default=0,
        verbose_name="Количество оборудования"
    )

    # Email
    email_subject = models.CharField(
        max_length=500,
        blank=True,
        verbose_name="Тема письма"
    )

    # Ошибки и причины пропуска
    skip_reason = models.CharField(
        max_length=50,
        blank=True,
        choices=SKIP_REASON_CHOICES,
        verbose_name="Причина пропуска"
    )

    error_message = models.TextField(
        blank=True,
        verbose_name="Сообщение об ошибке"
    )

    sent_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Дата отправки"
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Дата создания"
    )

    def get_recipients_list(self):
        """Возвращает список получателей из JSON"""
        import json
        try:
            return json.loads(self.recipients)
        except Exception:
            return []

    def get_skip_reason_display_custom(self):
        """Возвращает отображение причины пропуска"""
        if self.skip_reason:
            return dict(self.SKIP_REASON_CHOICES).get(self.skip_reason, self.skip_reason)
        return self.error_message if self.error_message else '-'

    class Meta:
        verbose_name = "📋 Деталь рассылки журнала"
        verbose_name_plural = "📋 Детали рассылок журналов"
        ordering = ['subdivision__name']
        db_table = 'deadline_control_equipment_journal_send_detail'

    def __str__(self):
        status_icon = {
            'success': '✅',
            'failed': '❌',
            'skipped': '⏩'
        }.get(self.status, '❓')
        return f"{status_icon} {self.subdivision.name} - {self.get_status_display()}"
