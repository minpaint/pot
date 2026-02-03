# deadline_control/urls.py
from django.urls import path, include
from deadline_control.views import equipment, key_deadline, dashboard, medical, medical_referral

app_name = 'deadline_control'

# ⚙️ ТО оборудования
equipment_patterns = [
    path('', equipment.EquipmentListView.as_view(), name='list'),  # По умолчанию табличное
    path('table/', equipment.EquipmentListView.as_view(), name='list_table'),  # Табличное
    path('tree/', equipment.EquipmentTreeView.as_view(), name='list_tree'),  # Древовидное
    path('create/', equipment.EquipmentCreateView.as_view(), name='create'),
    path('<int:pk>/', equipment.EquipmentDetailView.as_view(), name='detail'),
    path('<int:pk>/update/', equipment.EquipmentUpdateView.as_view(), name='update'),
    path('<int:pk>/delete/', equipment.EquipmentDeleteView.as_view(), name='delete'),
    path('<int:pk>/perform-maintenance/', equipment.perform_maintenance, name='perform_maintenance'),
    path('type/<int:type_id>/api/', equipment.equipment_type_api, name='type_api'),
    path('journal/', equipment.EquipmentJournalView.as_view(), name='journal'),
    path('journal/send-sample/<int:subdivision_id>/', equipment.send_equipment_journal_sample, name='send_journal_sample'),
    path('journal/send-organization/<int:organization_id>/', equipment.send_equipment_journals_for_organization, name='send_journals_organization'),
    path('journal/preview/<int:organization_id>/', equipment.preview_mass_send_equipment_journals, name='preview_journals'),
]

# 📅 Ключевые сроки
key_deadline_patterns = [
    path('', key_deadline.KeyDeadlineListView.as_view(), name='list'),
    path('category/create/', key_deadline.KeyDeadlineCategoryCreateView.as_view(), name='category_create'),
    path('category/<int:pk>/update/', key_deadline.KeyDeadlineCategoryUpdateView.as_view(), name='category_update'),
    path('category/<int:pk>/delete/', key_deadline.KeyDeadlineCategoryDeleteView.as_view(), name='category_delete'),
    path('item/create/', key_deadline.KeyDeadlineItemCreateView.as_view(), name='item_create'),
    path('item/<int:pk>/update/', key_deadline.KeyDeadlineItemUpdateView.as_view(), name='item_update'),
    path('item/<int:pk>/delete/', key_deadline.KeyDeadlineItemDeleteView.as_view(), name='item_delete'),
]

# 🏥 Медицинские осмотры
medical_patterns = [
    path('', medical.MedicalExaminationListView.as_view(), name='list'),
    path('<int:pk>/update-date/', medical.update_medical_date, name='update_date'),
    path('<int:pk>/perform-examination/', medical.perform_medical_examination, name='perform_examination'),
    # Детальная страница медосмотров сотрудника
    path('employee/<int:pk>/', medical.EmployeeMedicalDetailView.as_view(), name='employee_detail'),
    # Обновление всех медосмотров сотрудника
    path('employee/<int:employee_id>/update-examinations/', medical.update_employee_medical_examinations, name='update_employee_examinations'),
    # Массовое обновление медосмотров
    path('update-multiple/', medical.update_multiple_medical_examinations, name='update_multiple_examinations'),
    # Направления на медосмотр
    path('referral/employee/<int:employee_id>/', medical_referral.ExistingEmployeeReferralView.as_view(), name='referral_existing_employee'),
    # API для направлений
    path('referral/api/employee/<int:employee_id>/', medical_referral.EmployeeReferralDataView.as_view(), name='referral_employee_data'),
    path('referral/generate/', medical_referral.GenerateReferralView.as_view(), name='referral_generate'),
    # Скачивание направления
    path('referral/download/<int:referral_id>/', medical_referral.DownloadReferralView.as_view(), name='referral_download'),
    # Форма для направления нового сотрудника
    path('referral/new-employee/', medical_referral.NewEmployeeReferralView.as_view(), name='referral_new_employee'),
]

urlpatterns = [
    path('', dashboard.DashboardView.as_view(), name='dashboard'),
    path('equipment/', include((equipment_patterns, 'equipment'))),
    path('key-deadlines/', include((key_deadline_patterns, 'key_deadline'))),
    path('medical/', include((medical_patterns, 'medical'))),
]
