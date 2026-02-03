# directory/forms/employee.py
"""
👤 Форма для сотрудников с ограничением по организациям и иерархической фильтрацией

Обеспечивает выбор организации, подразделения, отдела и должности,
при этом данные фильтруются согласно доступным организациям из профиля пользователя. 🚀
"""

from django import forms
from crispy_forms.helper import FormHelper
from crispy_forms.layout import Submit
from dal import autocomplete
from directory.models import Employee, StructuralSubdivision, Department, Position
from .mixins import OrganizationRestrictionFormMixin  # Импорт миксина 🚀


class EmployeeForm(OrganizationRestrictionFormMixin, forms.ModelForm):
    class Meta:
        model = Employee
        fields = [
            "full_name_nominative",
            "full_name_by",
            "date_of_birth", "place_of_residence", "email",
            "organization", "subdivision", "department", "position",
            "work_schedule",
            "education_level",
            "prior_qualification",
            "height", "clothing_size", "shoe_size",
            "is_contractor"
        ]
        widgets = {
            "organization": autocomplete.ModelSelect2(
                url="directory:organization-autocomplete",
                attrs={
                    "data-placeholder": "🏢 Выберите организацию...",
                    "class": "select2-basic"
                }
            ),
            "subdivision": autocomplete.ModelSelect2(
                url="directory:subdivision-autocomplete",
                forward=["organization"],
                attrs={
                    "data-placeholder": "🏭 Выберите подразделение...",
                    "class": "select2-basic"
                }
            ),
            "department": autocomplete.ModelSelect2(
                url="directory:department-autocomplete",
                forward=["subdivision"],
                attrs={
                    "data-placeholder": "📂 Выберите отдел...",
                    "class": "select2-basic"
                }
            ),
            "position": autocomplete.ModelSelect2(
                url="directory:position-autocomplete",
                forward=["organization", "subdivision", "department"],
                attrs={
                    "data-placeholder": "👔 Выберите должность...",
                    "class": "select2-basic"
                }
            ),
            "date_of_birth": forms.DateInput(
                attrs={"type": "date"},
                format="%Y-%m-%d"
            ),
            "place_of_residence": forms.TextInput(
                attrs={
                    "size": "50",
                    "placeholder": "Населенный пункт"
                }
            ),
            "education_level": forms.TextInput(
                attrs={
                    "size": "50",
                    "placeholder": "Например: среднее специальное"
                }
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # 🎨 Настройка crispy-forms
        self.helper = FormHelper()
        self.helper.form_method = "post"
        self.helper.add_input(Submit("submit", "💾 Сохранить"))

        # Делам поля subdivision и department необязательными 🔧
        self.fields["subdivision"].required = False
        self.fields["department"].required = False

        def _get_selected_id(field_name):
            if self.is_bound:
                value = self.data.get(field_name)
            else:
                value = None
            if not value:
                value = self.initial.get(field_name)
            if not value:
                current_obj = getattr(self.instance, field_name, None)
                value = getattr(current_obj, "pk", None)
            if value in (None, "", "None"):
                return None
            try:
                return int(value)
            except (TypeError, ValueError):
                return value

        def _ensure_in_queryset(field_name, qs):
            current_obj = getattr(self.instance, field_name, None)
            current_id = getattr(current_obj, "pk", None)
            if current_id and not qs.filter(pk=current_id).exists():
                qs = qs | qs.model.objects.filter(pk=current_id)
            self.fields[field_name].queryset = qs

        allowed_orgs = self.fields["organization"].queryset

        # Если у пользователя одна организация – ставим её по умолчанию
        if not self.is_bound and allowed_orgs.count() == 1 and not self.initial.get("organization"):
            self.initial["organization"] = allowed_orgs.first().pk

        organization_id = _get_selected_id("organization")
        subdivision_id = _get_selected_id("subdivision")
        department_id = _get_selected_id("department")

        if organization_id:
            subdivision_qs = StructuralSubdivision.objects.filter(
                organization_id=organization_id,
                organization__in=allowed_orgs
            )
        else:
            subdivision_qs = StructuralSubdivision.objects.none()
        _ensure_in_queryset("subdivision", subdivision_qs)

        if subdivision_id:
            department_qs = Department.objects.filter(subdivision_id=subdivision_id)
            if organization_id:
                department_qs = department_qs.filter(organization_id=organization_id)
        else:
            department_qs = Department.objects.none()
        _ensure_in_queryset("department", department_qs)

        if organization_id:
            position_qs = Position.objects.filter(organization_id=organization_id)
            if department_id:
                position_qs = position_qs.filter(department_id=department_id)
            elif subdivision_id:
                position_qs = position_qs.filter(subdivision_id=subdivision_id)
            else:
                position_qs = position_qs.filter(subdivision__isnull=True)
        else:
            position_qs = Position.objects.none()
        _ensure_in_queryset("position", position_qs)

    def clean(self):
        """
        🛠 Дополнительные проверки перед сохранением:
        - Если выбрано подразделение, но не выбрана организация, устанавливаем организацию.
        - Если выбрано подразделение, но не указан отдел – очищаем поле department.
        """
        cleaned_data = super().clean()
        organization = cleaned_data.get("organization")
        subdivision = cleaned_data.get("subdivision")
        department = cleaned_data.get("department")

        if subdivision and not organization:
            cleaned_data["organization"] = subdivision.organization

        if subdivision and not department:
            cleaned_data["department"] = None

        return cleaned_data
