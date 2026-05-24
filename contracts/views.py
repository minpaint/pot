from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.http import require_POST

from .models import Act


def superuser_required(view_func):
    """Декоратор: только суперпользователь."""
    from django.core.exceptions import PermissionDenied
    from functools import wraps
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_superuser:
            raise PermissionDenied
        return view_func(request, *args, **kwargs)
    return wrapper


@login_required
@superuser_required
@require_POST
def toggle_act_paid(request, pk):
    """AJAX: переключить статус оплаты акта."""
    from django.utils import timezone
    act = get_object_or_404(Act, pk=pk)
    act.is_paid = not act.is_paid
    act.paid_date = timezone.now().date() if act.is_paid else None
    act.save(update_fields=['is_paid', 'paid_date'])
    return JsonResponse({
        'is_paid': act.is_paid,
        'paid_date': act.paid_date.strftime('%d.%m.%Y') if act.paid_date else None,
    })
