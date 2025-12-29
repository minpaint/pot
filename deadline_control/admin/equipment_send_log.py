# deadline_control/admin/equipment_send_log.py

from django.contrib import admin
from deadline_control.models import EquipmentJournalSendLog, EquipmentJournalSendDetail


class EquipmentJournalSendDetailInline(admin.TabularInline):
    """Детали отправки по подразделениям"""
    model = EquipmentJournalSendDetail
    extra = 0
    can_delete = False

    fields = [
        'subdivision',
        'status',
        'equipment_count',
        'recipients_count',
        'error_message',
    ]
    readonly_fields = fields


@admin.register(EquipmentJournalSendLog)
class EquipmentJournalSendLogAdmin(admin.ModelAdmin):
    """Админка логов рассылки журналов осмотра оборудования"""

    list_display = [
        'id',
        'organization',
        'equipment_type',
        'inspection_date',
        'initiated_by',
        'status',
        'get_stats',
        'created_at',
    ]

    list_filter = [
        'status',
        'created_at',
        'equipment_type',
    ]

    search_fields = [
        'organization__short_name_ru',
        'organization__full_name_ru',
        'initiated_by__username',
    ]

    readonly_fields = [
        'organization',
        'initiated_by',
        'equipment_type',
        'inspection_date',
        'total_subdivisions',
        'successful_count',
        'failed_count',
        'skipped_count',
        'status',
        'created_at',
        'updated_at',
    ]

    inlines = [EquipmentJournalSendDetailInline]

    def has_add_permission(self, request):
        return False

    def get_stats(self, obj):
        return f"? {obj.successful_count} / ? {obj.failed_count} / ?? {obj.skipped_count}"

    get_stats.short_description = "Статистика"

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if not request.user.is_superuser and hasattr(request.user, 'profile'):
            allowed_orgs = request.user.profile.organizations.all()
            qs = qs.filter(organization__in=allowed_orgs)
        return qs.select_related('organization', 'initiated_by', 'equipment_type')
