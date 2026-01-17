from django.contrib import admin

from directory.models import Organization
from directory.forms.organization import OrganizationForm


@admin.register(Organization)
class OrganizationAdmin(admin.ModelAdmin):
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
        ('🎓 Эталонные роли для обучения', {
            'fields': (
                'default_theory_consultant',
                'default_commission_chairman',
                'default_instructor',
            ),
            'classes': ('collapse',),
            'description': 'Эти роли будут подставляться по умолчанию при создании карточки обучения. '
                          'Их можно переопределить для конкретного обучения.'
        }),
    )

    def get_form(self, request, obj=None, **kwargs):
        """
        Обычно Organization видят все админы, но если хотите, можно фильтровать.
        """
        Form = super().get_form(request, obj, **kwargs)
        return Form

    def get_queryset(self, request):
        """Фильтрация по организациям пользователя"""
        qs = super().get_queryset(request)
        if not request.user.is_superuser and hasattr(request.user, 'profile'):
            allowed_orgs = request.user.profile.organizations.all()
            qs = qs.filter(pk__in=allowed_orgs)
        return qs
