# directory/admin/mixins/org_filter.py
from django.db.models import Q

DEFAULT_ORG_GET_FILTER_KEYS = (
    'organization__id__exact',
    'organization_id',
)


def apply_session_org_filter(
    request,
    qs,
    organization_lookup='organization_id',
    get_filter_keys=None,
    include_null_org=False,
    null_org_lookup='organization__isnull',
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

    org_filter = Q(**{organization_lookup: selected_org_id})
    if include_null_org:
        org_filter |= Q(**{null_org_lookup: True})
    return qs.filter(org_filter)


class OrgFilterAdminMixin:
    """
    Миксин для ModelAdmin-классов с единой логикой фильтрации по организации:
    - обычные пользователи (не staff): фильтр по profile.organizations
    - admin/superuser: фильтр по selected_org_id из сессии (хэдер)
    """

    org_filter_lookup = 'organization_id'      # lookup для сессионного фильтра
    org_profile_lookup = 'organization__in'    # lookup для профильного фильтра
    org_filter_get_params = DEFAULT_ORG_GET_FILTER_KEYS

    def get_queryset(self, request):
        qs = super().get_queryset(request)

        # Обычные пользователи — фильтр по profile.organizations
        if not (request.user.is_superuser or request.user.is_staff):
            if hasattr(request.user, 'profile'):
                qs = qs.filter(**{self.org_profile_lookup: request.user.profile.organizations.all()})
            else:
                return qs.none()

        # Для всех пользователей — дополнительный фильтр по выбранной org в хэдере
        return apply_session_org_filter(
            request,
            qs,
            organization_lookup=self.org_filter_lookup,
            get_filter_keys=self.org_filter_get_params,
        )
