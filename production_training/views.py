from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import ListView

from .models import ProductionTraining


class ProductionTrainingListView(LoginRequiredMixin, ListView):
    model = ProductionTraining
    template_name = 'production_training/training_list.html'
    context_object_name = 'trainings'
    paginate_by = 50

    def get_queryset(self):
        qs = super().get_queryset().select_related(
            'employee', 'profession', 'training_type', 'organization', 'subdivision', 'department'
        )
        return qs
