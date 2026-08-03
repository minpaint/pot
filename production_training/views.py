from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import JsonResponse
from django.views.generic import ListView

from .models import TrainingAssignment, TrainingProgram


class ProductionTrainingListView(LoginRequiredMixin, ListView):
    model = TrainingAssignment
    template_name = 'production_training/training_list.html'
    context_object_name = 'assignments'
    paginate_by = 50

    def get_queryset(self):
        return super().get_queryset().select_related(
            'employee',
            'current_position',
            'training',
            'training__profession',
            'training__training_type',
            'training__organization',
            'training__subdivision',
            'training__department',
        )


@login_required
def program_lookup_view(request):
    """
    AJAX: подобрать программу обучения по типу обучения + профессии (+ разряду).

    Если найдена ровно одна подходящая программа — возвращает её id/название
    для автоподстановки. Если ни одной или несколько — не подставляет ничего,
    оставляя выбор пользователю.
    """
    training_type_id = request.GET.get('training_type_id')
    profession_id = request.GET.get('profession_id')
    qualification_grade_id = request.GET.get('qualification_grade_id') or None

    if not training_type_id or not profession_id:
        return JsonResponse({'program_id': None})

    qs = TrainingProgram.objects.filter(
        is_active=True,
        training_type_id=training_type_id,
        profession_id=profession_id,
    )
    if qualification_grade_id:
        qs = qs.filter(qualification_grade_id=qualification_grade_id)

    programs = list(qs[:2])

    if len(programs) == 1:
        program = programs[0]
        return JsonResponse({'program_id': program.id, 'program_text': str(program)})

    return JsonResponse({'program_id': None})
