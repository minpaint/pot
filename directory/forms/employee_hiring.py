from django import forms
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from crispy_forms.helper import FormHelper
from crispy_forms.layout import Submit, Layout, Fieldset, Div, HTML, Button, Field, Row, Column
from dal import autocomplete

# Миксин, который ограничивает список организаций по профилю пользователя
from directory.forms.mixins import OrganizationRestrictionFormMixin

# Прямой импорт модели Employee
from directory.models.employee import Employee


class EmployeeHiringForm(OrganizationRestrictionFormMixin, forms.ModelForm):
    """
    👥 Форма для найма сотрудника, использующая django-autocomplete-light (DAL).
    Содержит все поля модели Employee, включая место проживания, рост и т.д.
    """

    class Meta:
        model = Employee
        fields = [
            'full_name_nominative',  # ФИО (именительный) 📝
            'date_of_birth',         # Дата рождения 📅
            'place_of_residence',    # Место проживания 🏠
            'hire_date',             # Дата приема 📅
            'start_date',            # Дата начала работы 📅
            'contract_type',         # Вид договора (заменяет is_contractor) 📄
            'organization',          # Организация 🏢
            'subdivision',           # Подразделение 🏭
            'department',            # Отдел 📂
            'position',              # Должность 👔
            'height',                # Рост 📏
            'clothing_size',         # Размер одежды 👕
            'shoe_size',             # Размер обуви 👞
        ]
        widgets = {
            'contract_type': forms.Select(
                attrs={
                    'class': 'form-control',
                    'data-placeholder': '📄 Выберите вид договора...'
                }
            ),
            'hire_date': forms.DateInput(
                attrs={'type': 'date', 'class': 'form-control'},
                format='%Y-%m-%d'
            ),
            'start_date': forms.DateInput(
                attrs={'type': 'date', 'class': 'form-control'},
                format='%Y-%m-%d'
            ),
            'organization': autocomplete.ModelSelect2(
                url='directory:organization-autocomplete',
                attrs={
                    'data-placeholder': '🏢 Выберите организацию...',
                    'class': 'select2 form-control',
                    'data-theme': 'bootstrap4',
                    'style': 'width: 100%; text-align: left;'
                }
            ),
            'subdivision': autocomplete.ModelSelect2(
                url='directory:subdivision-autocomplete',
                forward=['organization'],
                attrs={
                    'data-placeholder': '🏭 Выберите подразделение...',
                    'class': 'select2 form-control',
                    'data-theme': 'bootstrap4',
                    'style': 'width: 100%; text-align: left;'
                }
            ),
            'department': autocomplete.ModelSelect2(
                url='directory:department-autocomplete',
                forward=['subdivision'],
                attrs={
                    'data-placeholder': '📂 Выберите отдел...',
                    'class': 'select2 form-control',
                    'data-theme': 'bootstrap4',
                    'style': 'width: 100%; text-align: left;'
                }
            ),
            'position': autocomplete.ModelSelect2(
                url='directory:position-autocomplete',
                forward=['organization', 'subdivision', 'department'],
                attrs={
                    'data-placeholder': '👔 Выберите должность...',
                    'class': 'select2 form-control',
                    'data-theme': 'bootstrap4',
                    'style': 'width: 100%; text-align: left;'
                }
            ),
            'date_of_birth': forms.DateInput(
                attrs={'type': 'date', 'class': 'form-control'},
                format='%Y-%m-%d'
            ),
            'place_of_residence': forms.Textarea(
                attrs={
                    'class': 'form-control',
                    'rows': 3,
                    'placeholder': '🏠 Введите место проживания...'
                }
            ),
            'height': forms.Select(
                attrs={'class': 'form-control'}
            ),
            'clothing_size': forms.Select(
                attrs={'class': 'form-control'}
            ),
            'shoe_size': forms.Select(
                attrs={'class': 'form-control'}
            ),
        }

    def __init__(self, *args, **kwargs):
        # user/initial_org_id обрабатывает OrganizationRestrictionFormMixin.__init__ —
        # не извлекаем их здесь заранее, иначе миксин перезатрёт self.user значением None
        super().__init__(*args, **kwargs)

        # 🎨 Настройка crispy-forms
        self.helper = FormHelper()
        self.helper.form_method = 'post'
        self.helper.layout = Layout(
            Fieldset(
                _('Информация о приеме на работу'),
                Row(
                    Column('hire_date', css_class='form-group col-md-6'),
                    Column('start_date', css_class='form-group col-md-6'),
                    css_class='form-row'
                ),
                Row(
                    Column('contract_type', css_class='form-group col-md-12'),
                    css_class='form-row'
                ),
                css_class='mb-3'
            ),
            Fieldset(
                _('Организационная структура'),
                Row(
                    Column('organization', css_class='form-group col-md-12'),
                    css_class='form-row'
                ),
                Row(
                    Column('subdivision', css_class='form-group col-md-6'),
                    Column('department', css_class='form-group col-md-6'),
                    css_class='form-row'
                ),
                Row(
                    Column('position', css_class='form-group col-md-12'),
                    css_class='form-row'
                ),
                css_class='mb-3'
            ),
            Fieldset(
                _('Информация о сотруднике'),
                Row(
                    Column('full_name_nominative', css_class='form-group col-md-12'),
                    css_class='form-row'
                ),
                Row(
                    Column('date_of_birth', css_class='form-group col-md-6'),
                    css_class='form-row'
                ),
                'place_of_residence',
                css_class='mb-3'
            ),
            Fieldset(
                _('Размеры для спецодежды'),
                Row(
                    Column('height', css_class='form-group col-md-4'),
                    Column('clothing_size', css_class='form-group col-md-4'),
                    Column('shoe_size', css_class='form-group col-md-4'),
                    css_class='form-row'
                ),
                css_class='mb-3'
            ),
            Div(
                Submit('submit', '💾 Принять', css_class='btn-primary'),
                Button('preview', '👁️ Предпросмотр', css_class='btn-info', type='submit'),
                HTML('<a href="{% url \"directory:employee_home\" %}" class="btn btn-secondary">Отмена</a>'),
                css_class='d-flex justify-content-between mt-3'
            )
        )

        # 🔒 Установка организации по умолчанию
        if self.user and hasattr(self.user, 'profile'):
            user_orgs = self.user.profile.organizations.all()
            if user_orgs.count() == 1:
                self.initial['organization'] = user_orgs.first().id

        # Даты по умолчанию
        if not self.initial.get('hire_date'):
            self.initial['hire_date'] = timezone.now().date()
        if not self.initial.get('start_date'):
            self.initial['start_date'] = timezone.now().date()

        # Значение contract_type по умолчанию
        if not self.initial.get('contract_type'):
            self.initial['contract_type'] = 'standard'

        # Стили для Select2
        for field_name in ['organization', 'subdivision', 'department', 'position']:
            if field_name in self.fields:
                self.fields[field_name].widget.attrs.update({
                    'class': 'select2 form-control',
                    'style': 'width: 100%; text-align: left;'
                })

    def clean(self):
        cleaned_data = super().clean()
        hire_date = cleaned_data.get('hire_date')
        start_date = cleaned_data.get('start_date')
        if hire_date and start_date and start_date < hire_date:
            self.add_error('start_date', _("Дата начала работы не может быть раньше даты приема"))
        return cleaned_data
