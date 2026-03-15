# directory/forms/bulk_employee.py
from django import forms
from directory.models import Organization, StructuralSubdivision, Department, Position, EmployeeHiring


class BulkEmployeeAddForm(forms.Form):
    organization = forms.ModelChoiceField(
        queryset=Organization.objects.all(),
        label='Организация',
        empty_label='--- Выберите организацию ---',
        widget=forms.Select(attrs={'id': 'id_organization'}),
    )
    subdivision = forms.ModelChoiceField(
        queryset=StructuralSubdivision.objects.none(),
        label='Структурное подразделение',
        required=False,
        empty_label='--- Без подразделения ---',
        widget=forms.Select(attrs={'id': 'id_subdivision'}),
    )
    department = forms.ModelChoiceField(
        queryset=Department.objects.none(),
        label='Отдел',
        required=False,
        empty_label='--- Без отдела ---',
        widget=forms.Select(attrs={'id': 'id_department'}),
    )
    position = forms.ModelChoiceField(
        queryset=Position.objects.none(),
        label='Должность',
        empty_label='--- Выберите должность ---',
        widget=forms.Select(attrs={'id': 'id_position'}),
    )
    hire_date = forms.DateField(
        label='Дата приёма',
        widget=forms.DateInput(attrs={'type': 'date', 'id': 'id_hire_date'}),
    )
    start_date = forms.DateField(
        label='Дата начала работы',
        required=False,
        help_text='Если не указана — совпадает с датой приёма',
        widget=forms.DateInput(attrs={'type': 'date', 'id': 'id_start_date'}),
    )
    hiring_type = forms.ChoiceField(
        label='Вид приёма',
        choices=EmployeeHiring.HIRING_TYPE_CHOICES,
        initial='new',
        widget=forms.Select(attrs={'id': 'id_hiring_type'}),
    )
    names_text = forms.CharField(
        label='Список сотрудников (ФИО каждого — с новой строки)',
        help_text='Введите полное ФИО каждого сотрудника с новой строки',
        widget=forms.Textarea(attrs={
            'id': 'id_names_text',
            'rows': 15,
            'placeholder': 'Иванов Иван Иванович\nПетров Пётр Петрович\nСидорова Мария Ивановна',
        }),
    )

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)

        # Ограничиваем организации по правам пользователя
        if user and not user.is_superuser and hasattr(user, 'profile'):
            self.fields['organization'].queryset = user.profile.organizations.all()

        # При наличии данных заполняем каскадные queryset'ы
        data = args[0] if args else kwargs.get('data')
        if data:
            org_id = data.get('organization')
            sub_id = data.get('subdivision')
            if org_id:
                self.fields['subdivision'].queryset = StructuralSubdivision.objects.filter(
                    organization_id=org_id
                ).order_by('name')
                self.fields['position'].queryset = Position.objects.filter(
                    organization_id=org_id
                ).order_by('position_name')
            if sub_id:
                self.fields['department'].queryset = Department.objects.filter(
                    subdivision_id=sub_id
                ).order_by('name')

    def clean(self):
        cleaned_data = super().clean()

        # start_date по умолчанию = hire_date
        if not cleaned_data.get('start_date') and cleaned_data.get('hire_date'):
            cleaned_data['start_date'] = cleaned_data['hire_date']

        # Проверяем что names_text не пустой после парсинга
        names_text = cleaned_data.get('names_text', '')
        names = [line.strip() for line in names_text.splitlines() if line.strip()]
        if not names:
            self.add_error('names_text', 'Введите хотя бы одно ФИО.')

        return cleaned_data
