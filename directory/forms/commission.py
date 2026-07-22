from django import forms
from django.core.exceptions import ValidationError
from crispy_forms.helper import FormHelper
from crispy_forms.layout import Layout, Fieldset, ButtonHolder, Submit, Div, HTML, Field, Row, Column
from dal import autocomplete, forward as dal_forward
from directory.models import Commission, CommissionMember, Employee, Organization, StructuralSubdivision as Subdivision, \
    Department
from .mixins import OrganizationRestrictionFormMixin


class CommissionForm(OrganizationRestrictionFormMixin, forms.ModelForm):
    """Форма для создания и редактирования комиссии с иерархическим выбором структуры"""

    class Meta:
        model = Commission
        fields = ['name', 'commission_type', 'organization', 'subdivision', 'department', 'is_active']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Название комиссии'}),
            'commission_type': forms.Select(attrs={'class': 'form-control'}),
            'organization': autocomplete.ModelSelect2(
                url='directory:organization-autocomplete',
                attrs={'data-placeholder': '🏢 Выберите организацию...', 'class': 'form-control'}
            ),
            'subdivision': autocomplete.ModelSelect2(
                url='directory:subdivision-autocomplete',
                forward=['organization'],
                attrs={'data-placeholder': '🏭 Выберите подразделение...', 'class': 'form-control'}
            ),
            'department': autocomplete.ModelSelect2(
                url='directory:department-autocomplete',
                forward=['subdivision', 'organization'],  # Важно передавать оба параметра
                attrs={'data-placeholder': '📂 Выберите отдел...', 'class': 'form-control'}
            ),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }

    def __init__(self, *args, **kwargs):
        # user/initial_org_id обрабатывает OrganizationRestrictionFormMixin.__init__ —
        # не извлекаем их здесь заранее, иначе миксин перезатрёт self.user значением None
        super().__init__(*args, **kwargs)

        # Настройка внешнего вида формы
        self.helper = FormHelper()
        self.helper.form_tag = False
        self.helper.layout = Layout(
            Fieldset(
                'Основная информация',
                'name',
                'commission_type',
                'is_active',
            ),
            Fieldset(
                'Привязка к структуре организации',
                HTML(
                    '<p class="text-info">Выберите только один уровень привязки: организация, подразделение или отдел</p>'),
                'organization',
                'subdivision',
                'department',
            ),
            ButtonHolder(
                Submit('submit', 'Сохранить', css_class='btn btn-primary'),
                HTML(
                    '<a href="{% url "directory:commissions:commission_list" %}" class="btn btn-secondary">Отмена</a>'),
            )
        )

        # Делаем поля необязательными для валидации на уровне формы
        self.fields['organization'].required = False
        self.fields['subdivision'].required = False
        self.fields['department'].required = False

        # Инициализация для организаций в зависимости от прав пользователя
        if self.user and hasattr(self.user, 'profile'):
            user_orgs = self.user.profile.organizations.all()
            self.fields['organization'].queryset = user_orgs
        else:
            self.fields['organization'].queryset = Organization.objects.all()

        # КЛЮЧЕВОЙ МОМЕНТ: Обработка данных формы из POST запроса или initial
        # Для выбора организации
        org_id = None
        if self.data and 'organization' in self.data:
            org_id = self.data.get('organization') or None
        elif self.instance and self.instance.pk and self.instance.organization:
            org_id = self.instance.organization.pk
        elif self.initial.get('organization'):
            org_id = self.initial.get('organization')

        # Для выбора подразделения
        subdiv_id = None
        if self.data and 'subdivision' in self.data:
            subdiv_id = self.data.get('subdivision') or None
        elif self.instance and self.instance.pk and self.instance.subdivision:
            subdiv_id = self.instance.subdivision.pk
        elif self.initial.get('subdivision'):
            subdiv_id = self.initial.get('subdivision')

        # dept_id нужен для случая, когда отдел выбран без подразделения
        dept_id = None
        if self.data and 'department' in self.data:
            dept_id = self.data.get('department') or None
        elif self.instance and self.instance.pk and self.instance.department:
            dept_id = self.instance.department.pk
        elif self.initial.get('department'):
            dept_id = self.initial.get('department')

        # Настраиваем querysets для зависимых полей
        if org_id:
            self.fields['subdivision'].queryset = Subdivision.objects.filter(organization_id=org_id)
        elif subdiv_id:
            # Организация не выбрана, но подразделение есть (комиссия на уровне подразделения)
            self.fields['subdivision'].queryset = Subdivision.objects.filter(pk=subdiv_id)
        else:
            self.fields['subdivision'].queryset = Subdivision.objects.none()

        if subdiv_id:
            self.fields['department'].queryset = Department.objects.filter(subdivision_id=subdiv_id)
        elif dept_id:
            # Подразделение не выбрано, но отдел есть (комиссия на уровне отдела)
            self.fields['department'].queryset = Department.objects.filter(pk=dept_id)
        else:
            self.fields['department'].queryset = Department.objects.none()

    def clean(self):
        """Дополнительная валидация формы"""
        cleaned_data = super().clean()

        # Проверка, что выбран только один уровень привязки
        organization = cleaned_data.get('organization')
        subdivision = cleaned_data.get('subdivision')
        department = cleaned_data.get('department')

        bindings = sum(1 for field in [organization, subdivision, department] if field is not None)

        if bindings == 0:
            raise ValidationError('Необходимо выбрать организацию, структурное подразделение или отдел.')
        elif bindings > 1:
            raise ValidationError(
                'Комиссия должна быть привязана только к одному уровню: организация, '
                'структурное подразделение или отдел.'
            )

        # Проверка согласованности иерархии: подразделение должно принадлежать организации
        if subdivision and organization and subdivision.organization != organization:
            self.add_error('subdivision',
                           'Выбранное подразделение не принадлежит выбранной организации')

        # Проверка согласованности иерархии: отдел должен принадлежать подразделению
        if department and subdivision and department.subdivision != subdivision:
            self.add_error('department',
                           'Выбранный отдел не принадлежит выбранному подразделению')

        return cleaned_data


class CommissionMemberForm(forms.ModelForm):
    """Форма для добавления и редактирования участника комиссии"""

    class Meta:
        model = CommissionMember
        fields = ['commission', 'employee', 'role', 'is_active']
        widgets = {
            'commission': forms.HiddenInput(),
            'employee': autocomplete.ModelSelect2(
                url='directory:employee-for-commission-autocomplete',
                forward=['commission'],
                attrs={'data-placeholder': '👤 Выберите сотрудника...', 'class': 'form-control select2'}
            ),
            'role': forms.Select(attrs={'class': 'form-control'}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }

    def __init__(self, *args, **kwargs):
        commission = kwargs.pop('commission', None)
        super().__init__(*args, **kwargs)

        # Настройка внешнего вида формы
        self.helper = FormHelper()
        self.helper.form_tag = False
        self.helper.layout = Layout(
            'commission',
            Row(
                Column('employee', css_class='form-group col-md-6'),
                Column('role', css_class='form-group col-md-6'),
                css_class='form-row'
            ),
            'is_active',
            ButtonHolder(
                Submit('submit', 'Сохранить', css_class='btn btn-primary'),
                HTML(
                    '<a href="{% url "directory:commissions:commission_detail" commission.id %}" class="btn btn-secondary">Отмена</a>'),
            )
        )

        # Устанавливаем комиссию в скрытое поле
        if commission:
            self.fields['commission'].initial = commission.id

            # ИСПРАВЛЕНИЕ: Настраиваем виджет только если комиссия сохранена
            if commission.pk:
                # Настраиваем виджет для выбора сотрудников с учетом иерархии комиссии
                self.fields['employee'].widget.forward = [
                    dal_forward.Const(commission.id, 'commission'),
                    dal_forward.Const(commission.organization_id or '', 'organization'),
                    dal_forward.Const(commission.subdivision_id or '', 'subdivision'),
                    dal_forward.Const(commission.department_id or '', 'department'),
                ]

        # Создаем список ролей с информацией о том, какие уже заняты
        self.role_choices = []

        # Получаем занятые роли для визуализации в форме
        existing_roles = []
        if commission and commission.pk:  # ИСПРАВЛЕНИЕ: проверяем, что комиссия сохранена
            existing_roles = list(commission.members.filter(
                is_active=True
            ).exclude(
                id=self.instance.id if self.instance and self.instance.id else None
            ).values_list('role', flat=True))

        # Создаем список ролей с информацией о том, какие уже заняты
        for value, label in self.fields['role'].choices:
            disabled = False
            tooltip = ""
            if value in ['chairman', 'secretary'] and value in existing_roles:
                disabled = True
                tooltip = f"Роль {label} уже занята"

            self.role_choices.append((value, label, disabled, tooltip))

    def clean(self):
        """Дополнительная валидация формы"""
        cleaned_data = super().clean()

        commission = cleaned_data.get('commission')
        role = cleaned_data.get('role')
        is_active = cleaned_data.get('is_active')

        # ИСПРАВЛЕНИЕ: Проверяем, что комиссия сохранена
        if not commission or not commission.pk:
            return cleaned_data

        # Проверка на дубликаты ролей председателя и секретаря
        if is_active and role in ['chairman', 'secretary']:
            existing = CommissionMember.objects.filter(
                commission=commission,
                role=role,
                is_active=True
            )

            # Если это редактирование, исключаем текущий экземпляр из проверки
            if self.instance and self.instance.pk:
                existing = existing.exclude(id=self.instance.id)

            if existing.exists():
                role_display = dict(CommissionMember.ROLE_CHOICES)[role]
                raise ValidationError(
                    f'В комиссии уже есть активный {role_display.lower()}. '
                    'Пожалуйста, деактивируйте его перед назначением нового.'
                )

        return cleaned_data