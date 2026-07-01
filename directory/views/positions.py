from collections import OrderedDict

from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.core.exceptions import ValidationError
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.urls import reverse_lazy
from django.views.decorators.http import require_POST
from django.views.generic import ListView, CreateView, UpdateView, DeleteView, TemplateView

from directory.models import Position, Organization, StructuralSubdivision, Department  # добавляем Department
from directory.forms import PositionForm
from directory.mixins import AccessControlMixin, AccessControlObjectMixin
from directory.utils.profession_icons import get_profession_icon
from directory.utils.permissions import AccessControlHelper


def _user_can_delete_position(user):
    return bool(
        user and user.is_authenticated and (
            user.is_superuser or
            (user.is_staff and user.has_perm('directory.delete_position'))
        )
    )


def _position_has_instructions(position):
    return any(
        (value or '').strip()
        for value in (
            position.safety_instructions_numbers,
            position.contract_safety_instructions,
            position.company_vehicle_instructions,
        )
    )


def _get_selected_position_org(request, accessible_orgs):
    selected_org_id = request.session.get('selected_org_id')
    if selected_org_id:
        try:
            selected_org_id = int(selected_org_id)
        except (TypeError, ValueError):
            selected_org_id = None

    if selected_org_id and accessible_orgs.filter(id=selected_org_id).exists():
        return selected_org_id

    # Автовыбор только если у пользователя ровно одна организация —
    # при нескольких не перезаписываем сессию (не ломаем «Все организации»)
    if accessible_orgs.count() == 1:
        only_org_id = accessible_orgs.first().id
        request.session['selected_org_id'] = only_org_id
        return only_org_id

    return None


def _build_position_tree(positions):
    tree = OrderedDict()

    for position in positions:
        org = position.organization
        sub = position.subdivision
        dept = position.department

        org_entry = tree.setdefault(
            org.id,
            {
                'org': org,
                'direct_positions': [],
                'subdivisions': OrderedDict(),
                'positions_count': 0,
            }
        )
        org_entry['positions_count'] += 1

        if not sub:
            org_entry['direct_positions'].append(position)
            continue

        sub_entry = org_entry['subdivisions'].setdefault(
            sub.id,
            {
                'subdivision': sub,
                'direct_positions': [],
                'departments': OrderedDict(),
                'positions_count': 0,
            }
        )
        sub_entry['positions_count'] += 1

        if not dept:
            sub_entry['direct_positions'].append(position)
            continue

        dept_entry = sub_entry['departments'].setdefault(
            dept.id,
            {
                'department': dept,
                'positions': [],
                'positions_count': 0,
            }
        )
        dept_entry['positions_count'] += 1
        dept_entry['positions'].append(position)

    return tree.values()


class PositionInstructionListView(LoginRequiredMixin, TemplateView):
    template_name = 'directory/positions/instruction_list.html'

    def get_queryset(self):
        queryset = Position.objects.select_related(
            'organization',
            'subdivision',
            'department',
        )
        queryset = AccessControlHelper.filter_queryset(queryset, self.request.user, self.request)

        accessible_orgs = AccessControlHelper.get_accessible_organizations(self.request.user, self.request)
        session_org_id = _get_selected_position_org(self.request, accessible_orgs)
        if session_org_id:
            queryset = queryset.filter(organization_id=session_org_id)

        query = (self.request.GET.get('q') or '').strip()
        if query:
            queryset = queryset.filter(position_name__icontains=query)

        return queryset.order_by(
            'organization__short_name_ru',
            'organization__full_name_ru',
            'subdivision__name',
            'department__name',
            'position_name',
        )

    def get_filtered_positions(self):
        positions = list(self.get_queryset())

        for position in positions:
            position.has_any_instructions = _position_has_instructions(position)
            position.profession_icon = get_profession_icon(position.position_name)

        if self.request.GET.get('no_instructions') == '1':
            positions = [position for position in positions if not position.has_any_instructions]

        if self.request.GET.get('responsible') == '1':
            positions = [position for position in positions if position.is_responsible_for_safety]

        if self.request.GET.get('vehicle') == '1':
            positions = [position for position in positions if position.drives_company_vehicle]

        return positions

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        positions = self.get_filtered_positions()
        accessible_orgs = AccessControlHelper.get_accessible_organizations(self.request.user, self.request)

        context.update({
            'title': 'Должности',
            'tree': _build_position_tree(positions),
            'positions_count': len(positions),
            'organizations_count': accessible_orgs.count(),
            'can_delete_position': _user_can_delete_position(self.request.user),
            'query': (self.request.GET.get('q') or '').strip(),
            'no_instructions': self.request.GET.get('no_instructions') == '1',
            'responsible_only': self.request.GET.get('responsible') == '1',
            'vehicle_only': self.request.GET.get('vehicle') == '1',
        })
        return context


class PositionListView(LoginRequiredMixin, AccessControlMixin, ListView):
    model = Position
    template_name = 'directory/positions/list.html'
    context_object_name = 'positions'
    paginate_by = 20

    def get_queryset(self):
        # AccessControlMixin автоматически фильтрует по правам доступа
        queryset = super().get_queryset()
        accessible_orgs = AccessControlHelper.get_accessible_organizations(self.request.user, self.request)
        session_org_id = _get_selected_position_org(self.request, accessible_orgs)

        if session_org_id:
            queryset = queryset.filter(organization_id=session_org_id)

        # Фильтрация по подразделению
        subdivision = self.request.GET.get('subdivision')
        if subdivision:
            queryset = queryset.filter(subdivision_id=subdivision)

        # Поиск по названию должности
        search = self.request.GET.get('search')
        if search:
            queryset = queryset.filter(position_name__icontains=search)

        return queryset.select_related('organization', 'subdivision', 'department').order_by(
            'position_name', 'subdivision__name', 'department__name'
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['title'] = 'Должности'

        # Используем AccessControlHelper для получения доступных организаций и подразделений
        accessible_orgs = AccessControlHelper.get_accessible_organizations(
            self.request.user, self.request
        )
        selected_org_id = _get_selected_position_org(self.request, accessible_orgs)

        subdivisions = AccessControlHelper.get_accessible_subdivisions(
            self.request.user, self.request
        )
        if selected_org_id:
            subdivisions = subdivisions.filter(organization_id=selected_org_id)

        context['subdivisions'] = subdivisions
        context['selected_subdivision'] = int(self.request.GET.get('subdivision') or 0) or ''
        context['search_query'] = (self.request.GET.get('search') or '').strip()
        context['can_delete_position'] = _user_can_delete_position(self.request.user)

        return context

class PositionCreateView(LoginRequiredMixin, CreateView):
    model = Position
    form_class = PositionForm
    template_name = 'directory/positions/form.html'
    success_url = reverse_lazy('directory:positions:position_list')

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['user'] = self.request.user
        org_id = self.request.session.get('selected_org_id')
        if org_id:
            try:
                kwargs['initial_org_id'] = int(org_id)
            except (ValueError, TypeError):
                pass
        return kwargs

    def get_initial(self):
        initial = super().get_initial()
        org_id = self.request.session.get('selected_org_id')
        if org_id:
            try:
                initial['organization'] = int(org_id)
            except (ValueError, TypeError):
                pass
        return initial

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['title'] = 'Добавление должности'
        context['can_delete_position'] = _user_can_delete_position(self.request.user)
        return context

class PositionUpdateView(LoginRequiredMixin, AccessControlObjectMixin, UpdateView):
    model = Position
    form_class = PositionForm
    template_name = 'directory/positions/form.html'
    success_url = reverse_lazy('directory:positions:position_list')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['title'] = 'Редактирование должности'
        context['can_delete_position'] = _user_can_delete_position(self.request.user)
        return context

class PositionDeleteView(LoginRequiredMixin, UserPassesTestMixin, AccessControlObjectMixin, DeleteView):
    model = Position
    template_name = 'directory/positions/confirm_delete.html'
    success_url = reverse_lazy('directory:positions:position_list')
    raise_exception = True

    def test_func(self):
        return _user_can_delete_position(self.request.user)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['title'] = 'Удаление должности'
        return context

def get_positions(request):
    """AJAX представление для получения должностей по подразделению"""
    subdivision_id = request.GET.get('subdivision')
    positions = Position.objects.filter(
        subdivision_id=subdivision_id
    ).values('id', 'position_name')  # Используем position_name вместо name
    return JsonResponse(list(positions), safe=False)


def get_departments(request):
    """AJAX представление для получения отделов по организации и подразделению"""
    organization_id = request.GET.get('organization')
    subdivision_id = request.GET.get('subdivision')

    departments = Department.objects.filter(
        organization_id=organization_id,
        subdivision_id=subdivision_id
    ).values('id', 'name')

    return JsonResponse(list(departments), safe=False)


@login_required
@require_POST
def update_position_instructions(request, pk):
    position = get_object_or_404(
        Position.objects.select_related('organization', 'subdivision', 'department'),
        pk=pk,
    )
    if not AccessControlHelper.can_access_object(request.user, position):
        return JsonResponse({'error': 'Нет доступа'}, status=403)

    position.safety_instructions_numbers = request.POST.get('safety_instructions_numbers', '').strip()
    position.contract_safety_instructions = request.POST.get('contract_safety_instructions', '').strip()
    position.company_vehicle_instructions = request.POST.get('company_vehicle_instructions', '').strip()
    position.is_responsible_for_safety = request.POST.get('is_responsible_for_safety') in {'1', 'true', 'True', 'on'}
    position.drives_company_vehicle = request.POST.get('drives_company_vehicle') in {'1', 'true', 'True', 'on'}

    try:
        position.full_clean()
        position.save(update_fields=[
            'safety_instructions_numbers',
            'contract_safety_instructions',
            'company_vehicle_instructions',
            'is_responsible_for_safety',
            'drives_company_vehicle',
        ])
    except ValidationError as exc:
        errors = []
        for field_errors in exc.message_dict.values():
            errors.extend(field_errors)
        return JsonResponse({'error': ' '.join(errors) or 'Ошибка валидации'}, status=400)

    return JsonResponse({
        'ok': True,
        'has_instructions': _position_has_instructions(position),
    })
