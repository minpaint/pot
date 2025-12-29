# deadline_control/admin/email_template.py

from django.contrib import admin
from django.utils.html import format_html
from django.db import models
from deadline_control.models import EmailTemplateType, EmailTemplate


@admin.register(EmailTemplateType)
class EmailTemplateTypeAdmin(admin.ModelAdmin):
    """Админка для типов шаблонов писем"""

    list_display = (
        'name',
        'code',
        'templates_count',
        'is_active',
        'created_at',
    )
    list_filter = ('is_active', 'created_at')
    search_fields = ('name', 'code', 'description')
    readonly_fields = ('created_at', 'updated_at')

    fieldsets = (
        ('Основная информация', {
            'fields': ('name', 'code', 'description', 'is_active')
        }),
        ('Доступные переменные', {
            'fields': ('available_variables',),
            'description': 'JSON с доступными переменными для этого типа шаблона. '
                          'Формат: {"variable_name": "Описание переменной"}'
        }),
        ('Служебная информация', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )

    def templates_count(self, obj):
        """Количество шаблонов этого типа"""
        count = obj.templates.count()
        if count > 0:
            return format_html(
                '<span style="background:#2196f3;color:white;padding:2px 8px;border-radius:6px;font-weight:600;">{}</span>',
                count
            )
        return '0'

    templates_count.short_description = "Шаблонов"


@admin.register(EmailTemplate)
class EmailTemplateAdmin(admin.ModelAdmin):
    """Админка для шаблонов писем"""

    list_display = (
        'name',
        'organization_display',
        'template_type',
        'is_default_badge',
        'is_active',
        'updated_at',
        'preview_button',
    )
    list_filter = ('is_active', 'is_default', 'template_type', 'organization', 'updated_at')
    search_fields = ('name', 'subject', 'organization__short_name_ru', 'organization__full_name_ru')
    readonly_fields = ('created_at', 'updated_at', 'created_by')

    fieldsets = (
        ('Основная информация', {
            'fields': ('organization', 'template_type', 'name'),
            'description': '<strong>💡 Совет:</strong> Оставьте "Организация" пустой, '
                          'чтобы создать эталонный шаблон для всех организаций.'
        }),
        ('📧 Содержимое письма', {
            'fields': ('subject', 'body'),
            'description': '<strong>💡 Используйте переменные в фигурных скобках:</strong> '
                          '{organization_name}, {subdivision_name}, {date} и т.д.<br>'
                          'Доступные переменные зависят от типа шаблона.'
        }),
        ('⚙️ Настройки', {
            'fields': ('is_active', 'is_default')
        }),
        ('📊 Служебная информация', {
            'fields': ('created_at', 'updated_at', 'created_by'),
            'classes': ('collapse',)
        }),
    )

    def get_queryset(self, request):
        """Фильтруем по организациям пользователя"""
        qs = super().get_queryset(request)
        if not request.user.is_superuser and hasattr(request.user, 'profile'):
            allowed_orgs = request.user.profile.organizations.all()
            qs = qs.filter(organization__in=allowed_orgs)
        return qs.select_related('organization', 'template_type', 'created_by')

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        """
        Настраиваем поле organization:
        - Для обычных пользователей - только доступные организации
        - Для всех пользователей разрешаем пустое значение (эталонный шаблон)
        """
        if db_field.name == "organization":
            if not request.user.is_superuser and hasattr(request.user, 'profile'):
                kwargs["queryset"] = request.user.profile.organizations.all()
            # Для всех пользователей разрешаем пустое значение (эталонный шаблон)
            kwargs["required"] = False
        return super().formfield_for_foreignkey(db_field, request, **kwargs)

    def save_model(self, request, obj, form, change):
        """Сохраняем автора при создании"""
        if not change and not obj.created_by:
            obj.created_by = request.user
        super().save_model(request, obj, form, change)

    def is_default_badge(self, obj):
        """Бейдж для эталонного шаблона"""
        if obj.is_default:
            # Проверяем, эталонный ли это шаблон
            if obj.organization is None:
                return format_html(
                    '<span style="background:#ff9800;color:white;padding:4px 12px;border-radius:6px;font-weight:600;">⭐ Эталонный</span>'
                )
            else:
                return format_html(
                    '<span style="background:#4caf50;color:white;padding:4px 12px;border-radius:6px;font-weight:600;">✓ По умолчанию</span>'
                )
        return format_html(
            '<span style="background:#9e9e9e;color:white;padding:4px 12px;border-radius:6px;font-weight:600;">—</span>'
        )

    is_default_badge.short_description = "Статус"

    def organization_display(self, obj):
        """Отображение организации с учётом эталонных шаблонов"""
        if obj.organization is None:
            return format_html(
                '<span style="color:#ff9800;font-weight:600;">⭐ Эталон (для всех)</span>'
            )
        return obj.organization.short_name_ru

    organization_display.short_description = "Организация"
    organization_display.admin_order_field = "organization"

    def preview_button(self, obj):
        """Кнопка предпросмотра"""
        return format_html(
            '<a class="button" href="#" onclick="alert(\'Предпросмотр: {}\\n\\n{}\'); return false;" style="padding:4px 12px;">👁 Просмотр</a>',
            obj.subject[:50],
            obj.body[:100].replace('\n', ' ').replace('<', '&lt;').replace('>', '&gt;')
        )

    preview_button.short_description = "Действия"
