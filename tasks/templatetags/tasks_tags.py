# -*- coding: utf-8 -*-
from datetime import timedelta

from django import template
from django.utils import timezone

from directory.models import Organization
from directory.utils.permissions import AccessControlHelper

from ..models import TaskItem

register = template.Library()


@register.inclusion_tag('tasks/_home_compact.html', takes_context=True)
def tasks_home_block(context, limit=5):
    """Компактный блок задач для главной: счётчики и ближайшие открытые задачи."""
    request = context['request']
    user = request.user
    today = timezone.now().date()
    if user.is_superuser:
        orgs = Organization.objects.all()
    else:
        orgs = AccessControlHelper.get_accessible_organizations(user, request)
    selected = request.session.get('selected_org_id')
    if selected:
        orgs = orgs.filter(pk=selected)

    open_qs = TaskItem.objects.filter(
        task_list__organization__in=orgs, task_list__is_archived=False, is_done=False,
    )
    items = list(
        open_qs.select_related('task_list__organization', 'assignee')
        .order_by('due_date', 'order')[:200]
    )
    far = today + timedelta(days=36500)
    items.sort(key=lambda i: (0 if i.is_overdue else 1, i.priority_rank, i.due_date or far, i.order))
    return {
        'open_count': open_qs.count(),
        'overdue_count': open_qs.filter(due_date__lt=today).count(),
        'items': items[:limit],
        'multi_org': orgs.count() > 1,
    }
