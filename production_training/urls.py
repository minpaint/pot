from django.urls import path

from .views import ProductionTrainingListView, program_lookup_view
from .autocomplete_views import (
    TrainingAssignmentEmployeeAutocomplete,
    TrainingAssignmentPositionAutocomplete,
)

app_name = 'production_training'

urlpatterns = [
    path('', ProductionTrainingListView.as_view(), name='training_list'),
    path(
        'autocomplete/employee-for-assignment/',
        TrainingAssignmentEmployeeAutocomplete.as_view(),
        name='employee-for-assignment-autocomplete',
    ),
    path(
        'autocomplete/position-for-assignment/',
        TrainingAssignmentPositionAutocomplete.as_view(),
        name='position-for-assignment-autocomplete',
    ),
    path('program-lookup/', program_lookup_view, name='program-lookup'),
]
