from django.urls import path
from . import views

app_name = 'tasks'

urlpatterns = [
    path('item/<int:pk>/toggle/',   views.toggle_item,  name='toggle_item'),
    path('item/<int:pk>/delete/',   views.delete_item,  name='delete_item'),
    path('list/<int:list_pk>/add/', views.add_item,     name='add_item'),
    path('list/add/',               views.add_list,     name='add_list'),
    path('list/<int:pk>/delete/',   views.delete_list,  name='delete_list'),
    path('list/<int:pk>/archive/',  views.archive_list, name='archive_list'),
]
