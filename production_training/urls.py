from django.urls import path

from .views import ProductionTrainingListView

app_name = 'production_training'

urlpatterns = [
    path('', ProductionTrainingListView.as_view(), name='training_list'),
]
