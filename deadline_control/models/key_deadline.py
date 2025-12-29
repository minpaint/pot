# deadline_control/models/key_deadline.py
import calendar
from django.db import models
from django.core.exceptions import ValidationError
from django.utils import timezone
from directory.models import Organization


class KeyDeadlineCategory(models.Model):
    """
    📋 Справочник категорий ключевых сроков.
    Например: "Повторный инструктаж", "Периодическая проверка знаний" и т.д.

    Категории общие для всех организаций, с эталонной периодичностью.
    Каждое мероприятие может переопределить периодичность.
    """
    name = models.CharField(
        "Название категории",
        max_length=255,
        unique=True,
        help_text="Например: 'Повторный инструктаж', 'Аттестация рабочих мест'"
    )
    periodicity_months = models.PositiveIntegerField(
        "Периодичность (месяцев)",
        help_text="Периодичность по умолчанию для мероприятий этой категории",
        null=True,
        blank=True
    )
    icon = models.CharField(
        "Иконка",
        max_length=10,
        default="📋",
        help_text="Emoji иконка для отображения в интерфейсе"
    )

    def __str__(self):
        return self.name

    def clean(self):
        """Валидация модели"""
        if self.periodicity_months and self.periodicity_months < 1:
            raise ValidationError({
                'periodicity_months': 'Периодичность должна быть не менее 1 месяца'
            })

    class Meta:
        verbose_name = "📋 Категория"
        verbose_name_plural = "📋 Категории (справочник)"
        app_label = 'deadline_control'
        ordering = ['name']


class KeyDeadlineItem(models.Model):
    """
    📅 Конкретное мероприятие ключевых сроков организации.
    Привязано к организации и категории.
    Периодичность берется из мероприятия, если указана, иначе из категории.
    """
    organization = models.ForeignKey(
        'directory.Organization',
        on_delete=models.CASCADE,
        related_name='key_deadline_items',
        verbose_name="Организация",
        null=True,  # Временно для миграции
        blank=True
    )
    category = models.ForeignKey(
        KeyDeadlineCategory,
        on_delete=models.PROTECT,
        related_name="items",
        verbose_name="Категория"
    )
    name = models.CharField(
        "Наименование мероприятия",
        max_length=500,
        help_text="Например: 'Испытание лестниц на складе'"
    )
    current_date = models.DateField(
        "Дата проведения",
        help_text="Дата последнего/текущего проведения мероприятия"
    )
    next_date = models.DateField(
        "Дата следующего проведения",
        blank=True,
        null=True,
        editable=False,
        help_text="Автоматически рассчитывается на основе даты проведения и периодичности"
    )
    periodicity_months = models.PositiveIntegerField(
        "Срок проведения (месяцев)",
        null=True,
        blank=True,
        help_text="Переопределяет периодичность из категории. Если пусто - берется из категории"
    )
    responsible_person = models.CharField(
        "Ответственное лицо",
        max_length=255,
        blank=True,
        help_text="ФИО или email ответственного за проведение мероприятия"
    )
    is_active = models.BooleanField(
        "Активно",
        default=True,
        help_text="Неактивные мероприятия не участвуют в рассылках уведомлений"
    )
    notes = models.TextField("Примечания", blank=True)

    def __str__(self):
        return f"{self.name} ({self.category.name})"

    @staticmethod
    def _add_months(source_date, months):
        """
        Прибавляет к дате заданное число месяцев, корректно обрабатывая конец месяца.
        """
        month = source_date.month - 1 + months
        year = source_date.year + month // 12
        month = month % 12 + 1
        day = min(source_date.day, calendar.monthrange(year, month)[1])
        return source_date.replace(year=year, month=month, day=day)

    def calculate_next_date(self):
        """
        Вычисляет следующую дату проведения мероприятия.
        Периодичность: сначала проверяется у мероприятия, если пусто - берется из категории.
        """
        if self.current_date and self.category_id:
            # Используем периодичность из мероприятия, если указана, иначе из категории
            periodicity = self.periodicity_months or self.category.periodicity_months
            if periodicity:
                return self._add_months(self.current_date, periodicity)
        return None

    def days_until_next(self):
        """
        Возвращает количество дней до следующего проведения.
        Отрицательное значение означает просрочку.
        """
        if not self.next_date:
            return None
        return (self.next_date - timezone.now().date()).days

    def is_overdue(self):
        """Проверяет, просрочено ли мероприятие"""
        days = self.days_until_next()
        return days is not None and days < 0

    def days_overdue(self):
        """Возвращает количество просроченных дней (положительное число)"""
        days = self.days_until_next()
        if days is None or days >= 0:
            return 0
        return abs(days)

    def is_upcoming(self, warning_days=14):
        """Проверяет, приближается ли срок (по умолчанию за 14 дней)"""
        days = self.days_until_next()
        return days is not None and 0 <= days <= warning_days

    def save(self, *args, **kwargs):
        """Автоматически рассчитываем следующую дату при сохранении"""
        self.next_date = self.calculate_next_date()
        super().save(*args, **kwargs)

    class Meta:
        verbose_name = "📅 Ключевой срок"
        verbose_name_plural = "📅 Ключевые сроки"
        app_label = 'deadline_control'
        ordering = ['next_date', 'name']


class OrganizationKeyDeadline(Organization):
    """
    Proxy-модель для отображения организаций в разделе "Ключевые сроки"
    Используется для группировки мероприятий по организациям в админке
    """
    class Meta:
        proxy = True
        verbose_name = "📅 Организация"
        verbose_name_plural = "📅 Ключевые сроки"
        app_label = 'deadline_control'
