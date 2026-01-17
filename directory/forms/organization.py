# directory/forms/organization.py
from django import forms
from crispy_forms.helper import FormHelper
from crispy_forms.layout import Submit
from dal import autocomplete
from directory.models import Organization


class OrganizationForm(forms.ModelForm):
    """🏢 Форма для организаций"""

    class Meta:
        model = Organization
        fields = '__all__'
        widgets = {
            'default_theory_consultant': autocomplete.ModelSelect2(
                url='directory:employee-autocomplete',
                attrs={
                    'data-placeholder': '👨‍🏫 Консультант теоретического обучения',
                    'class': 'select2-basic'
                }
            ),
            'default_commission_chairman': autocomplete.ModelSelect2(
                url='directory:employee-autocomplete',
                attrs={
                    'data-placeholder': '👔 Руководитель производственного обучения',
                    'class': 'select2-basic'
                }
            ),
            'default_instructor': autocomplete.ModelSelect2(
                url='directory:employee-autocomplete',
                attrs={
                    'data-placeholder': '🧑‍🏭 Инструктор производственного обучения',
                    'class': 'select2-basic'
                }
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # 🎨 Crispy-forms
        self.helper = FormHelper()
        self.helper.form_method = 'post'
        self.helper.add_input(Submit('submit', '💾 Сохранить'))

        # Фильтровать сотрудников по текущей организации
        if self.instance and self.instance.pk:
            org_id = self.instance.pk
            from directory.models import Employee
            qs = Employee.objects.filter(organization_id=org_id)
            self.fields['default_theory_consultant'].queryset = qs
            self.fields['default_commission_chairman'].queryset = qs
            self.fields['default_instructor'].queryset = qs