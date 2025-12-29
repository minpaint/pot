# directory/models/__init__.py
from .organization import Organization
from .subdivision import StructuralSubdivision
from .subdivision_email import SubdivisionEmail
from .department import Department
from .document import Document
from .position import Position, ResponsibilityType
from .employee import Employee
from .profile import Profile
from .menu_item import MenuItem
from .siz_issued import SIZIssued
from .siz import SIZ, SIZNorm
from .document_template import DocumentTemplateType, DocumentTemplate, GeneratedDocument, DocumentGenerationLog
from .commission import Commission, CommissionMember
from .hiring import EmployeeHiring
# Добавляем импорт моделей экзаменов
from .quiz import QuizCategory, QuizCategoryOrder, Quiz, Question, Answer, QuizAttempt, UserAnswer, QuizAccessToken, QuizQuestionOrder

__all__ = [
    'Organization',
    'Profile',
    'MenuItem',
    'StructuralSubdivision',
    'SubdivisionEmail',
    'Department',
    'Document',
    'Position',
    'ResponsibilityType',
    'Employee',
    'SIZIssued',
    'SIZ',
    'SIZNorm',
    'DocumentTemplate',
    'DocumentTemplateType',
    'GeneratedDocument',
    'DocumentGenerationLog',
    'Commission',
    'CommissionMember',
    'EmployeeHiring',
    # Добавляем модели экзаменов в список экспорта
    'QuizCategory',
    'QuizCategoryOrder',
    'Quiz',
    'Question',
    'Answer',
    'QuizAttempt',
    'UserAnswer',
    'QuizAccessToken',
    'QuizQuestionOrder',
]
