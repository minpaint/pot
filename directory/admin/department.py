"""
📂 Admin для отделов.
"""
from django.contrib import admin
from directory.admin.mixins.tree_view import TreeViewMixin
from directory.models import Department, DepartmentEmail
from directory.forms.department import DepartmentForm


class DepartmentEmailInline(admin.TabularInline):
    """
    📧 Inline для email-адресов отдела.
    """
    model = DepartmentEmail
    extra = 1
    fields = ['email', 'description', 'is_active', 'created_at']
    readonly_fields = ['created_at']
    verbose_name = "Email отдела"
    verbose_name_plural = "Email отдела"

@admin.register(Department)
class DepartmentAdmin(TreeViewMixin, admin.ModelAdmin):
    """
    📂 Организация -> Подразделение -> Отдел
    """
    form = DepartmentForm
    inlines = [DepartmentEmailInline]

    change_list_template = "admin/directory/department/change_list_tree.html"

    tree_settings = {
        'icons': {
            'organization': '🏢',
            'subdivision': '🏭',
            'department': '📂',
            'item': '📂',  # Можно поставить любую иконку
            'no_subdivision': '🏗️',
            'no_department': '📁'
        },
        'fields': {
            'name_field': 'name',        # как у модели Department
            'organization_field': 'organization',
            'subdivision_field': 'subdivision',
            'department_field': None,    # т.к. сам Department не имеет department
        },
        'display_rules': {
            'hide_empty_branches': False,
            'hide_no_subdivision_no_department': False
        }
    }

    list_display = ['name', 'short_name', 'organization', 'subdivision']
    list_filter = ['organization', 'subdivision']
    search_fields = ['name', 'short_name']

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if not request.user.is_superuser and hasattr(request.user, 'profile'):
            allowed_orgs = request.user.profile.organizations.all()
            qs = qs.filter(organization__in=allowed_orgs)
        return qs
