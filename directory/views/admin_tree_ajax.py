"""
AJAX endpoints для подгрузки дочерних узлов древовидных представлений Employee и Position
"""
from django.contrib.admin.views.decorators import staff_member_required
from django.http import JsonResponse
from django.template.loader import render_to_string
from django.contrib import admin

from directory.models import Employee, Position
from directory.admin.employee import EmployeeAdmin
from directory.admin.position import PositionAdmin


@staff_member_required
def load_tree_children(request, model_name, parent_type, parent_id):
    """
    AJAX endpoint для подгрузки дочерних узлов дерева.

    URL: /admin/directory/ajax/tree-children/employee/org/123/

    Parameters:
        model_name: 'employee' или 'position'
        parent_type: 'org', 'sub', 'dept'
        parent_id: ID родительского узла

    Returns:
        JSON: {
            'success': True,
            'count': 10,
            'rows': ['<tr>...</tr>', '<tr>...</tr>', ...]
        }
    """
    # Определить модель и admin класс
    if model_name == 'employee':
        model = Employee
        admin_class = EmployeeAdmin(model, admin.site)
    elif model_name == 'position':
        model = Position
        admin_class = PositionAdmin(model, admin.site)
    else:
        return JsonResponse({'error': 'Invalid model name'}, status=400)

    # Получить оптимизированный queryset с правами доступа
    qs = admin_class.get_queryset(request)

    # Фильтровать по родителю
    if parent_type == 'org':
        # Дети организации: элементы без subdivision и department
        children = qs.filter(
            organization_id=parent_id,
            subdivision__isnull=True,
            department__isnull=True
        )
    elif parent_type == 'sub':
        # Дети подразделения: элементы без department
        children = qs.filter(
            subdivision_id=parent_id,
            department__isnull=True
        )
    elif parent_type == 'dept':
        # Дети отдела: все элементы отдела
        children = qs.filter(department_id=parent_id)
    else:
        return JsonResponse({'error': 'Invalid parent type'}, status=400)

    # Рендерить HTML для каждой строки
    rows_html = []
    level = {'org': 1, 'sub': 2, 'dept': 3}.get(parent_type, 1)

    for obj in children:
        # Получить дополнительные данные через admin метод
        additional_data = admin_class.get_node_additional_data(obj)

        # Подготовить контекст для шаблона
        context = {
            'item': {
                'name': str(obj),
                'object': obj,
                'pk': obj.pk,
                'additional_data': additional_data
            },
            'parent_id': f'{parent_type}-{parent_id}',
            'level': level,
            'model_name': model_name,
        }

        # Рендерить partial шаблон для одной строки
        html = render_to_string(
            f'admin/directory/{model_name}/_tree_row_ajax.html',
            context,
            request=request
        )
        rows_html.append(html)

    return JsonResponse({
        'success': True,
        'count': len(rows_html),
        'rows': rows_html
    })
