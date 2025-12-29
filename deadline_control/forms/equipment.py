# deadline_control/forms/equipment.py
from django import forms
from django.utils import timezone
from crispy_forms.helper import FormHelper
from crispy_forms.layout import Submit, Layout, Fieldset, Div, HTML
from dal import autocomplete
from deadline_control.models import Equipment, EquipmentType
from directory.models import Organization
from directory.forms.mixins import OrganizationRestrictionFormMixin
import datetime


class EquipmentForm(OrganizationRestrictionFormMixin, forms.ModelForm):
    class Meta:
        model = Equipment
        fields = [
            'equipment_name', 'inventory_number',
            'load_capacity_kg',
            'equipment_type',
            'organization', 'subdivision', 'department',
            'maintenance_period_months',
            'last_maintenance_date', 'next_maintenance_date',
            'maintenance_status'
        ]
        widgets = {
            'organization': autocomplete.ModelSelect2(
                url='directory:organization-autocomplete',
                attrs={
                    'data-placeholder': '🏢 Выберите организацию...',
                    'class': 'select2-basic'
                }
            ),
            'subdivision': autocomplete.ModelSelect2(
                url='directory:subdivision-autocomplete',
                forward=['organization'],
                attrs={
                    'data-placeholder': '🏭 Выберите подразделение...',
                    'class': 'select2-basic'
                }
            ),
            'department': autocomplete.ModelSelect2(
                url='directory:department-autocomplete',
                forward=['subdivision'],
                attrs={
                    'data-placeholder': '📂 Выберите отдел...',
                    'class': 'select2-basic'
                }
            ),
            'last_maintenance_date': forms.DateInput(
                attrs={'type': 'date'}, format='%Y-%m-%d'
            ),
            'next_maintenance_date': forms.DateInput(
                attrs={'type': 'date'}, format='%Y-%m-%d'
            ),
            'load_capacity_kg': forms.NumberInput(
                attrs={'min': 0, 'step': 1, 'placeholder': '2500'}
            ),
        }

    def __init__(self, *args, **kwargs):
        # ВАЖНО: не извлекаем 'user' здесь, это делает миксин OrganizationRestrictionFormMixin
        super().__init__(*args, **kwargs)

        # Делаем поле next_maintenance_date только для чтения
        self.fields['next_maintenance_date'].required = False
        self.fields['next_maintenance_date'].widget.attrs['readonly'] = True
        self.fields['next_maintenance_date'].help_text = '📅 Рассчитывается автоматически на основе даты последнего ТО и периодичности'

        self.fields['load_capacity_kg'].required = False

        # Делаем поля subdivision и department необязательными
        self.fields['subdivision'].required = False
        self.fields['department'].required = False

        self.helper = FormHelper()
        self.helper.form_method = 'post'
        self.helper.layout = Layout(
            Fieldset(
                'Основная информация',
                'equipment_name', 'inventory_number', 'load_capacity_kg', 'equipment_type',
                'organization', 'subdivision', 'department',
            ),
            Fieldset(
                'Техническое обслуживание',
                'maintenance_period_months',
                'last_maintenance_date',
                'next_maintenance_date',
                'maintenance_status',
            ),
            HTML('<hr>'),
            Div(
                Submit('submit', '💾 Сохранить', css_class='btn-primary'),
                HTML('<a href="{% url "deadline_control:equipment:list" %}" class="btn btn-secondary">Отмена</a>'),
                css_class='d-flex justify-content-between mt-3'
            )
        )

        # Настройка каскадных queryset для autocomplete
        if self.user and hasattr(self.user, 'profile'):
            from directory.models import StructuralSubdivision, Department

            user_orgs = self.user.profile.organizations.all()

            # Если у пользователя только одна организация - предзаполняем
            if user_orgs.count() == 1 and not self.instance.pk:
                # Только для новых объектов (не при редактировании)
                org = user_orgs.first()
                self.initial['organization'] = org.id
                # Разрешаем выбор подразделений из этой организации
                self.fields['subdivision'].queryset = StructuralSubdivision.objects.filter(organization=org)
            else:
                # Если несколько организаций или редактирование - начинаем с пустого queryset
                if not self.instance.pk:
                    self.fields['subdivision'].queryset = StructuralSubdivision.objects.none()

            # Для department всегда начинаем с пустого queryset, пока не выбрано subdivision
            if not self.instance.pk:
                self.fields['department'].queryset = Department.objects.none()
            elif self.instance.subdivision:
                # При редактировании - показываем отделы текущего подразделения
                self.fields['department'].queryset = Department.objects.filter(
                    subdivision=self.instance.subdivision
                )


        equipment_type = getattr(self.instance, 'equipment_type', None)
        if equipment_type and equipment_type.name == 'Грузовая тележка':
            if not self.instance.load_capacity_kg:
                self.initial.setdefault('load_capacity_kg', 2500)

    def clean(self):
        cleaned_data = super().clean()
        equipment_type = cleaned_data.get('equipment_type')
        load_capacity = cleaned_data.get('load_capacity_kg')

        if equipment_type and equipment_type.name == 'Грузовая тележка':
            cleaned_data['load_capacity_kg'] = load_capacity or 2500
        else:
            cleaned_data['load_capacity_kg'] = None

        return cleaned_data


class EquipmentJournalGenerationForm(forms.Form):
    """
    📄 Форма для генерации журнала периодического осмотра оборудования
    Период журнала автоматически устанавливается на текущий год
    """
    organization = forms.ModelChoiceField(
        queryset=Organization.objects.all(),
        label='Организация',
        widget=autocomplete.ModelSelect2(
            url='directory:organization-autocomplete',
            attrs={
                'data-placeholder': '🏢 Выберите организацию...',
                'class': 'select2-basic'
            }
        ),
        help_text='Выберите организацию для генерации журнала'
    )

    equipment_type = forms.ModelChoiceField(
        queryset=EquipmentType.objects.filter(is_active=True),
        label='Тип оборудования',
        widget=forms.Select(attrs={'class': 'form-control'}),
        help_text='Выберите тип оборудования (например, "Грузовая тележка"). Журнал будет сгенерирован на текущий год.'
    )

    def __init__(self, *args, **kwargs):
        user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)

        # Ограничиваем выбор организаций для пользователя
        if user and hasattr(user, 'profile'):
            user_orgs = user.profile.organizations.all()
            self.fields['organization'].queryset = user_orgs

            # Если у пользователя только одна организация - предзаполняем
            if user_orgs.count() == 1:
                self.initial['organization'] = user_orgs.first()

        # Настройка Crispy Forms
        self.helper = FormHelper()
        self.helper.form_method = 'post'
        self.helper.layout = Layout(
            Fieldset(
                'Параметры журнала',
                'organization',
                'equipment_type',
            ),
            HTML('<hr>'),
            Div(
                Submit('submit', '📄 Сгенерировать журнал', css_class='btn-primary'),
                HTML('<a href="{% url \'deadline_control:equipment:list\' %}" class="btn btn-secondary">Отмена</a>'),
                css_class='d-flex justify-content-between mt-3'
            )
        )
