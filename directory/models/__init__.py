# directory/models/__init__.py
from .organization import Organization
from .subdivision import StructuralSubdivision
from .subdivision_email import SubdivisionEmail
from .department import Department
from .department_email import DepartmentEmail
from .document import Document
from .position import Position, ResponsibilityType
from .employee import Employee
from .profile import Profile
from .menu_item import MenuItem
from .siz import SIZ, SIZNorm, SIZIssued, ProfessionSIZNorm
from .document_template import DocumentTemplateType, DocumentTemplate, GeneratedDocument, DocumentGenerationLog, DocumentEmailSendLog
from .commission import Commission, CommissionMember
from .hiring import EmployeeHiring
# Добавляем импорт моделей экзаменов
from .quiz import QuizCategory, QuizCategoryOrder, Quiz, Question, Answer, QuizAttempt, UserAnswer, QuizAccessToken, QuizQuestionOrder
# Лог импортов
from .import_log import ImportLog
# Асинхронные задачи генерации документов
from .generation_job import GenerationJob

__all__ = [
    'Organization',
    'Profile',
    'MenuItem',
    'StructuralSubdivision',
    'SubdivisionEmail',
    'Department',
    'DepartmentEmail',
    'Document',
    'Position',
    'ResponsibilityType',
    'Employee',
    'SIZIssued',
    'SIZ',
    'SIZNorm',
    'ProfessionSIZNorm',
    'DocumentTemplate',
    'DocumentTemplateType',
    'GeneratedDocument',
    'DocumentGenerationLog',
    'DocumentEmailSendLog',
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
    'ImportLog',
    'GenerationJob',
]
