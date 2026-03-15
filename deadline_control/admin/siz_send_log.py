from django.contrib import admin

from deadline_control.models import SIZCardSendLog


@admin.register(SIZCardSendLog)
class SIZCardSendLogAdmin(admin.ModelAdmin):
    list_display = [
        'id',
        'organization',
        'initiated_by',
        'issue_date',
        'successful_count',
        'failed_count',
        'skipped_count',
        'total_cards',
        'test_mode',
        'status',
        'created_at',
    ]
    list_filter = ['status', 'test_mode', 'organization', 'created_at']
    search_fields = ['organization__short_name_ru', 'organization__full_name_ru', 'initiated_by__username']
    readonly_fields = [
        'organization',
        'initiated_by',
        'issue_date',
        'total_subdivisions',
        'successful_count',
        'failed_count',
        'skipped_count',
        'total_cards',
        'test_mode',
        'status',
        'created_at',
        'updated_at',
    ]

    def has_add_permission(self, request):
        return False
