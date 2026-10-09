# -*- coding: utf-8 -*-
import json
from datetime import date

from datetime import timedelta

from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Q
from django.views.decorators.http import require_POST
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.views.generic import TemplateView

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


# ─── Сериализация и вспомогательные функции ──────────────────────────────────

def _user_name(user):
    if not user:
        return ''
    return user.get_full_name().strip() or user.username


def _resolve_assignee(raw, org):
    """Исполнитель — только пользователь с доступом к организации (или суперпользователь)."""
    if not raw:
        return None
    try:
        uid = int(raw)
    except (TypeError, ValueError):
        return None
    return _org_users(org).filter(pk=uid).first()


def _org_users(org):
    User = get_user_model()
    return User.objects.filter(is_active=True).filter(
        Q(is_superuser=True) | Q(profile__organizations=org)
    ).distinct().order_by('last_name', 'first_name', 'username')


def _item_json(item):
    today = timezone.now().date()
    return {
        'id': item.pk,
        'list_id': item.task_list_id,
        'text': item.text,
        'priority': item.priority,
        'priority_label': item.get_priority_display(),
        'due_date': item.due_date.strftime('%d.%m.%Y') if item.due_date else None,
        'due_date_iso': item.due_date.isoformat() if item.due_date else None,
        'is_done': item.is_done,
        'is_overdue': bool(item.due_date and not item.is_done and item.due_date < today),
        'assignee_id': item.assignee_id,
        'assignee_name': _user_name(item.assignee),
        'note': item.note,
    }


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
        assignee=_resolve_assignee(request.POST.get('assignee'), task_list.organization),
        note=request.POST.get('note', '').strip(),
        created_by=request.user,
    )
    return JsonResponse(_item_json(item))


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


# ─── Изменить задачу ──────────────────────────────────────────────────────────

@login_required
@require_POST
def update_item(request, pk):
    item = get_object_or_404(TaskItem.objects.select_related('task_list__organization'), pk=pk)
    org = item.task_list.organization
    if not _check_org_access(request.user, request, org):
        return JsonResponse({'error': 'forbidden'}, status=403)

    text = request.POST.get('text', '').strip()
    if not text:
        return JsonResponse({'error': 'empty'}, status=400)
    item.text = text[:500]

    priority = request.POST.get('priority', item.priority)
    if priority in ('high', 'normal', 'low'):
        item.priority = priority

    due_raw = request.POST.get('due_date', '').strip()
    if due_raw:
        try:
            item.due_date = date.fromisoformat(due_raw)
        except ValueError:
            pass
    else:
        item.due_date = None

    item.assignee = _resolve_assignee(request.POST.get('assignee'), org)
    item.note = request.POST.get('note', '').strip()

    # перенос в другой список той же организации
    new_list = request.POST.get('list_id')
    if new_list and str(item.task_list_id) != str(new_list):
        target = TaskList.objects.filter(pk=new_list, organization=org).first()
        if target:
            item.task_list = target

    item.save()
    return JsonResponse(_item_json(item))


# ─── Страница «Задачи» ──────────────────────────────────────────────────

class PlanningView(LoginRequiredMixin, TemplateView):
    """Сводка задач по организациям (обзор) и списки задач."""
    template_name = 'tasks/planning.html'

    STATUSES = [
        ('open', 'Открытые'),
        ('overdue', 'Просроченные'),
        ('week', 'Срок ≤ 7 дней'),
        ('nodue', 'Без срока'),
        ('done', 'Выполненные'),
        ('all', 'Все'),
    ]

    def _selected_org(self, accessible):
        """GET ?org= (all — все организации) → сессия selected_org_id → все."""
        raw = self.request.GET.get('org')
        if raw == 'all':
            return None
        if raw:
            try:
                org_id = int(raw)
            except ValueError:
                return None
            if accessible.filter(pk=org_id).exists():
                self.request.session['selected_org_id'] = org_id
                return org_id
            return None
        org_id = self.request.session.get('selected_org_id')
        if org_id and accessible.filter(pk=org_id).exists():
            return org_id
        return None

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        request = self.request
        user = request.user
        today = timezone.now().date()
        week = today + timedelta(days=7)

        accessible = _accessible_orgs(user, request)
        selected_org_id = self._selected_org(accessible)
        orgs = accessible.filter(pk=selected_org_id) if selected_org_id else accessible
        orgs = orgs.order_by('short_name_ru')

        tab = request.GET.get('tab', 'overview')
        if tab not in ('overview', 'lists'):
            tab = 'overview'
        status = request.GET.get('status', 'open')
        if status not in dict(self.STATUSES):
            status = 'open'
        priority = request.GET.get('priority', '')
        mine = request.GET.get('mine') == '1'
        q = request.GET.get('q', '').strip()
        show_archived = request.GET.get('archived') == '1'

        base = TaskItem.objects.filter(
            task_list__organization__in=orgs,
            task_list__is_archived=False,
        )

        # KPI считаются по организациям в области видимости, без учёта фильтров статуса
        open_qs = base.filter(is_done=False)
        kpi = {
            'open': open_qs.count(),
            'overdue': open_qs.filter(due_date__lt=today).count(),
            'week': open_qs.filter(due_date__gte=today, due_date__lte=week).count(),
            'nodue': open_qs.filter(due_date__isnull=True).count(),
            'done': base.filter(is_done=True).count(),
        }

        qs = base.select_related('task_list', 'task_list__organization', 'assignee')
        if status == 'open':
            qs = qs.filter(is_done=False)
        elif status == 'overdue':
            qs = qs.filter(is_done=False, due_date__lt=today)
        elif status == 'week':
            qs = qs.filter(is_done=False, due_date__gte=today, due_date__lte=week)
        elif status == 'nodue':
            qs = qs.filter(is_done=False, due_date__isnull=True)
        elif status == 'done':
            qs = qs.filter(is_done=True)
        if priority in ('high', 'normal', 'low'):
            qs = qs.filter(priority=priority)
        if mine:
            qs = qs.filter(assignee=user)
        if q:
            qs = qs.filter(Q(text__icontains=q) | Q(note__icontains=q))

        far = date.max

        def sort_key(it):
            return (
                it.is_done,
                0 if it.is_overdue else 1,
                it.priority_rank,
                it.due_date or far,
                it.order,
            )

        by_org = {}
        for it in qs:
            by_org.setdefault(it.task_list.organization_id, []).append(it)

        # агрегаты по организации (без фильтров статуса — чтобы шапка не «прыгала»)
        stats = {}
        for it in base.values('task_list__organization_id', 'is_done', 'due_date'):
            st = stats.setdefault(it['task_list__organization_id'], {'open': 0, 'overdue': 0, 'done': 0})
            if it['is_done']:
                st['done'] += 1
            else:
                st['open'] += 1
                if it['due_date'] and it['due_date'] < today:
                    st['overdue'] += 1

        list_counts = {}
        for tl in TaskList.objects.filter(organization__in=orgs, is_archived=False).values('organization_id', 'id', 'title'):
            list_counts.setdefault(tl['organization_id'], []).append({'id': tl['id'], 'title': tl['title']})

        org_blocks, orgs_without_lists = [], []
        for org in orgs:
            lists = list_counts.get(org.id, [])
            if not lists:
                orgs_without_lists.append(org)
                continue
            st = stats.get(org.id, {'open': 0, 'overdue': 0, 'done': 0})
            total = st['open'] + st['done']
            org_blocks.append({
                'org': org,
                'items': sorted(by_org.get(org.id, []), key=sort_key),
                'open': st['open'], 'overdue': st['overdue'], 'done': st['done'],
                'percent': int(st['done'] * 100 / total) if total else 0,
                'lists_count': len(lists),
            })
        # организации с просрочкой — выше
        org_blocks.sort(key=lambda b: (-b['overdue'], -b['open'], b['org'].short_name_ru))

        # данные для модального окна (списки и исполнители по организациям)
        org_lists = {}
        org_users = {}
        for org in orgs:
            org_lists[org.id] = list_counts.get(org.id, [])
            org_users[org.id] = [{'id': u.id, 'name': _user_name(u)} for u in _org_users(org)]

        ctx.update({
            'tab': tab,
            'orgs_all': accessible.order_by('short_name_ru'),
            'selected_org_id': selected_org_id,
            'statuses': self.STATUSES,
            'f_status': status, 'f_priority': priority, 'f_mine': mine, 'f_q': q,
            'show_archived': show_archived,
            'kpi': kpi,
            'org_blocks': org_blocks,
            'orgs_without_lists': orgs_without_lists,
            'org_lists_json': org_lists,
            'org_users_json': org_users,
            'today': today,
        })

        if tab == 'lists':
            blocks = []
            for org in orgs:
                lq = TaskList.objects.filter(organization=org)
                if not show_archived:
                    lq = lq.filter(is_archived=False)
                lq = lq.prefetch_related('items__assignee').order_by('-created_at')
                blocks.append({'org': org, 'lists': list(lq)})
            ctx['task_orgs'] = blocks
        return ctx
