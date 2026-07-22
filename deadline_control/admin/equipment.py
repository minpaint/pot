# deadline_control/admin/equipment.py
from django.contrib import admin
from django.contrib import messages
from django.shortcuts import redirect, render
from django.urls import path, reverse
from django.utils.dateparse import parse_date
from django.http import HttpResponse
from tablib import Dataset

from directory.admin.mixins.tree_view import TreeViewMixin
from directory.admin.mixins.org_filter import OrgFilterAdminMixin
from deadline_control.models import Equipment
from deadline_control.forms import EquipmentForm
from deadline_control.resources import EquipmentResource


class EquipmentTreeViewMixin(TreeViewMixin):
    """Расширяет TreeViewMixin, добавляя данные о ТО."""

    change_list_template = "admin/deadline_control/equipment/change_list_tree.html"

    tree_settings = {
        'icons': {
            'organization': '🏢',
            'subdivision': '🏭',
            'department': '📂',
            'item': '⚙️',
            'no_subdivision': '🏗️',
            'no_department': '📁',
        },
        'fields': {
            'name_field': 'equipment_name',
            'organization_field': 'organization',
            'subdivision_field': 'subdivision',
            'department_field': 'department',
        },
        'display_rules': {
            'hide_empty_branches': False,
            'hide_no_subdivision_no_department': False,
        }
    }

    # ────────────────────────────────────────────────────────────
    # ДАННЫЕ ДЛЯ ДЕРЕВА
    # ────────────────────────────────────────────────────────────
    def get_tree_data(self, request):
        """Добавляем информацию о следующих ТО в каждый `item`."""
        tree = super().get_tree_data(request)
        for org_data in tree.values():
            for item in org_data['items']:
                self._add_maintenance(item)
            for sub_data in org_data['subdivisions'].values():
                for item in sub_data['items']:
                    self._add_maintenance(item)
                for dept_data in sub_data['departments'].values():
                    for item in dept_data['items']:
                        self._add_maintenance(item)
        return tree

    # ────────────────────────────────────────────────────────────
    #  МЕТОДЫ ВСПОМОГАТЕЛЬНЫЕ
    # ────────────────────────────────────────────────────────────
    def _add_maintenance(self, item):
        """Записываем дату, дни до ТО и статус (только overdue/ok)."""
        obj = item['object']
        days = obj.days_until_maintenance()
        item.update({
            'next_maintenance_date': obj.next_maintenance_date,
            'days_to_maintenance': days,
            'maintenance_state': self._get_state(days),
        })

    @staticmethod
    def _get_state(days):
        """
        Возвращает статус обслуживания:
        - "overdue" - просрочено (дни < 0)
        - "warning" - скоро (0 <= дни <= 7)
        - "ok" - норма (дни > 7)
        - "unknown" - неизвестно (дни is None)
        """
        if days is None:
            return 'unknown'
        if days < 0:
            return 'overdue'
        if days <= 7:
            return 'warning'
        return 'ok'


@admin.register(Equipment)
class EquipmentAdmin(OrgFilterAdminMixin, EquipmentTreeViewMixin, admin.ModelAdmin):
    form = EquipmentForm
    change_list_template = "admin/deadline_control/equipment/change_list_tree.html"

    list_display = [
        'equipment_name', 'inventory_number', 'equipment_type',
        'organization', 'subdivision', 'department',
        'last_maintenance_date', 'next_maintenance_date'
    ]
    list_filter = ['equipment_type', 'organization', 'subdivision', 'department']
    search_fields = ['equipment_name', 'inventory_number']

    def get_form(self, request, obj=None, **kwargs):
        Form = super().get_form(request, obj, **kwargs)

        class FormWithUser(Form):
            def __init__(self2, *args, **inner_kwargs):
                inner_kwargs['user'] = request.user
                if not obj and not inner_kwargs.get('initial_org_id'):
                    selected_org_id = request.session.get('selected_org_id')
                    if selected_org_id:
                        try:
                            inner_kwargs['initial_org_id'] = int(selected_org_id)
                        except (ValueError, TypeError):
                            pass
                super().__init__(*args, **inner_kwargs)

        return FormWithUser

    def get_urls(self):
        """🔗 Добавляем кастомные URL для импорта/экспорта"""
        urls = super().get_urls()
        custom_urls = [
            path('import/', self.admin_site.admin_view(self.import_view), name='deadline_control_equipment_import'),
            path('export/', self.admin_site.admin_view(self.export_view), name='deadline_control_equipment_export'),
        ]
        return custom_urls + urls

    # ────────────────────────────────────────────────────────────
    #  ПЕРЕПРОВЕДЕНИЕ ТО ИЗ СПИСКА
    # ────────────────────────────────────────────────────────────
    def changelist_view(self, request, extra_context=None):
        # Обработка «Провести ТО» из дерева
        if request.method == 'POST' and 'perform_maintenance' in request.POST:
            pk = request.POST.get('perform_maintenance')
            date_str = request.POST.get(f'maintenance_date_{pk}')
            new_date = parse_date(date_str) if date_str else None
            obj = self.get_queryset(request).filter(pk=pk).first()
            if obj:
                obj.update_maintenance(new_date=new_date, comment='')
                self.message_user(request, f'ТО проведено для "{obj}"')
            return redirect(request.path)
        return super().changelist_view(request, extra_context)

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if not request.user.is_superuser and hasattr(request.user, 'profile'):
            allowed_orgs = request.user.profile.organizations.all()
            qs = qs.filter(organization__in=allowed_orgs)
        return qs

    def import_view(self, request):
        """📥 Импорт оборудования"""
        context = self.admin_site.each_context(request)

        if request.method == 'POST':
            if 'confirm' in request.POST:
                # Финальное подтверждение импорта
                dataset_data = request.session.get('equipment_dataset')
                if not dataset_data:
                    messages.error(request, 'Данные для импорта не найдены. Загрузите файл заново.')
                    return redirect('admin:deadline_control_equipment_import')

                dataset = Dataset().load(dataset_data)
                resource = EquipmentResource()
                result = resource.import_data(dataset, dry_run=False)

                del request.session['equipment_dataset']

                messages.success(request, f'✅ Импорт завершен! Создано: {result.totals["new"]}, обновлено: {result.totals["update"]}')
                return redirect('admin:deadline_control_equipment_changelist')
            else:
                # Предпросмотр импорта
                import_file = request.FILES.get('import_file')
                if not import_file:
                    messages.error(request, 'Файл не выбран')
                    return redirect('admin:deadline_control_equipment_import')

                file_format = import_file.name.split('.')[-1].lower()
                if file_format not in ['xlsx', 'xls']:
                    messages.error(request, 'Поддерживаются только файлы XLSX и XLS')
                    return redirect('admin:deadline_control_equipment_import')

                try:
                    dataset = Dataset().load(import_file.read(), format=file_format)
                    resource = EquipmentResource()
                    result = resource.import_data(dataset, dry_run=True)

                    # Сохраняем данные в сессии для финального импорта
                    request.session['equipment_dataset'] = dataset.export('json')

                    context.update({
                        'title': 'Предпросмотр импорта оборудования',
                        'result': result,
                        'dataset': dataset,
                    })
                    return render(request, 'admin/deadline_control/equipment/import_preview.html', context)
                except Exception as e:
                    messages.error(request, f'Ошибка при обработке файла: {str(e)}')
                    return redirect('admin:deadline_control_equipment_import')

        context.update({
            'title': 'Импорт оборудования',
            'subtitle': None,
        })
        return render(request, 'admin/deadline_control/equipment/import.html', context)

    def export_view(self, request):
        """📤 Экспорт оборудования"""
        from deadline_control.models import Equipment

        # Фильтрация по организации (если указана)
        organization_id = request.GET.get('organization_id')

        if organization_id:
            queryset = Equipment.objects.filter(organization_id=organization_id)
        else:
            queryset = Equipment.objects.all()

        # Применяем права доступа
        if not request.user.is_superuser and hasattr(request.user, 'profile'):
            allowed_orgs = request.user.profile.organizations.all()
            queryset = queryset.filter(organization__in=allowed_orgs)

        queryset = queryset.select_related('organization', 'subdivision', 'department')

        resource = EquipmentResource()
        dataset = resource.export(queryset)

        response = HttpResponse(
            dataset.export('xlsx'),
            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
        response['Content-Disposition'] = 'attachment; filename="equipment.xlsx"'
        return response
