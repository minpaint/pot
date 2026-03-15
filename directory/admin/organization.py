from django.contrib import admin

from directory.models import Organization
from directory.forms.organization import OrganizationForm
from directory.admin.mixins.org_filter import OrgFilterAdminMixin


@admin.register(Organization)
class OrganizationAdmin(OrgFilterAdminMixin, admin.ModelAdmin):
    org_filter_lookup = 'pk'
    org_profile_lookup = 'pk__in'
    org_filter_get_params = ('id__exact', 'pk')
    """
    🏢 Админ-класс для модели Organization

    Примечание: Ключевые сроки управляются через раздел
    "Контроль сроков" -> "📅 Ключевые сроки"
    """
    form = OrganizationForm
    list_display = ['full_name_ru', 'short_name_ru', 'full_name_by', 'short_name_by', 'location']
    search_fields = ['full_name_ru', 'short_name_ru', 'full_name_by', 'short_name_by', 'location']

    fieldsets = (
        ('Основная информация', {
            'fields': (
                'full_name_ru',
                'short_name_ru',
                'full_name_by',
                'short_name_by',
                'location',
            )
        }),
        ('Реквизиты', {
            'fields': ('requisites_ru', 'requisites_by')
        }),
    )

