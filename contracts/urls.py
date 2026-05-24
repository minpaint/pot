from django.urls import path
from . import views

app_name = 'contracts'

urlpatterns = [
    path('act/<int:pk>/toggle-paid/', views.toggle_act_paid, name='toggle_act_paid'),
]
