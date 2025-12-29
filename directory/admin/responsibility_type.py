# directory/admin/responsibility_type.py

from django.contrib import admin
from directory.models import ResponsibilityType


@admin.register(ResponsibilityType)
class ResponsibilityTypeAdmin(admin.ModelAdmin):
    """
    📋 Администрирование видов ответственных
    """
    list_display = ('name', 'order', 'is_active')
    list_editable = ('order', 'is_active')
    list_filter = ('is_active',)
    search_fields = ('name', 'description')
    ordering = ('order', 'name')

    fieldsets = (
        ('Основная информация', {
            'fields': ('name', 'description')
        }),
        ('Настройки', {
            'fields': ('order', 'is_active')
        }),
    )
