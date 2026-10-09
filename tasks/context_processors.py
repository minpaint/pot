# -*- coding: utf-8 -*-
from django.utils import timezone

from directory.models import Organization
from directory.utils.permissions import AccessControlHelper

from .models import TaskItem


def tasks_badge(request):
    """Счётчик просроченных задач для бейджа пункта «Задачи» в боковом меню."""
    user = getattr(request, 'user', None)
    if user is None or not user.is_authenticated:
        return {}
    if user.is_superuser:
        orgs = Organization.objects.all()
    else:
        orgs = AccessControlHelper.get_accessible_organizations(user, request)
    overdue = TaskItem.objects.filter(
        task_list__organization__in=orgs,
        task_list__is_archived=False,
        is_done=False,
        due_date__lt=timezone.now().date(),
    ).count()
    return {'tasks_overdue_total': overdue}
