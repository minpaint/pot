# -*- coding: utf-8 -*-
import json
from datetime import date

from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone

from .models import TaskList, TaskItem
from directory.models import Organization
from directory.utils.permissions import AccessControlHelper


# ─── Хелпер проверки доступа ─────────────────────────────────────────────────

def _accessible_orgs(user, request):
    if user.is_superuser:
        return Organization.objects.all()
    return AccessControlHelper.get_accessible_organizations(user, request)


def _check_org_access(user, request, org):
    return _accessible_orgs(user, request).filter(pk=org.pk).exists()


# ─── Toggle задачи ────────────────────────────────────────────────────────────

@login_required
@require_POST
def toggle_item(request, pk):
    item = get_object_or_404(TaskItem, pk=pk)
    if not _check_org_access(request.user, request, item.task_list.organization):
        return JsonResponse({'error': 'forbidden'}, status=403)
    item.is_done = not item.is_done
    item.done_at = timezone.now() if item.is_done else None
    item.save(update_fields=['is_done', 'done_at'])
    return JsonResponse({
        'is_done': item.is_done,
        'done_at': item.done_at.strftime('%d.%m.%Y %H:%M') if item.done_at else None,
    })


# ─── Добавить задачу ──────────────────────────────────────────────────────────

@login_required
@require_POST
def add_item(request, list_pk):
    task_list = get_object_or_404(TaskList, pk=list_pk)
    if not _check_org_access(request.user, request, task_list.organization):
        return JsonResponse({'error': 'forbidden'}, status=403)

    text = request.POST.get('text', '').strip()
    if not text:
        return JsonResponse({'error': 'empty'}, status=400)

    priority = request.POST.get('priority', 'normal')
    if priority not in ('high', 'normal', 'low'):
        priority = 'normal'

    due_date = None
    due_date_raw = request.POST.get('due_date', '').strip()
    if due_date_raw:
        try:
            due_date = date.fromisoformat(due_date_raw)
        except ValueError:
            pass

    order = TaskItem.objects.filter(task_list=task_list).count()
    item = TaskItem.objects.create(
        task_list=task_list,
        text=text,
        priority=priority,
        due_date=due_date,
        order=order,
    )

    today = timezone.now().date()
    return JsonResponse({
        'id': item.pk,
        'text': item.text,
        'priority': item.priority,
        'priority_label': item.get_priority_display(),
        'due_date': item.due_date.strftime('%d.%m.%Y') if item.due_date else None,
        'due_date_iso': item.due_date.isoformat() if item.due_date else None,
        'is_done': item.is_done,
        'is_overdue': bool(item.due_date and item.due_date < today),
    })


# ─── Удалить задачу ───────────────────────────────────────────────────────────

@login_required
@require_POST
def delete_item(request, pk):
    item = get_object_or_404(TaskItem, pk=pk)
    if not _check_org_access(request.user, request, item.task_list.organization):
        return JsonResponse({'error': 'forbidden'}, status=403)
    item.delete()
    return JsonResponse({'success': True})


# ─── Добавить список ──────────────────────────────────────────────────────────

@login_required
@require_POST
def add_list(request):
    org_id = request.POST.get('org_id', '').strip()
    title = request.POST.get('title', '').strip()
    color = request.POST.get('color', '#3498db').strip()

    if not org_id or not title:
        return JsonResponse({'error': 'invalid'}, status=400)

    org = get_object_or_404(Organization, pk=org_id)
    if not _check_org_access(request.user, request, org):
        return JsonResponse({'error': 'forbidden'}, status=403)

    if not color.startswith('#') or len(color) != 7:
        color = '#3498db'

    task_list = TaskList.objects.create(
        organization=org,
        title=title,
        color=color,
        created_by=request.user,
    )
    return JsonResponse({
        'id': task_list.pk,
        'title': task_list.title,
        'color': task_list.color,
        'org_id': org.pk,
    })


# ─── Удалить список ───────────────────────────────────────────────────────────

@login_required
@require_POST
def delete_list(request, pk):
    task_list = get_object_or_404(TaskList, pk=pk)
    if not _check_org_access(request.user, request, task_list.organization):
        return JsonResponse({'error': 'forbidden'}, status=403)
    task_list.delete()
    return JsonResponse({'success': True})


# ─── Архивировать/разархивировать список ─────────────────────────────────────

@login_required
@require_POST
def archive_list(request, pk):
    task_list = get_object_or_404(TaskList, pk=pk)
    if not _check_org_access(request.user, request, task_list.organization):
        return JsonResponse({'error': 'forbidden'}, status=403)
    task_list.is_archived = not task_list.is_archived
    task_list.save(update_fields=['is_archived'])
    return JsonResponse({'is_archived': task_list.is_archived})
