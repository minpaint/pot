# deadline_control/admin/organization_key_deadlines.py
from django.contrib import admin
from django.utils.html import format_html

from directory.models import Organization
from deadline_control.models import KeyDeadlineItem


class KeyDeadlineItemInline(admin.TabularInline):
    """Inline для управления ключевыми сроками организации"""
    model = KeyDeadlineItem
    extra = 3
    fields = ['category', 'name', 'current_date', 'next_date', 'periodicity_months', 'responsible_person', 'is_active']
    readonly_fields = ['next_date']

    verbose_name = "Ключевой срок"
    verbose_name_plural = "Ключевые сроки"


@admin.register(Organization)
class OrganizationKeyDeadlinesAdmin(admin.ModelAdmin):
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

    def get_queryset(self, request):
        """Фильтрация по организациям пользователя"""
        qs = super().get_queryset(request)
        if not request.user.is_superuser and hasattr(request.user, 'profile'):
            allowed_orgs = request.user.profile.organizations.all()
            qs = qs.filter(pk__in=allowed_orgs)
        return qs

    class Media:
        css = {
            'all': ('admin/css/changelists.css',)
        }
