# deadline_control/admin/equipment_type.py
from django.contrib import admin
from deadline_control.models import EquipmentType


@admin.register(EquipmentType)
class EquipmentTypeAdmin(admin.ModelAdmin):
    """
    📋 Админ-панель для управления типами оборудования
    """
    list_display = [
        'name',
        'default_maintenance_period_months',
        'is_active',
        'equipment_count',
        'created_at'
    ]
    list_filter = ['is_active', 'created_at']
    search_fields = ['name', 'description']
    ordering = ['name']

    fieldsets = (
        ('Основная информация', {
            'fields': ('name', 'default_maintenance_period_months', 'is_active')
        }),
        ('Дополнительно', {
            'fields': ('description',),
            'classes': ('collapse',)
        }),
    )

    readonly_fields = ['created_at', 'updated_at']

    def equipment_count(self, obj):
        """Количество единиц оборудования данного типа"""
        return obj.equipment_items.count()
    equipment_count.short_description = "Кол-во оборудования"
