"""
Модели приложения 'Контроль сроков'
"""
from .equipment import Equipment
from .equipment_type import EquipmentType
from .key_deadline import KeyDeadlineCategory, KeyDeadlineItem, OrganizationKeyDeadline
from .medical_examination import HarmfulFactor, MedicalExaminationType, MedicalSettings
from .medical_norm import MedicalExaminationNorm, PositionMedicalFactor, EmployeeMedicalExamination
from .medical_referral import MedicalReferral
from .email_settings import EmailSettings
from .email_template import EmailTemplateType, EmailTemplate
from .send_log import InstructionJournalSendLog, InstructionJournalSendDetail
from .equipment_send_log import EquipmentJournalSendLog, EquipmentJournalSendDetail
from .medical_send_log import MedicalNotificationSendLog, MedicalNotificationSendDetail
from .key_deadline_send_log import KeyDeadlineSendLog

__all__ = [
    'Equipment',
    'EquipmentType',
    'KeyDeadlineCategory',
    'KeyDeadlineItem',
    'OrganizationKeyDeadline',
    'HarmfulFactor',
    'MedicalExaminationType',
    'MedicalSettings',
    'MedicalExaminationNorm',
    'PositionMedicalFactor',
    'EmployeeMedicalExamination',
    'MedicalReferral',
    'EmailSettings',
    'EmailTemplateType',
    'EmailTemplate',
    'InstructionJournalSendLog',
    'InstructionJournalSendDetail',
    'EquipmentJournalSendLog',
    'EquipmentJournalSendDetail',
    'MedicalNotificationSendLog',
    'MedicalNotificationSendDetail',
    'KeyDeadlineSendLog',
]
