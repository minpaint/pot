"""
👔 Форма для должностей с ограничением по организациям

Использует автодополнение для выбора организации, подразделения, отдела,
а также документов и оборудования, связанных с должностью.
Данные фильтруются по разрешённым организациям из профиля пользователя. 🚀
"""

from django import forms
from crispy_forms.helper import FormHelper
from crispy_forms.layout import Submit
from dal import autocomplete
from directory.models import Position, StructuralSubdivision, Department
from .mixins import OrganizationRestrictionFormMixin


class PositionForm(OrganizationRestrictionFormMixin, forms.ModelForm):
    class Meta:
        model = Position
        fields = '__all__'
        widgets = {
            'organization': autocomplete.ModelSelect2(
                url='directory:organization-autocomplete',
                attrs={'data-placeholder': '🏢 Выберите организацию...'}
            ),
            'subdivision': autocomplete.ModelSelect2(
                url='directory:subdivision-autocomplete',
                forward=['organization'],
                attrs={'data-placeholder': '🏭 Выберите подразделение...'}
            ),
            'department': autocomplete.ModelSelect2(
                url='directory:department-autocomplete',
                forward=['subdivision'],
                attrs={
                    'data-placeholder': '📂 Выберите отдел...',
                    'data-minimum-input-length': 0
                }
            ),
            'documents': autocomplete.ModelSelect2Multiple(
                url='directory:document-autocomplete',
                forward=['organization'],
                attrs={'data-placeholder': '📄 Выберите документы...'}
            ),
            'equipment': autocomplete.ModelSelect2Multiple(
                url='directory:equipment-autocomplete',
                forward=['organization', 'subdivision', 'department'],
                attrs={'data-placeholder': '⚙️ Выберите оборудование...'}
            ),
            'contract_work_name': forms.Textarea(attrs={'rows': 3}),
            'safety_instructions_numbers': forms.Textarea(attrs={'rows': 2}),
            'company_vehicle_instructions': forms.Textarea(attrs={'rows': 2}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # 🎨 Настройка crispy-forms
        self.helper = FormHelper()
        self.helper.form_method = 'post'
        self.helper.add_input(Submit('submit', '💾 Сохранить'))

        def _get_selected_id(field_name):
            if self.is_bound:
                value = self.data.get(field_name)
            else:
                value = None
            if not value:
                value = self.initial.get(field_name)
            if not value:
                current_obj = getattr(self.instance, field_name, None)
                value = getattr(current_obj, 'pk', None)
            if value in (None, "", "None"):
                return None
            try:
                return int(value)
            except (TypeError, ValueError):
                return value

        def _ensure_in_queryset(field_name, qs):
            current_obj = getattr(self.instance, field_name, None)
            current_id = getattr(current_obj, 'pk', None)
            if current_id and not qs.filter(pk=current_id).exists():
                qs = qs | qs.model.objects.filter(pk=current_id)
            self.fields[field_name].queryset = qs

        allowed_orgs = self.fields['organization'].queryset
        allowed_orgs_count = allowed_orgs.count()

        # ModelSelect2 uses AJAX and ignores the form's queryset restriction.
        # Switch to plain Select when restricted to 1 org so the dropdown only
        # shows that org instead of all organizations from the autocomplete endpoint.
        if allowed_orgs_count == 1:
            self.fields['organization'].widget = forms.Select(
                attrs={'class': 'form-select'},
                choices=self.fields['organization'].choices,
            )

        if not self.is_bound and allowed_orgs_count == 1 and not self.initial.get('organization'):
            self.initial['organization'] = allowed_orgs.first().pk

        organization_id = _get_selected_id('organization')
        subdivision_id = _get_selected_id('subdivision')
        department_id = _get_selected_id('department')

        if organization_id:
            subdivision_qs = StructuralSubdivision.objects.filter(
                organization_id=organization_id,
                organization__in=allowed_orgs
            )
        else:
            subdivision_qs = StructuralSubdivision.objects.none()
        _ensure_in_queryset('subdivision', subdivision_qs)

        if subdivision_id:
            department_qs = Department.objects.filter(subdivision_id=subdivision_id)
            if organization_id:
                department_qs = department_qs.filter(organization_id=organization_id)
        else:
            department_qs = Department.objects.none()
        _ensure_in_queryset('department', department_qs)

        docs_qs = self.fields['documents'].queryset
        equip_qs = self.fields['equipment'].queryset
        if organization_id:
            docs_qs = docs_qs.filter(organization_id=organization_id)
            equip_qs = equip_qs.filter(organization_id=organization_id)
            if department_id:
                equip_qs = equip_qs.filter(department_id=department_id)
            elif subdivision_id:
                equip_qs = equip_qs.filter(subdivision_id=subdivision_id)
        else:
            docs_qs = docs_qs.none()
            equip_qs = equip_qs.none()

        if self.instance.pk:
            docs_qs = docs_qs | self.instance.documents.all()
            equip_qs = equip_qs | self.instance.equipment.all()

        self.fields['documents'].queryset = docs_qs.distinct()
        self.fields['equipment'].queryset = equip_qs.distinct()
