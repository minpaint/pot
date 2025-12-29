from django.views.generic import TemplateView
from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import render, redirect
from django.contrib import messages
from django.db.models import Prefetch

from directory.forms import EmployeeHiringForm
from directory.models import (
    Organization,
    StructuralSubdivision,
    Department,
    Employee,
    Position
)
from .auth import UserRegistrationView

# Импортируем представления для сотрудников
from .employees import (
    EmployeeListView,
    EmployeeCreateView,
    EmployeeUpdateView,
    EmployeeDeleteView,
    EmployeeHiringView,
    EmployeeProfileView, # Добавляем новое представление
    get_subdivisions
)

# Импортируем представления для должностей
from .positions import (
    PositionListView,
    PositionCreateView,
    PositionUpdateView,
    PositionDeleteView,
    get_positions,
    get_departments
)

# Импортируем представления из новой модульной структуры документов
# Используем абсолютный импорт, чтобы избежать конфликтов
from directory.views.documents import (
    DocumentSelectionView,
    GeneratedDocumentListView,
    document_download,
)

# Импортируем представления для выдачи СИЗ
from .siz_issued import (
    SIZIssueFormView,
    SIZPersonalCardView,
    SIZIssueReturnView,
    employee_siz_issued_list,
)

# Представления для медосмотров перемещены в deadline_control

# Импортируем представление вводного инструктажа и главной страницы
from .home import IntroductoryBriefingView, HomePageView

# ВАЖНО: HomePageView теперь импортируется из home.py (с фильтрацией по организациям)
# Старая реализация удалена - используется только версия из home.py


# Экспортируем все представления
__all__ = [
    'HomePageView',
    'IntroductoryBriefingView',
    'EmployeeListView',
    'EmployeeCreateView',
    'EmployeeUpdateView',
    'EmployeeDeleteView',
    'EmployeeHiringView',
    'EmployeeProfileView', # Добавляем в список экспорта
    'PositionListView',
    'PositionCreateView',
    'PositionUpdateView',
    'PositionDeleteView',
    'get_subdivisions',
    'get_positions',
    'get_departments',
    'UserRegistrationView',
    'DocumentSelectionView',
    'GeneratedDocumentListView',
    'document_download',
    'SIZIssueFormView',
    'SIZPersonalCardView',
    'SIZIssueReturnView',
    'employee_siz_issued_list',
]