# deadline_control/admin/organization_key_deadlines.py
from django.contrib import admin
from django.utils.html import format_html

from directory.models import Organization
from deadline_control.models import KeyDeadlineItem
from directory.admin.mixins.org_filter import OrgFilterAdminMixin


class KeyDeadlineItemInline(admin.TabularInline):
    """Inline для управления ключевыми сроками организации"""
    model = KeyDeadlineItem
    extra = 3
    fields = ['category', 'name', 'current_date', 'next_date', 'periodicity_months', 'responsible_person', 'is_active']
    readonly_fields = ['next_date']

    verbose_name = "Ключевой срок"
    verbose_name_plural = "Ключевые сроки"


@admin.register(Organization)
class OrganizationKeyDeadlinesAdmin(OrgFilterAdminMixin, admin.ModelAdmin):
    org_filter_lookup = 'pk'
    org_profile_lookup = 'pk__in'
    org_filter_get_params = ('id__exact', 'pk')
    """
    📅 Ключевые сроки организаций
    Управление всеми мероприятиями через организацию
    """
    list_display = ['short_name_ru', 'active_items_count', 'overdue_items_count']
    search_fields = ['short_name_ru', 'full_name_ru']
    inlines = [KeyDeadlineItemInline]

    def get_model_perms(self, request):
        """
        Возвращаем пермишены чтобы модель отображалась в админке
        """
        return {
            'add': False,  # Не даем создавать организации через этот админ
            'change': True,
            'delete': False,
            'view': True,
        }

    def active_items_count(self, obj):
        """Количество активных мероприятий"""
        count = obj.key_deadline_items.filter(is_active=True).count()
        return format_html('<span>{}</span>', count)
    active_items_count.short_description = "Активных мероприятий"

    def overdue_items_count(self, obj):
        """Количество просроченных мероприятий"""
        items = obj.key_deadline_items.filter(is_active=True)
        count = sum(1 for item in items if item.is_overdue())
        if count > 0:
            return format_html('<span style="color:red; font-weight:bold;">🚨 {}</span>', count)
        return format_html('<span style="color:green;">✅ 0</span>')
    overdue_items_count.short_description = "Просроченных"

    class Media:
        css = {
            'all': ('admin/css/changelists.css',)
        }
