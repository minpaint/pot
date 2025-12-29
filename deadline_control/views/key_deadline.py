# deadline_control/views/key_deadline.py
from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import ListView, CreateView, UpdateView, DeleteView, DetailView
from django.urls import reverse_lazy
from django.contrib import messages
from collections import defaultdict

from deadline_control.models import KeyDeadlineCategory, KeyDeadlineItem
from directory.mixins import AccessControlMixin, AccessControlObjectMixin


class KeyDeadlineListView(LoginRequiredMixin, AccessControlMixin, ListView):
    """Список мероприятий ключевых сроков, сгруппированных по организациям и категориям"""
    model = KeyDeadlineItem
    template_name = 'deadline_control/key_deadline/list.html'
    context_object_name = 'items'

    def get_queryset(self):
        # AccessControlMixin автоматически фильтрует по правам доступа
        qs = super().get_queryset()
        return qs.filter(is_active=True).select_related(
            'organization', 'category'
        ).order_by('organization__short_name_ru', 'category__name', 'name')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        # Группируем мероприятия по организациям, а затем по категориям
        items_by_org = defaultdict(lambda: defaultdict(list))
        for item in context['items']:
            items_by_org[item.organization][item.category].append(item)

        # Преобразуем в отсортированный список для шаблона
        # [(организация, [(категория, [мероприятия])])]
        items_by_organization = []
        for org in sorted(items_by_org.keys(), key=lambda x: x.short_name_ru or x.full_name_ru):
            categories_list = []
            for category in sorted(items_by_org[org].keys(), key=lambda x: x.name):
                categories_list.append((category, items_by_org[org][category]))
            items_by_organization.append((org, categories_list))

        context['items_by_organization'] = items_by_organization

        return context


class KeyDeadlineCategoryCreateView(LoginRequiredMixin, CreateView):
    """Создание новой категории"""
    model = KeyDeadlineCategory
    template_name = 'deadline_control/key_deadline/category_form.html'
    fields = ['name', 'periodicity_months', 'icon']
    success_url = reverse_lazy('deadline_control:key_deadline:list')

    def form_valid(self, form):
        messages.success(self.request, f'Категория "{form.instance.name}" успешно создана')
        return super().form_valid(form)


class KeyDeadlineCategoryUpdateView(LoginRequiredMixin, UpdateView):
    """Редактирование категории"""
    model = KeyDeadlineCategory
    template_name = 'deadline_control/key_deadline/category_form.html'
    fields = ['name', 'periodicity_months', 'icon']
    success_url = reverse_lazy('deadline_control:key_deadline:list')

    def form_valid(self, form):
        messages.success(self.request, f'Категория "{form.instance.name}" успешно обновлена')
        return super().form_valid(form)


class KeyDeadlineCategoryDeleteView(LoginRequiredMixin, DeleteView):
    """Удаление категории"""
    model = KeyDeadlineCategory
    template_name = 'deadline_control/key_deadline/category_confirm_delete.html'
    success_url = reverse_lazy('deadline_control:key_deadline:list')

    def delete(self, request, *args, **kwargs):
        category = self.get_object()
        messages.success(request, f'Категория "{category.name}" успешно удалена')
        return super().delete(request, *args, **kwargs)


class KeyDeadlineItemCreateView(LoginRequiredMixin, CreateView):
    """Создание нового мероприятия"""
    model = KeyDeadlineItem
    template_name = 'deadline_control/key_deadline/item_form.html'
    fields = ['organization', 'category', 'name', 'periodicity_months', 'current_date', 'responsible_person', 'is_active', 'notes']
    success_url = reverse_lazy('deadline_control:key_deadline:list')

    def form_valid(self, form):
        messages.success(self.request, f'Мероприятие "{form.instance.name}" успешно создано')
        return super().form_valid(form)


class KeyDeadlineItemUpdateView(LoginRequiredMixin, AccessControlObjectMixin, UpdateView):
    """Редактирование мероприятия"""
    model = KeyDeadlineItem
    template_name = 'deadline_control/key_deadline/item_form.html'
    fields = ['organization', 'category', 'name', 'periodicity_months', 'current_date', 'responsible_person', 'is_active', 'notes']
    success_url = reverse_lazy('deadline_control:key_deadline:list')

    def form_valid(self, form):
        messages.success(self.request, f'Мероприятие "{form.instance.name}" успешно обновлено')
        return super().form_valid(form)


class KeyDeadlineItemDeleteView(LoginRequiredMixin, AccessControlObjectMixin, DeleteView):
    """Удаление мероприятия"""
    model = KeyDeadlineItem
    template_name = 'deadline_control/key_deadline/item_confirm_delete.html'
    success_url = reverse_lazy('deadline_control:key_deadline:list')

    def delete(self, request, *args, **kwargs):
        item = self.get_object()
        messages.success(request, f'Мероприятие "{item.name}" успешно удалено')
        return super().delete(request, *args, **kwargs)
