# directory/forms/department.py
"""
📂 Форма для отделов с ограничением по организациям и иерархической фильтрацией

Эта форма позволяет создавать и редактировать отделы, при этом:
- Поля "organization" и "subdivision" фильтруются по организациям, доступным пользователю. 🚀
"""

from django import forms
from crispy_forms.helper import FormHelper
from crispy_forms.layout import Submit
from dal import autocomplete
from directory.models import Department
from .mixins import OrganizationRestrictionFormMixin  # Импорт миксина 🚀


class DepartmentForm(OrganizationRestrictionFormMixin, forms.ModelForm):
    class Meta:
        model = Department
        fields = ['name', 'short_name', 'organization', 'subdivision']
        widgets = {
            'organization': autocomplete.ModelSelect2(
                url='directory:organization-autocomplete',
                attrs={'data-placeholder': '🏢 Выберите организацию...'}
            ),
            'subdivision': autocomplete.ModelSelect2(
                url='directory:subdivision-autocomplete',
                forward=['organization'],
                attrs={'data-placeholder': '🏭 Выберите подразделение...'}
            )
        }

    def __init__(self, *args, **kwargs):
        # user/initial_org_id обрабатывает OrganizationRestrictionFormMixin.__init__ —
        # не извлекаем их здесь заранее, иначе миксин перезатрёт self.user значением None
        super().__init__(*args, **kwargs)

        # 🎨 Настройка crispy-forms
        self.helper = FormHelper()
        self.helper.form_method = 'post'
        self.helper.add_input(Submit('submit', '💾 Сохранить'))
