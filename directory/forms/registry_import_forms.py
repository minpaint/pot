"""
📋 Формы для импорта реестра сотрудников
"""
from django import forms
from directory.models import Organization


class RegistryImportForm(forms.Form):
    """
    Форма для загрузки файла реестра сотрудников
    """
    import_file = forms.FileField(
        label='Excel файл с реестром сотрудников',
        help_text='Загрузите файл в формате XLSX с реестром сотрудников',
        required=True,
        widget=forms.FileInput(attrs={
            'accept': '.xlsx,.xls',
            'class': 'form-control'
        })
    )

    organization = forms.ModelChoiceField(
        queryset=Organization.objects.all(),
        label='Организация',
        help_text='Выберите организацию для импорта. Если организация указана в файле - это поле опционально.',
        required=False,
        widget=forms.Select(attrs={'class': 'form-control'})
    )

    update_existing = forms.BooleanField(
        label='Обновлять существующих сотрудников',
        help_text='Если сотрудник с таким ФИО уже существует - обновить его данные',
        required=False,
        initial=False
    )

    def clean_import_file(self):
        """Валидация файла"""
        file = self.cleaned_data.get('import_file')

        if not file:
            raise forms.ValidationError('Файл не загружен')

        # Проверяем расширение
        if not file.name.endswith(('.xlsx', '.xls')):
            raise forms.ValidationError('Поддерживаются только файлы XLSX и XLS')

        # Проверяем размер (макс 10 MB)
        if file.size > 10 * 1024 * 1024:
            raise forms.ValidationError('Файл слишком большой (максимум 10 MB)')

        return file
