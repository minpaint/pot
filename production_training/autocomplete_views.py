# -*- coding: utf-8 -*-
"""
Автодополнение для формы TrainingAssignment.

У формы назначения на обучение нет собственного поля «organization» для
forward. Как и весь остальной admin, она должна подтягивать данные по
организации, выбранной в хэдере (request.session['selected_org_id'],
см. apply_session_org_filter / OrgFilterAdminMixin), а не по какому-то
полю самой формы. Обычные directory:employee-autocomplete /
directory:position-autocomplete требуют forwarded 'organization' и без
него всегда возвращают пустой queryset — здесь подставляем organization
из сессии перед вызовом родительской логики.
"""

from directory.autocomplete_views import EmployeeAutocomplete, PositionAutocomplete


def _forward_selected_org(request, forwarded):
    if forwarded.get('organization'):
        return forwarded

    selected_org_id = request.session.get('selected_org_id')
    if selected_org_id:
        forwarded = {**forwarded, 'organization': selected_org_id}
    return forwarded


class TrainingAssignmentEmployeeAutocomplete(EmployeeAutocomplete):
    """Сотрудники для назначения на обучение — организация берётся из хэдера."""

    def get_queryset(self):
        self.forwarded = _forward_selected_org(self.request, self.forwarded)
        return super().get_queryset()


class TrainingAssignmentPositionAutocomplete(PositionAutocomplete):
    """Должности для назначения на обучение — организация берётся из хэдера."""

    def get_queryset(self):
        self.forwarded = _forward_selected_org(self.request, self.forwarded)
        return super().get_queryset()
