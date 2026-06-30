# 📁 directory/forms/siz_issued.py
from django import forms
from django.utils import timezone
from django.forms import formset_factory
from crispy_forms.helper import FormHelper
from crispy_forms.layout import Layout, Div, Field, HTML, Submit, Button
from dal import autocomplete
from directory.models import SIZIssued, SIZ, Employee
from directory.models.siz import SIZNorm


class SIZIssueForm(forms.ModelForm):
    """
    📝 Форма для выдачи СИЗ сотруднику
    """

    class Meta:
        model = SIZIssued
        fields = [
            'employee', 'siz', 'issue_date', 'quantity',
            'cost', 'condition', 'notes', 'received_signature'
        ]
        widgets = {
            'employee': autocomplete.ModelSelect2(
                url='directory:employee-for-siz-autocomplete',
                attrs={'data-placeholder': '🔍 Начните вводить ФИО сотрудника...'},
            ),
            'issue_date': forms.DateInput(attrs={'type': 'date'}, format='%Y-%m-%d'),
            'notes': forms.Textarea(attrs={'rows': 3}),
        }

    def __init__(self, *args, **kwargs):
        # 🔑 Извлекаем пользователя, если он был передан
        self.user = kwargs.pop('user', None)

        # 🧩 Извлекаем предварительно выбранного сотрудника, если он есть
        self.initial_employee_id = kwargs.pop('employee_id', None)

        super().__init__(*args, **kwargs)

        # 🎨 Настройка формы с помощью crispy-forms
        self.helper = FormHelper()
        self.helper.form_method = 'post'
        self.helper.form_tag = True

        # 🔒 Ограничиваем выбор по организациям пользователя
        if self.user and hasattr(self.user, 'profile'):
            allowed_orgs = self.user.profile.organizations.all()
            self.fields['employee'].queryset = Employee.objects.selectable().filter(
                organization__in=allowed_orgs
            ).order_by('full_name_nominative')

        # 📌 Если уже выбран сотрудник, предзаполняем форму
        if self.initial_employee_id:
            try:
                employee = Employee.objects.selectable().get(id=self.initial_employee_id)
                self.fields['employee'].initial = employee

                # 🔍 Получаем список СИЗ, положенных по нормам для данного сотрудника
                if hasattr(employee, 'position') and employee.position:
                    norms = SIZNorm.objects.filter(
                        position=employee.position
                    ).select_related('siz')

                    if norms.exists():
                        # Ограничиваем выбор СИЗ теми, что положены по нормам
                        siz_ids = norms.values_list('siz_id', flat=True)
                        self.fields['siz'].queryset = SIZ.objects.filter(id__in=siz_ids)

                        # ✅ Создаем подсказки для поля condition на основе условий из норм
                        conditions = norms.exclude(condition='').values_list('condition', flat=True).distinct()
                        if conditions:
                            self.fields['condition'].widget.attrs['list'] = 'condition_datalist'
                            condition_options = ''.join([f'<option value="{c}">' for c in conditions])
                            self.fields[
                                'condition'].help_text += f'<datalist id="condition_datalist">{condition_options}</datalist>'
            except Employee.DoesNotExist:
                pass

        # 📅 Предустанавливаем текущую дату для поля issue_date
        self.fields['issue_date'].initial = timezone.now().date()


class SIZIssueMassForm(forms.Form):
    """
    📋 Форма для массовой выдачи СИЗ сотрудникам
    """
    employee = forms.ModelChoiceField(
        queryset=Employee.objects.selectable(),
        label="Сотрудник",
        required=True
    )

    siz_norm = forms.ModelChoiceField(
        queryset=SIZNorm.objects.none(),  # Будет заполнено динамически
        label="СИЗ (из норм)",
        required=True,
        empty_label="Выберите СИЗ из норм"
    )

    issue_date = forms.DateField(
        label="Дата выдачи",
        widget=forms.DateInput(attrs={'type': 'date'}, format='%Y-%m-%d'),
        initial=timezone.now().date()
    )

    quantity = forms.IntegerField(
        label="Количество",
        min_value=1,
        initial=1
    )

    cost = forms.DecimalField(
        label="Стоимость",
        required=False,
        min_value=0,
        decimal_places=2
    )

    notes = forms.CharField(
        label="Примечания",
        required=False,
        widget=forms.Textarea(attrs={'rows': 3})
    )

    received_signature = forms.BooleanField(
        label="Подпись о получении",
        required=False,
        initial=True
    )

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)

        # 🎨 Настройка формы с помощью crispy-forms
        self.helper = FormHelper()
        self.helper.form_method = 'post'
        self.helper.form_id = 'siz-issue-mass-form'

        # 🔒 Ограничиваем выбор по организациям пользователя
        if self.user and hasattr(self.user, 'profile'):
            allowed_orgs = self.user.profile.organizations.all()
            self.fields['employee'].queryset = Employee.objects.selectable().filter(
                organization__in=allowed_orgs
            ).order_by('full_name_nominative')

        # 📱 Добавляем AJAX-функциональность для зависимых полей
        self.fields['employee'].widget.attrs.update({
            'class': 'select2 form-control',
            'data-placeholder': 'Выберите сотрудника',
            'onchange': 'updateSIZNorms(this.value)'
        })

        self.fields['siz_norm'].widget.attrs.update({
            'class': 'select2 form-control',
            'data-placeholder': 'Сначала выберите сотрудника'
        })


class SIZIssueReturnForm(forms.ModelForm):
    """
    🔄 Форма для возврата СИЗ
    """

    confirm_return = forms.BooleanField(
        label="Подтверждаю возврат СИЗ",
        required=True,
        initial=True,
        help_text="Отметьте для подтверждения возврата СИЗ"
    )

    class Meta:
        model = SIZIssued
        fields = ['return_date', 'wear_percentage', 'notes']
        widgets = {
            'return_date': forms.DateInput(attrs={'type': 'date'}, format='%Y-%m-%d'),
            'wear_percentage': forms.NumberInput(attrs={'min': '0', 'max': '100'}),
            'notes': forms.Textarea(attrs={'rows': 3, 'placeholder': 'Укажите причину возврата или состояние СИЗ'})
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # 🎨 Настройка формы с помощью crispy-forms
        self.helper = FormHelper()
        self.helper.form_method = 'post'
        self.helper.form_tag = True

        # 📅 Предустанавливаем текущую дату для поля return_date
        self.fields['return_date'].initial = timezone.now().date()

        # 🧩 Создаем информативный макет формы
        self.helper.layout = Layout(
            Field('return_date'),
            Field('wear_percentage'),
            Field('notes'),
            Div(
                Field('confirm_return'),
                css_class='alert alert-warning p-3 mt-3'
            ),
            Div(
                Submit('submit', '✅ Подтвердить возврат', css_class='btn-success'),
                Button('cancel', '❌ Отмена', css_class='btn-secondary ml-2',
                       onclick="window.history.back();"),
                css_class='text-center mt-4'
            )
        )

    def clean(self):
        """
        🧪 Валидация данных формы
        """
        cleaned_data = super().clean()

        # ✅ Проверяем, что пользователь подтвердил возврат
        if not cleaned_data.get('confirm_return'):
            self.add_error('confirm_return', 'Необходимо подтвердить возврат СИЗ')

        # 📅 Проверяем, что дата возврата не раньше даты выдачи
        return_date = cleaned_data.get('return_date')
        if return_date and self.instance and self.instance.issue_date and return_date < self.instance.issue_date:
            self.add_error('return_date', 'Дата возврата не может быть раньше даты выдачи')

        return cleaned_data

    def save(self, commit=True):
        """
        💾 Переопределяем метод сохранения для установки флага is_returned
        """
        instance = super().save(commit=False)
        instance.is_returned = True

        if commit:
            instance.save()

        return instance
