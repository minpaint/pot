"""
Админ-панель для приложения 'Контроль сроков'
"""
from .equipment import EquipmentAdmin
from .equipment_type import EquipmentTypeAdmin
from .key_deadline import KeyDeadlineCategoryAdmin, OrganizationKeyDeadlineAdmin
from .medical_examination import (
    MedicalExaminationTypeAdmin,
    HarmfulFactorAdmin,
    MedicalSettingsAdmin,
    MedicalExaminationNormAdmin,
    EmployeeMedicalExaminationAdmin,
)
from .medical_referral import MedicalReferralAdmin
from .email_settings import EmailSettingsAdmin
from .email_template import EmailTemplateTypeAdmin, EmailTemplateAdmin
from .send_log import InstructionJournalSendLogAdmin
from .equipment_send_log import EquipmentJournalSendLogAdmin
from .medical_send_log import MedicalNotificationSendLogAdmin
from .key_deadline_send_log import KeyDeadlineSendLogAdmin
from .hiring_send_log import DocumentEmailSendLogAdmin

__all__ = [
    'EquipmentAdmin',
    'EquipmentTypeAdmin',
    'KeyDeadlineCategoryAdmin',
    'OrganizationKeyDeadlineAdmin',
    'MedicalExaminationTypeAdmin',
    'HarmfulFactorAdmin',
    'MedicalSettingsAdmin',
    'MedicalExaminationNormAdmin',
    'EmployeeMedicalExaminationAdmin',
    'MedicalReferralAdmin',
    'EmailSettingsAdmin',
    'EmailTemplateTypeAdmin',
    'EmailTemplateAdmin',
    'InstructionJournalSendLogAdmin',
    'EquipmentJournalSendLogAdmin',
    'MedicalNotificationSendLogAdmin',
    'KeyDeadlineSendLogAdmin',
    'DocumentEmailSendLogAdmin',
]
