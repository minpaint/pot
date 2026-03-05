from directory.utils.permissions import AccessControlHelper


def selected_organization(request):
    """
    Глобальный context processor для выбора организации.
    Предоставляет переменные global_org_options, global_selected_org_id,
    global_selected_org всем шаблонам.
    """
    if not request.user.is_authenticated:
        return {}

    accessible_orgs = AccessControlHelper.get_accessible_organizations(request.user, request)
    selected_org_id = request.session.get('selected_org_id')

    # Авто-выбор единственной организации
    if not selected_org_id and accessible_orgs.count() == 1:
        selected_org_id = accessible_orgs.first().id
        request.session['selected_org_id'] = selected_org_id

    selected_org = accessible_orgs.filter(id=selected_org_id).first() if selected_org_id else None

    return {
        'global_org_options': accessible_orgs,
        'global_selected_org_id': selected_org_id,
        'global_selected_org': selected_org,
    }
