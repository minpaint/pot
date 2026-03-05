# directory/admin/mixins/org_filter.py


class OrgFilterAdminMixin:
    """
    Миксин для AdminModelAdmin-классов, фильтрующий queryset по выбранной
    организации из сессии. Применяется только если в GET-параметрах нет
    явного фильтра по организации (organization__id__exact / organization_id).
    """

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        has_org_get_filter = bool(
            request.GET.get('organization__id__exact') or
            request.GET.get('organization_id')
        )
        if not has_org_get_filter:
            selected_org_id = request.session.get('selected_org_id')
            if selected_org_id:
                qs = qs.filter(organization_id=selected_org_id)
        return qs
