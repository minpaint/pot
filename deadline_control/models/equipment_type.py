# deadline_control/models/equipment_type.py
from django.db import models


class EquipmentType(models.Model):
    """
    📋 Справочник типов оборудования
    Определяет типы оборудования и периодичность ТО по умолчанию
    """
    name = models.CharField(
        "Название типа оборудования",
        max_length=100,
        unique=True,
        help_text="Например: Лестница, Погрузчик, Автомобиль"
    )
    default_maintenance_period_months = models.PositiveIntegerField(
        "Периодичность ТО по умолчанию (месяцев)",
        default=12,
        help_text="Стандартная периодичность технического обслуживания для данного типа оборудования"
    )
    description = models.TextField(
        "Описание",
        blank=True,
        help_text="Дополнительная информация о типе оборудования"
    )
    is_active = models.BooleanField(
        "Активен",
        default=True,
        help_text="Неактивные типы не отображаются при выборе"
    )
    created_at = models.DateTimeField("Дата создания", auto_now_add=True)
    updated_at = models.DateTimeField("Дата обновления", auto_now=True)

    def __str__(self):
        return f"{self.name} ({self.default_maintenance_period_months} мес.)"

    class Meta:
        verbose_name = "🔧 Тип оборудования"
        verbose_name_plural = "🔧 Типы оборудования"
        app_label = 'deadline_control'
        ordering = ['name']
