# directory/forms/document_forms.py
"""
📝 Формы для работы с документами

Этот модуль содержит формы для выбора и настройки параметров документов.
"""

from django import forms
from django.utils.translation import gettext_lazy as _
from crispy_forms.helper import FormHelper
from crispy_forms.layout import Layout, Fieldset, ButtonHolder, Submit, Div, HTML, Button, Field
from directory.models.document_template import DocumentTemplate, DocumentTemplateType
from directory.models import Employee


class DocumentSelectionForm(forms.Form):
    """
    Форма для выбора типов документов для генерации.
    """
    document_types = forms.MultipleChoiceField(
        label=_("Типы документов"),
        choices=[],  # Будет заполнено в __init__
        widget=forms.CheckboxSelectMultiple,
        required=True,
        help_text=_("Выберите один или несколько типов документов для генерации")
    )

    employee_id = forms.IntegerField(
        widget=forms.HiddenInput(),
        required=True
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Получаем choices из справочника DocumentTemplateType
        choices = [
            (template_type.code, template_type.name)
            for template_type in DocumentTemplateType.objects.filter(is_active=True)
            if template_type.code != 'periodic_protocol'  # Исключаем периодический протокол
        ]
        self.fields['document_types'].choices = choices
        self.helper = FormHelper()
        self.helper.form_method = 'post'
        self.helper.form_id = 'document-selection-form'
        self.helper.layout = Layout(
            'employee_id',
            Fieldset(
                _('Выберите типы документов для генерации'),
                Field('document_types'),
                css_class='mb-3'
            ),
            ButtonHolder(
                Submit('submit', _('Сгенерировать документы'), css_class='btn-primary'),
                Button('cancel', _('Отмена'), css_class='btn-secondary',
                       onclick="window.history.back();")
            )
        )