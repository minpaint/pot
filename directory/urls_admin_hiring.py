# directory/urls_admin_hiring.py
"""
URL маршруты для admin actions EmployeeHiring
"""

from django.urls import path
from directory.views.admin_hiring_actions import admin_hiring_documents_action

urlpatterns = [
    path('documents-action/', admin_hiring_documents_action, name='admin_hiring_documents_action'),
]
