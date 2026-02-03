from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import ListView

from .models import TrainingAssignment


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
