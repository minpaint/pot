# directory/admin/document_admin.py
"""
📝 Административный интерфейс для моделей документов

Этот модуль содержит классы для регистрации моделей документов
в административном интерфейсе Django.
"""
from django.contrib import admin
from django.utils.translation import gettext_lazy as _
from django.contrib import messages

from directory.models.document_template import (
    DocumentTemplateType,
    DocumentTemplate,
    GeneratedDocument,
    DocumentGenerationLog,
    DocumentEmailSendLog,
)


@admin.register(DocumentTemplateType)
class DocumentTemplateTypeAdmin(admin.ModelAdmin):
    """
    Административный интерфейс для видов шаблонов документов
    """
    list_display = ('name', 'code', 'is_active', 'show_in_hiring', 'updated_at')
    list_filter = ('is_active', 'show_in_hiring')
    search_fields = ('name', 'code', 'description')
    readonly_fields = ('created_at', 'updated_at')
    ordering = ('name',)


@admin.register(DocumentTemplate)
class DocumentTemplateAdmin(admin.ModelAdmin):
    """
    Административный интерфейс для шаблонов документов
    """
    list_display = ('name', 'document_type', 'organization', 'is_default', 'is_active', 'created_at', 'updated_at')
    list_filter = ('document_type', 'is_default', 'is_active', 'organization')
    search_fields = ('name', 'description')
    readonly_fields = ('created_at', 'updated_at')

    fieldsets = (
        (None, {
            'fields': ('name', 'description', 'document_type', 'is_active')
        }),
        (_('Привязка шаблона'), {
            'fields': ('organization', 'is_default')
        }),
        (_('Шаблон'), {
            'fields': ('template_file',)
        }),
        (_('Информация'), {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )

    def save_model(self, request, obj, form, change):
        """Дополнительная валидация перед сохранением"""
        # Если шаблон эталонный, убеждаемся, что организация не указана
        if obj.is_default and obj.organization:
            obj.organization = None
            messages.warning(request, _("Для эталонного шаблона организация не может быть указана. Организация сброшена."))

        super().save_model(request, obj, form, change)


@admin.register(GeneratedDocument)
class GeneratedDocumentAdmin(admin.ModelAdmin):
    """
    Административный интерфейс для сгенерированных документов
    """
    list_display = ('employee', 'get_document_type', 'created_at', 'created_by')
    list_filter = ('template__document_type', 'created_at')
    search_fields = ('employee__full_name_nominative', 'template__name')
    readonly_fields = ('employee', 'template', 'document_file', 'created_at', 'created_by', 'document_data')

    def get_document_type(self, obj):
        """
        Возвращает тип документа для отображения в списке
        """
        if obj.template and obj.template.document_type:
            return obj.template.document_type.name
        return _('Неизвестный тип')

    get_document_type.short_description = _('Тип документа')

    def has_add_permission(self, request):
        """
        Запрещает добавление документов через админку
        """
        return False


@admin.register(DocumentGenerationLog)
class DocumentGenerationLogAdmin(admin.ModelAdmin):
    """
    Административный интерфейс для логов генерации документов
    """
    list_display = ('employee', 'get_document_types', 'created_at', 'created_by')
    list_filter = ('created_at', 'created_by')
    search_fields = ('employee__full_name_nominative',)
    readonly_fields = ('employee', 'document_types', 'created_at', 'created_by')
    date_hierarchy = 'created_at'

    def get_document_types(self, obj):
        """Возвращает читаемые названия типов документов"""
        return obj.get_document_types_display()

    get_document_types.short_description = _('Типы документов')

    def has_add_permission(self, request):
        """Запрещает добавление логов через админку"""
        return False

    def has_change_permission(self, request, obj=None):
        """Запрещает редактирование логов"""
        return False


@admin.register(DocumentEmailSendLog)
class DocumentEmailSendLogAdmin(admin.ModelAdmin):
    """
    Административный интерфейс для логов отправки документов по email
    """
    list_display = (
        'get_status_icon',
        'employee',
        'get_document_types',
        'get_recipients_list',
        'sent_at',
        'sent_by'
    )
    list_filter = ('status', 'sent_at', 'sent_by')
    search_fields = (
        'employee__full_name_nominative',
        'email_subject',
        'recipients',
        'error_message'
    )
    readonly_fields = (
        'employee',
        'hiring',
        'document_types',
        'recipients',
        'recipients_count',
        'documents_count',
        'status',
        'error_message',
        'email_subject',
        'sent_by',
        'sent_at',
        'get_recipients_list'
    )
    date_hierarchy = 'sent_at'

    fieldsets = (
        (_('Основная информация'), {
            'fields': ('employee', 'hiring', 'status', 'sent_at', 'sent_by')
        }),
        (_('Отправленные документы'), {
            'fields': ('document_types', 'documents_count')
        }),
        (_('Получатели'), {
            'fields': ('recipients_count', 'get_recipients_list', 'email_subject')
        }),
        (_('Ошибка (если есть)'), {
            'fields': ('error_message',),
            'classes': ('collapse',)
        }),
    )

    def get_status_icon(self, obj):
        """Возвращает иконку статуса"""
        if obj.status == 'success':
            return '✅'
        return '❌'

    get_status_icon.short_description = ''

    def get_document_types(self, obj):
        """Возвращает читаемые названия типов документов"""
        return obj.get_document_types_display()

    get_document_types.short_description = _('Типы документов')

    def get_recipients_list(self, obj):
        """Возвращает список получателей"""
        return obj.get_recipients_display()

    get_recipients_list.short_description = _('Email получателей')

    def has_add_permission(self, request):
        """Запрещает добавление логов через админку"""
        return False

    def has_change_permission(self, request, obj=None):
        """Запрещает редактирование логов"""
        return False
