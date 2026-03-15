"""
🏭 Форма для структурных подразделений с ограничением по организациям

Использует автодополнение для выбора организации.
Данные фильтруются по разрешённым организациям из профиля пользователя. 🚀
"""

from django import forms
from crispy_forms.helper import FormHelper
from crispy_forms.layout import Submit
from dal import autocomplete
from directory.models import StructuralSubdivision
from .mixins import OrganizationRestrictionFormMixin


class StructuralSubdivisionForm(OrganizationRestrictionFormMixin, forms.ModelForm):
    class Meta:
        model = StructuralSubdivision
        fields = ['name', 'short_name', 'organization', 'skip_email_notifications']
        widgets = {
            'organization': autocomplete.ModelSelect2(
                url='directory:organization-autocomplete',
                attrs={'data-placeholder': '🏢 Выберите организацию...'}
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # 🎨 Настройка crispy-forms
        self.helper = FormHelper()
        self.helper.form_method = 'post'
        self.helper.add_input(Submit('submit', '💾 Сохранить'))
