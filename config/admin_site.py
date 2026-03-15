# config/admin_site.py

import logging
from collections import OrderedDict

from django.contrib.admin import AdminSite
from django.db import DatabaseError
from django.utils.translation import gettext_lazy as _

logger = logging.getLogger(__name__)

class OTAdminSite(AdminSite):
    site_header = "OT-online Администрирование"
    site_title = "OT-online"
    index_title = "Панель управления"

    MENU_ORDER = OrderedDict([
        (_("🏢 Организация"), [
            "Organization", "Subdivision", "Department", "StructuralSubdivision",
        ]),
        (_("👥 Сотрудники и должности"), [
            "Position", "Employee", "ResponsibilityType",
        ]),
        (_("📑 Прием на работу"), [
            "EmployeeHiring", "Commission",
        ]),
        (_("🏥 Медосмотры"), [
            "MedicalSettings",
            "MedicalExaminationType",
            "HarmfulFactor",
            "PositionMedicalFactor",
            "EmployeeMedicalExamination",
            "MedicalExaminationNorm",
            "MedicalReferral",
        ]),
        (_("🕐 Контроль сроков"), [
            "Equipment",
            "EquipmentType",
            "KeyDeadlineCategory",
            "OrganizationKeyDeadline",
            "EmployeeMedicalExamination",
        ]),
        (_("🛡️ СИЗ"), [
            "SIZ", "SIZNorm",
        ]),
        (_("📧 Уведомления"), [
            "EmailSettings",
            "EmailTemplateType",
            "EmailTemplate",
        ]),
        (_("📨 Исходящие письма"), [
            "InstructionJournalSendLog",
            "MedicalNotificationSendLog",
            "KeyDeadlineSendLog",
            "EquipmentJournalSendLog",
            "DocumentEmailSendLog",
        ]),
        (_("📄 Документы и шаблоны"), [
            "Document", "DocumentTemplateType", "DocumentTemplate", "GeneratedDocument", "DocumentGenerationLog",
        ]),
        (_("🎓 Обучение на производстве"), [
            "ProductionTraining",
            "TrainingAssignment",
            "TrainingType",
            "TrainingProfession",
            "TrainingQualificationGrade",
            "EducationLevel",
            "TrainingProgram",
        ]),
        (_("📊 Импорт/Экспорт данных"), [
            "ImportExportMenu",
        ]),
        (_("🔑 Администрирование доступа"), [
            "UserProxy", "GroupProxy",
        ]),
    ])

    def each_context(self, request):
        context = super().each_context(request)
        if request.user.is_authenticated:
            try:
                from directory.utils.permissions import AccessControlHelper
                accessible_orgs = AccessControlHelper.get_accessible_organizations(request.user, request)
                selected_org_id = request.session.get('selected_org_id')
                if not selected_org_id and accessible_orgs.count() == 1:
                    selected_org_id = accessible_orgs.first().id
                    request.session['selected_org_id'] = selected_org_id
                selected_org = accessible_orgs.filter(id=selected_org_id).first() if selected_org_id else None
                context.update({
                    'global_org_options': accessible_orgs,
                    'global_selected_org_id': selected_org_id,
                    'global_selected_org': selected_org,
                })
            except Exception:
                pass
        return context

    def get_app_list(self, request, app_label=None):
        """
        Возвращает меню, сгруппированное по логическим блокам.
        """
        try:
            app_list = super().get_app_list(request, app_label)
        except DatabaseError:
            logger.exception(
                "DatabaseError in OTAdminSite.get_app_list",
                extra={
                    'path': request.path,
                    'query_params': dict(request.GET),
                    'user': getattr(request.user, 'username', None),
                },
            )
            raise

        # Плоский список всех моделей
        all_models = []
        for app in app_list:
            all_models.extend(app['models'])

        # Распределение по группам
        grouped_apps = OrderedDict()
        for section, models in self.MENU_ORDER.items():
            grouped_apps[section] = {'name': section, 'models': []}
            for model in models:
                for m in all_models:
                    if m['object_name'] == model:
                        grouped_apps[section]['models'].append(m)

        # Экзамены
        grouped_apps["💻 Проверка знаний"] = {'name': "💻 Проверка знаний", 'models': []}
        for m in all_models:
            if not any(m['object_name'] in models for models in self.MENU_ORDER.values()):
                grouped_apps["💻 Проверка знаний"]['models'].append(m)

        return [section for section in grouped_apps.values() if section['models']]
