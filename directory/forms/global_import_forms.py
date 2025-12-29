"""
Формы для единого импорта/экспорта справочников
"""
from django import forms
from directory.models import Organization


class GlobalImportForm(forms.Form):
    """Форма для импорта справочников"""

    organization = forms.ModelChoiceField(
        queryset=Organization.objects.all(),
        label="Организация",
        required=False,
        empty_label="--- Все организации ---",
        help_text="Выберите организацию для фильтрации импорта. Если не выбрано - импорт для всех организаций из файла.",
        widget=forms.Select(attrs={'class': 'vForeignKeyRawIdAdminField'})
    )

    import_file = forms.FileField(
        label="Excel-файл",
        required=True,
        help_text="Поддерживаются форматы: XLSX, XLS",
        widget=forms.ClearableFileInput(attrs={'accept': '.xlsx,.xls'})
    )

    def clean_import_file(self):
        """Валидация файла"""
        file = self.cleaned_data.get('import_file')
        if file:
            # Проверяем расширение
            file_name = file.name.lower()
            if not (file_name.endswith('.xlsx') or file_name.endswith('.xls')):
                raise forms.ValidationError('Поддерживаются только файлы XLSX и XLS')

            # Проверяем размер (макс 10MB)
            if file.size > 10 * 1024 * 1024:
                raise forms.ValidationError('Размер файла не должен превышать 10 МБ')

        return file


class GlobalExportForm(forms.Form):
    """Форма для экспорта справочников"""

    organization = forms.ModelChoiceField(
        queryset=Organization.objects.all(),
        label="Организация",
        required=False,
        empty_label="--- Все организации ---",
        help_text="Выберите организацию для экспорта только её данных. Если не выбрано - экспорт всех данных.",
        widget=forms.Select(attrs={'class': 'vForeignKeyRawIdAdminField'})
    )
