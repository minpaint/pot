from django.db import models
from django.db.models.signals import post_save
from django.dispatch import receiver
from .siz_issued import SIZIssued  # Реэкспорт для обратной совместимости импорта


class SIZ(models.Model):
    """
    🛡️ Модель средства индивидуальной защиты (СИЗ)
    """
    name = models.CharField(
        "Наименование СИЗ",
        max_length=255
    )
    classification = models.CharField(
        "Классификация (маркировка)",
        max_length=100,
        blank=True,
        default='',
        help_text="Маркировка СИЗ по защитным свойствам или конструктивным особенностям"
    )
    unit = models.CharField(
        "Единица измерения",
        max_length=50,
        default="шт."
    )
    wear_period = models.PositiveIntegerField(
        "Срок носки в месяцах",
        default=12,
        help_text="0 означает особые случаи (До износа, Дежурные и т.д.)"
    )
    wear_type = models.CharField(
        "Тип выдачи",
        max_length=50,
        blank=True,
        default='',
        help_text="Для wear_period=0: 'До износа', 'Дежурный', 'Дежурная', 'Дежурные'"
    )
    cost = models.DecimalField(
        "Стоимость",
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True
    )

    class Meta:
        verbose_name = "🦺 Средство индивидуальной защиты"
        verbose_name_plural = "🦺 Средства индивидуальной защиты"
        ordering = ['name']

    def __str__(self):
        return f"{self.name} ({self.classification})"

    @property
    def wear_period_display(self):
        """🕒 Отображение срока носки (с учетом особых случаев)"""
        if self.wear_period == 0:
            return self.wear_type if self.wear_type else "До износа"
        return f"{self.wear_period} мес."


class ProfessionSIZNorm(models.Model):
    """
    📖 Эталонные нормы СИЗ для профессии (справочник).
    Используется как fallback, если у конкретной должности нет переопределённых норм.
    """
    profession_name = models.CharField(
        "Название профессии",
        max_length=255,
        db_index=True,
        help_text="Точное название профессии (регистронезависимо)"
    )
    siz = models.ForeignKey(
        SIZ,
        on_delete=models.CASCADE,
        related_name="profession_norms",
        verbose_name="СИЗ"
    )
    quantity = models.PositiveIntegerField(
        "Количество",
        default=1
    )
    condition = models.CharField(
        "Условие выдачи",
        max_length=255,
        blank=True,
        default='',
        help_text="Например: 'При влажной уборке помещений'"
    )
    order = models.PositiveIntegerField(
        "Порядок отображения",
        default=0
    )

    class Meta:
        verbose_name = "📖 Эталонная норма СИЗ профессии"
        verbose_name_plural = "📖 1. Эталонные нормы СИЗ (справочник)"
        unique_together = [['profession_name', 'siz', 'condition']]
        ordering = ['profession_name', 'condition', 'order', 'siz__name']
        indexes = [
            models.Index(fields=['profession_name'], name='prof_siz_name_idx'),
        ]

    def __str__(self):
        return f"{self.profession_name} — {self.siz.name}"


class SIZNorm(models.Model):
    """
    📋 Норма выдачи СИЗ для профессии
    """
    position = models.ForeignKey(
        'directory.Position',
        on_delete=models.CASCADE,
        related_name="siz_norms",
        verbose_name="Профессия/должность"
    )
    siz = models.ForeignKey(
        SIZ,
        on_delete=models.CASCADE,
        related_name="norms",
        verbose_name="СИЗ"
    )
    quantity = models.PositiveIntegerField(
        "Количество",
        default=1
    )
    condition = models.CharField(
        "Условие выдачи",
        max_length=255,
        blank=True,
        help_text="Например: 'При влажной уборке помещений', 'При работе на высоте' и т.д."
    )
    order = models.PositiveIntegerField(
        "Порядок отображения",
        default=0
    )

    class Meta:
        verbose_name = "📏 Норма выдачи СИЗ"
        verbose_name_plural = "📏 Нормы выдачи СИЗ"
        # Возвращаем прежнее unique_together вместо constraints
        unique_together = [['position', 'siz', 'condition']]
        ordering = ['position', 'condition', 'order', 'siz__name']

    def __str__(self):
        if self.condition:
            return f"{self.position} - {self.siz} ({self.condition})"
        return f"{self.position} - {self.siz}"

    @property
    def get_condition_display(self):
        """📝 Получение текста условия выдачи"""
        return self.condition or "Основная норма"


# Сигнал для автоматического копирования норм СИЗ
@receiver(post_save, sender='directory.Position')
def copy_reference_siz_norms(sender, instance, created, **kwargs):
    """
    🔄 Автоматическое копирование эталонных норм СИЗ при создании новой должности

    Функция используется только в исключительных случаях, когда в разных
    организациях для одинаковых профессий требуются разные СИЗ.

    Копирование выполняется только при точном совпадении названий должностей.
    """
    # Эта функция не выполняет автоматического копирования при создании должности
    # Копирование запускается вручную через админку при необходимости
    pass
