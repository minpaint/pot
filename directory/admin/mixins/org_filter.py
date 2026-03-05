# directory/admin/mixins/org_filter.py

DEFAULT_ORG_GET_FILTER_KEYS = (
    'organization__id__exact',
    'organization_id',
)


def apply_session_org_filter(
    request,
    qs,
    organization_lookup='organization_id',
    get_filter_keys=None,
):
    """
    Фильтрует queryset по selected_org_id из сессии,
    если в URL нет явного фильтра по организации.
    """
    keys = get_filter_keys or DEFAULT_ORG_GET_FILTER_KEYS
    has_org_get_filter = any(request.GET.get(key) for key in keys)
    if has_org_get_filter:
        return qs

    selected_org_id = request.session.get('selected_org_id')
    try:
        selected_org_id = int(selected_org_id)
    except (TypeError, ValueError):
        return qs

    return qs.filter(**{organization_lookup: selected_org_id})


class OrgFilterAdminMixin:
    """
    Миксин для AdminModelAdmin-классов, фильтрующий queryset по выбранной
    организации из сессии.
    """

    org_filter_lookup = 'organization_id'
    org_filter_get_params = DEFAULT_ORG_GET_FILTER_KEYS

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return apply_session_org_filter(
            request,
            qs,
            organization_lookup=self.org_filter_lookup,
            get_filter_keys=self.org_filter_get_params,
        )
