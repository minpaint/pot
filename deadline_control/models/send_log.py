# deadline_control/models/send_log.py

from django.db import models
from django.contrib.auth import get_user_model
from django.utils import timezone

User = get_user_model()


class InstructionJournalSendLog(models.Model):
    """
    📧 Лог массовой рассылки образцов журналов инструктажей.

    Хранит общую информацию о рассылке:
    - Кто и когда запустил
    - Для какой организации
    - Параметры инструктажа (дата, вид, причина)
    - Общая статистика (успешно/ошибки/пропуски)
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
        related_name='instruction_send_logs',
        verbose_name="Организация"
    )

    initiated_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        related_name='initiated_instruction_sends',
        verbose_name="Инициатор"
    )

    # Параметры инструктажа
    briefing_date = models.DateField(
        verbose_name="Дата инструктажа",
        help_text="Дата проведения повторного инструктажа"
    )

    briefing_type = models.CharField(
        max_length=100,
        default="Повторный",
        verbose_name="Вид инструктажа",
        help_text="Повторный, Внеплановый и т.д."
    )

    briefing_reason = models.TextField(
        blank=True,
        default='',
        verbose_name="Причина проведения",
        help_text="Причина проведения инструктажа"
    )

    # Статистика
    total_subdivisions = models.IntegerField(
        default=0,
        verbose_name="Всего подразделений",
        help_text="Общее количество подразделений в организации"
    )

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
        help_text="Пропущено (нет получателей или сотрудников)"
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
        verbose_name = "📧 Инструктажи"
        verbose_name_plural = "📧 Инструктажи"
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['organization', '-created_at']),
            models.Index(fields=['initiated_by', '-created_at']),
            models.Index(fields=['status']),
        ]

    def __str__(self):
        return f"{self.organization.short_name_ru} - {self.created_at.strftime('%d.%m.%Y %H:%M')}"

    def get_total_processed(self):
        """Возвращает общее количество обработанных подразделений"""
        return self.successful_count + self.failed_count + self.skipped_count

    def get_success_rate(self):
        """Возвращает процент успешности"""
        total = self.get_total_processed()
        if total == 0:
            return 0
        return round((self.successful_count / total) * 100, 1)


class InstructionJournalSendDetail(models.Model):
    """
    📋 Деталь отправки образца журнала для конкретного подразделения или отдела.

    Хранит информацию о конкретной попытке отправки:
    - Подразделение/отдел
    - Статус (успех/ошибка/пропуск)
    - Получатели
    - Причина пропуска или текст ошибки
    """

    STATUS_CHOICES = [
        ('success', '✅ Отправлено'),
        ('failed', '❌ Ошибка'),
        ('skipped', '⏩ Пропущено'),
    ]

    SKIP_REASON_CHOICES = [
        ('no_recipients', 'Нет получателей'),
        ('no_employees', 'Нет сотрудников с инструкциями'),
        ('doc_generation_failed', 'Ошибка генерации документа'),
        ('template_not_found', 'Не найден шаблон письма'),
        ('email_send_failed', 'Ошибка отправки email'),
    ]

    send_log = models.ForeignKey(
        InstructionJournalSendLog,
        on_delete=models.CASCADE,
        related_name='details',
        verbose_name="Лог рассылки"
    )

    subdivision = models.ForeignKey(
        'directory.StructuralSubdivision',
        on_delete=models.CASCADE,
        related_name='instruction_send_details',
        verbose_name="Подразделение"
    )

    department = models.ForeignKey(
        'directory.Department',
        on_delete=models.CASCADE,
        related_name='instruction_send_details',
        verbose_name="Отдел",
        null=True,
        blank=True,
        help_text="Если не указан - отправка для основного подразделения"
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

    employees_count = models.IntegerField(
        default=0,
        verbose_name="Количество сотрудников",
        help_text="Количество сотрудников в сгенерированном документе"
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
        verbose_name = "📋 Деталь отправки"
        verbose_name_plural = "📋 Детали отправок"
        ordering = ['subdivision__name', 'department__name']
        indexes = [
            models.Index(fields=['send_log', 'status']),
            models.Index(fields=['subdivision']),
            models.Index(fields=['department']),
        ]

    def __str__(self):
        status_icon = dict(self.STATUS_CHOICES).get(self.status, self.status)
        dept_name = f" / {self.department.name}" if self.department else ""
        return f"{self.subdivision.name}{dept_name} - {status_icon}"

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
