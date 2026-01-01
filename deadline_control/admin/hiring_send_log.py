# deadline_control/admin/hiring_send_log.py

from django.contrib import admin
from django.utils.translation import gettext_lazy as _

from directory.models import DocumentEmailSendLog


@admin.register(DocumentEmailSendLog)
class DocumentEmailSendLogAdmin(admin.ModelAdmin):
    """
    Административный интерфейс для логов отправки документов приема по email
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
