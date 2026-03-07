"""
Управление организационной структурой во фронтенде:
- Структурные подразделения (StructuralSubdivision) — полный CRUD
- Отделы (Department) — полный CRUD

Доступно обычным пользователям (is_staff=False) для управления структурой своей организации.
"""
from django.views.generic import ListView, CreateView, UpdateView, DeleteView
from django.contrib.auth.mixins import LoginRequiredMixin
from django.urls import reverse_lazy
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404

from directory.models import StructuralSubdivision, Department
from directory.forms.subdivision import StructuralSubdivisionForm
from directory.forms.department import DepartmentForm
from directory.utils.permissions import AccessControlHelper


class StructureListView(LoginRequiredMixin, ListView):
    """Иерархическое отображение структуры: Организации -> Подразделения -> Отделы"""
    template_name = 'directory/structure/list.html'
    context_object_name = 'subdivisions'
    model = StructuralSubdivision

    def get_queryset(self):
        accessible_orgs = AccessControlHelper.get_accessible_organizations(self.request.user, self.request)
        return StructuralSubdivision.objects.filter(
            organization__in=accessible_orgs
        ).select_related('organization').prefetch_related('departments').order_by('organization__short_name_ru', 'name')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['title'] = 'Структура организации'
        accessible_orgs = AccessControlHelper.get_accessible_organizations(self.request.user, self.request)
        # Группируем подразделения по организациям
        orgs_data = {}
        for org in accessible_orgs.order_by('short_name_ru'):
            orgs_data[org] = {
                'subdivisions': [],
                'departments_no_subdivision': list(
                    Department.objects.filter(organization=org, subdivision__isnull=True).order_by('name')
                ),
            }
        for subdivision in context['subdivisions']:
            org = subdivision.organization
            if org in orgs_data:
                orgs_data[org]['subdivisions'].append({
                    'obj': subdivision,
                    'departments': list(Department.objects.filter(subdivision=subdivision).order_by('name')),
                })
        context['orgs_data'] = orgs_data
        return context


# =====================
# Подразделения CRUD
# =====================

class SubdivisionCreateView(LoginRequiredMixin, CreateView):
    model = StructuralSubdivision
    form_class = StructuralSubdivisionForm
    template_name = 'directory/structure/subdivision_form.html'
    success_url = reverse_lazy('directory:structure:structure_list')

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['user'] = self.request.user
        return kwargs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['title'] = 'Добавить подразделение'
        return context


class SubdivisionUpdateView(LoginRequiredMixin, UpdateView):
    model = StructuralSubdivision
    form_class = StructuralSubdivisionForm
    template_name = 'directory/structure/subdivision_form.html'
    success_url = reverse_lazy('directory:structure:structure_list')

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['user'] = self.request.user
        return kwargs

    def get_object(self, queryset=None):
        obj = super().get_object(queryset)
        if not AccessControlHelper.can_access_object(self.request.user, obj):
            raise PermissionDenied
        return obj

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['title'] = f'Редактировать подразделение: {self.object.name}'
        return context


class SubdivisionDeleteView(LoginRequiredMixin, DeleteView):
    model = StructuralSubdivision
    template_name = 'directory/structure/subdivision_delete.html'
    success_url = reverse_lazy('directory:structure:structure_list')

    def get_object(self, queryset=None):
        obj = super().get_object(queryset)
        if not AccessControlHelper.can_access_object(self.request.user, obj):
            raise PermissionDenied
        return obj

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['title'] = 'Удалить подразделение'
        return context


# =====================
# Отделы CRUD
# =====================

class DepartmentCreateView(LoginRequiredMixin, CreateView):
    model = Department
    form_class = DepartmentForm
    template_name = 'directory/structure/department_form.html'
    success_url = reverse_lazy('directory:structure:structure_list')

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['user'] = self.request.user
        return kwargs

    def get_initial(self):
        initial = super().get_initial()
        # Предустанавливаем подразделение если передано в GET
        subdivision_id = self.request.GET.get('subdivision')
        if subdivision_id:
            try:
                subdivision = StructuralSubdivision.objects.get(pk=subdivision_id)
                initial['subdivision'] = subdivision
                initial['organization'] = subdivision.organization
            except StructuralSubdivision.DoesNotExist:
                pass
        return initial

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['title'] = 'Добавить отдел'
        return context


class DepartmentUpdateView(LoginRequiredMixin, UpdateView):
    model = Department
    form_class = DepartmentForm
    template_name = 'directory/structure/department_form.html'
    success_url = reverse_lazy('directory:structure:structure_list')

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['user'] = self.request.user
        return kwargs

    def get_object(self, queryset=None):
        obj = super().get_object(queryset)
        if not AccessControlHelper.can_access_object(self.request.user, obj):
            raise PermissionDenied
        return obj

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['title'] = f'Редактировать отдел: {self.object.name}'
        return context


class DepartmentDeleteView(LoginRequiredMixin, DeleteView):
    model = Department
    template_name = 'directory/structure/department_delete.html'
    success_url = reverse_lazy('directory:structure:structure_list')

    def get_object(self, queryset=None):
        obj = super().get_object(queryset)
        if not AccessControlHelper.can_access_object(self.request.user, obj):
            raise PermissionDenied
        return obj

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['title'] = 'Удалить отдел'
        return context
