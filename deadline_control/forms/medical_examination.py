# deadline_control/forms/medical_examination.py
"""
🩺 Формы модуля медицинских осмотров

• Синхронизированы с актуальными моделями.
• Добавлена UniquePositionMedicalNormForm — выбор нормы по общему названию
  профессии (должности) без привязки к организации.
"""

import logging
from django import forms
from django.core.validators import FileExtensionValidator
from django.utils import timezone

from deadline_control.models import (
    MedicalExaminationType,
    HarmfulFactor,
    MedicalSettings,
    MedicalExaminationNorm,
    PositionMedicalFactor,
    EmployeeMedicalExamination,
)
from directory.models.position import Position
from directory.models.employee import Employee

# Настройка логирования
logger = logging.getLogger(__name__)

__all__ = [
    # базовые формы
    "MedicalExaminationTypeForm",
    "HarmfulFactorForm",
    "HarmfulFactorNormFormWithCounter",
    "MedicalExaminationNormForm",
    "PositionMedicalFactorForm",
    "EmployeeMedicalExaminationForm",
    "MedicalSettingsForm",
    # поисковые / сервисные
    "MedicalNormSearchForm",
    "EmployeeMedicalExaminationSearchForm",
    "MedicalNormImportForm",
    "MedicalNormExportForm",
    # 🆕 новая
    "UniquePositionMedicalNormForm",
    "HarmfulFactorNormForm",
    "HarmfulFactorNormFormSet",
    "PositionNormForm",
]


# ---------------------------------------------------------------------------
# 📋 ВИДЫ МЕДОСМОТРОВ
# ---------------------------------------------------------------------------

class MedicalExaminationTypeForm(forms.ModelForm):
    class Meta:
        model = MedicalExaminationType
        fields = ["name"]
        widgets = {"name": forms.TextInput(attrs={"class": "form-control"})}


# ---------------------------------------------------------------------------
# ☢️ ВРЕДНЫЕ ФАКТОРЫ
# ---------------------------------------------------------------------------

class HarmfulFactorForm(forms.ModelForm):
    class Meta:
        model = HarmfulFactor
        fields = ["short_name", "full_name", "periodicity"]
        widgets = {
            "short_name": forms.TextInput(attrs={"class": "form-control"}),
            "full_name": forms.Textarea(attrs={
                "class": "form-control vLargeTextField",
                "rows": 4,
                "style": "width: 100%; max-width: 800px;",
            }),
            "periodicity": forms.NumberInput(attrs={"class": "form-control"}),
        }


class HarmfulFactorNormFormWithCounter(forms.ModelForm):
    """
    Форма для админки вредных факторов с расширенным полем full_name и счётчиком символов
    """
    class Meta:
        model = HarmfulFactor
        fields = ["short_name", "full_name", "periodicity"]
        widgets = {
            "short_name": forms.TextInput(attrs={"class": "vTextField", "style": "width: 300px;"}),
            "full_name": forms.Textarea(attrs={
                "id": "id_full_name",
                "class": "vLargeTextField",
                "rows": 5,
                "style": "width: 100%; max-width: 900px; font-size: 14px;",
                "maxlength": "1000",
            }),
            "periodicity": forms.NumberInput(attrs={"class": "vIntegerField", "style": "width: 100px;"}),
        }


# ---------------------------------------------------------------------------
# 📑 ЭТАЛОННЫЕ НОРМЫ
# ---------------------------------------------------------------------------

class MedicalExaminationNormForm(forms.ModelForm):
    class Meta:
        model = MedicalExaminationNorm
        fields = ["position_name", "harmful_factor", "periodicity_override", "notes"]
        widgets = {
            "position_name": forms.TextInput(attrs={"class": "form-control"}),
            "harmful_factor": forms.Select(attrs={"class": "form-control"}),
            "periodicity_override": forms.NumberInput(attrs={"class": "form-control"}),
            "notes": forms.Textarea(attrs={"class": "form-control", "rows": 3}),
        }


# ---------------------------------------------------------------------------
# 🔄 ПЕРЕОПРЕДЕЛЕНИЯ ДЛЯ КОНКРЕТНЫХ ДОЛЖНОСТЕЙ
# ---------------------------------------------------------------------------

class PositionMedicalFactorForm(forms.ModelForm):
    class Meta:
        model = PositionMedicalFactor
        fields = ["position", "harmful_factor", "periodicity_override", "is_disabled", "notes"]
        widgets = {
            "position": forms.Select(attrs={"class": "form-control"}),
            "harmful_factor": forms.Select(attrs={"class": "form-control"}),
            "periodicity_override": forms.NumberInput(attrs={"class": "form-control"}),
            "is_disabled": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "notes": forms.Textarea(attrs={"class": "form-control", "rows": 3}),
        }


# ---------------------------------------------------------------------------
# 👨‍⚕️ ЖУРНАЛ МЕДОСМОТРОВ СОТРУДНИКОВ
# ---------------------------------------------------------------------------

class EmployeeMedicalExaminationForm(forms.ModelForm):
    class Meta:
        model = EmployeeMedicalExamination
        fields = [
            "employee", "harmful_factor",
            "date_completed", "next_date", "medical_certificate",
            "status", "notes",
        ]
        widgets = {
            "employee": forms.Select(attrs={"class": "form-control"}),
            "harmful_factor": forms.Select(attrs={"class": "form-control"}),
            "date_completed": forms.DateInput(attrs={"class": "form-control", "type": "date"}),
            "next_date": forms.DateInput(attrs={"class": "form-control", "type": "date"}),
            "medical_certificate": forms.ClearableFileInput(attrs={"class": "form-control"}),
            "status": forms.Select(attrs={"class": "form-control"}),
            "notes": forms.Textarea(attrs={"class": "form-control", "rows": 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["employee"].queryset = Employee.objects.active_for_operations()

    def clean(self):
        cd = super().clean()
        d1, d2 = cd.get("date_completed"), cd.get("next_date")
        if d1 and d2 and d2 <= d1:
            self.add_error("next_date", "Дата следующего медосмотра должна быть позже даты прохождения")
        if d1 and d1 > timezone.now().date():
            self.add_error("date_completed", "Дата прохождения не может быть в будущем")
        return cd


# ---------------------------------------------------------------------------
# ⚙️ НАСТРОЙКИ
# ---------------------------------------------------------------------------

class MedicalSettingsForm(forms.ModelForm):
    class Meta:
        model = MedicalSettings
        fields = ["days_before_issue", "days_before_email"]
        widgets = {
            "days_before_issue": forms.NumberInput(attrs={"class": "form-control"}),
            "days_before_email": forms.NumberInput(attrs={"class": "form-control"}),
        }


# ---------------------------------------------------------------------------
# 🔍 ПОИСКОВЫЕ / СЕРВИСНЫЕ ФОРМЫ
# ---------------------------------------------------------------------------

class MedicalNormSearchForm(forms.Form):
    position_name = forms.CharField(required=False, label="Наименование должности",
                                    widget=forms.TextInput(attrs={"class": "form-control"}))
    harmful_factor = forms.CharField(required=False, label="Вредный фактор",
                                     widget=forms.TextInput(attrs={"class": "form-control"}))


class EmployeeMedicalExaminationSearchForm(forms.Form):
    employee = forms.CharField(required=False, label="Сотрудник",
                               widget=forms.TextInput(attrs={"class": "form-control"}))
    status = forms.ChoiceField(required=False, label="Статус",
                               choices=[("", "---")] + list(EmployeeMedicalExamination.STATUS_CHOICES),
                               widget=forms.Select(attrs={"class": "form-control"}))
    date_from = forms.DateField(required=False, label="Дата с",
                                widget=forms.DateInput(attrs={"class": "form-control", "type": "date"}))
    date_to = forms.DateField(required=False, label="Дата по",
                              widget=forms.DateInput(attrs={"class": "form-control", "type": "date"}))


# импорт / экспорт

class MedicalNormImportForm(forms.Form):
    file = forms.FileField(label="Файл для импорта",
                           validators=[FileExtensionValidator(allowed_extensions=["xls", "xlsx", "csv"])],
                           widget=forms.FileInput(attrs={"class": "form-control"}))
    skip_first_row = forms.BooleanField(required=False, initial=True,
                                        label="Пропустить первую строку",
                                        widget=forms.CheckboxInput(attrs={"class": "form-check-input"}))
    update_existing = forms.BooleanField(required=False, initial=True,
                                         label="Обновлять существующие",
                                         widget=forms.CheckboxInput(attrs={"class": "form-check-input"}))


class MedicalNormExportForm(forms.Form):
    FORMAT_CHOICES = [("xlsx", "Excel (.xlsx)"), ("csv", "CSV (.csv)"), ("json", "JSON (.json)")]
    format = forms.ChoiceField(label="Формат", choices=FORMAT_CHOICES, initial="xlsx",
                               widget=forms.Select(attrs={"class": "form-control"}))
    include_headers = forms.BooleanField(required=False, initial=True,
                                         label="Включить заголовки",
                                         widget=forms.CheckboxInput(attrs={"class": "form-check-input"}))


# ---------------------------------------------------------------------------
# 🆕 ФОРМА ВЫБОРА ОБЩЕЙ ДОЛЖНОСТИ
# ---------------------------------------------------------------------------

class UniquePositionMedicalNormForm(forms.ModelForm):
    """
    Используется в админке MedicalExaminationNormAdmin: выбор «Профессия (должность)»
    из уникальных Position.position_name. При сохранении заполняет `position_name`.
    """
    unique_position_name = forms.ChoiceField(
        label="Профессия (должность)",
        required=True,
        help_text="Выберите общее название без привязки к организации",
    )

    class Meta:
        model = MedicalExaminationNorm
        fields = ("harmful_factor", "periodicity_override", "notes")
        widgets = {
            "harmful_factor": forms.Select(attrs={"class": "form-control"}),
            "periodicity_override": forms.NumberInput(attrs={"class": "form-control"}),
            "notes": forms.Textarea(attrs={"class": "form-control", "rows": 3}),
        }

    def __init__(self, *args, **kwargs):
        # Важное изменение: сохраняем position_id перед вызовом super().__init__
        position_id = kwargs.pop("position_id", None)

        # Логирование для отладки
        logger.debug(
            f"Инициализация UniquePositionMedicalNormForm с position_id={position_id}, args={args}, kwargs={kwargs}")

        super().__init__(*args, **kwargs)

        # Получаем все уникальные имена должностей
        names = Position.objects.values_list("position_name", flat=True).distinct().order_by("position_name")
        self.fields["unique_position_name"].choices = [("", "-- Выберите профессию/должность --")] + [(n, n) for n in names]

        # Устанавливаем initial значение для unique_position_name
        # 1. Если передан position_id, используем его (даже если self.instance.pk существует)
        if position_id:
            try:
                position_id = int(position_id)
                pos = Position.objects.get(pk=position_id)
                position_name = pos.position_name
                self.fields["unique_position_name"].initial = position_name
                logger.debug(f"Установлено начальное значение из position_id: {position_name}")
            except (ValueError, TypeError, Position.DoesNotExist) as e:
                logger.error(f"Ошибка при установке position_id={position_id}: {str(e)}")
        # 2. Если нет position_id, но есть instance.pk, используем значение из instance
        elif self.instance.pk:
            self.fields["unique_position_name"].initial = self.instance.position_name
            logger.debug(f"Установлено начальное значение из instance: {self.instance.position_name}")

        # Переупорядочиваем поля
        self.order_fields(['unique_position_name', 'harmful_factor', 'periodicity_override', 'notes'])

    # проверяем уникальность (position_name + factor)
    def clean(self):
        cleaned = super().clean()
        name = cleaned.get("unique_position_name")
        factor = cleaned.get("harmful_factor")
        if not name:
            self.add_error("unique_position_name", "Необходимо выбрать должность")
            return cleaned

        qs = MedicalExaminationNorm.objects.filter(position_name=name, harmful_factor=factor)
        if self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            self.add_error("unique_position_name", f"Норма для «{name}» и этого фактора уже существует")
        return cleaned

    def save(self, commit=True):
        # Сохраняем название должности в поле position_name
        self.instance.position_name = self.cleaned_data["unique_position_name"]
        return super().save(commit)


# ---------------------------------------------------------------------------
# 📋 FORMSET ДЛЯ МНОЖЕСТВЕННОГО ДОБАВЛЕНИЯ ВРЕДНЫХ ФАКТОРОВ
# ---------------------------------------------------------------------------

class HarmfulFactorNormForm(forms.Form):
    """
    Форма для одного вредного фактора в formset
    """
    harmful_factor = forms.ModelChoiceField(
        queryset=HarmfulFactor.objects.all(),
        required=True,
        label="Вредный фактор",
        widget=forms.Select(attrs={"class": "form-control"})
    )
    periodicity_override = forms.IntegerField(
        required=False,
        label="Периодичность (мес)",
        widget=forms.NumberInput(attrs={"class": "form-control", "placeholder": "Оставьте пустым для использования значения по умолчанию"})
    )
    notes = forms.CharField(
        required=False,
        label="Примечания",
        widget=forms.Textarea(attrs={"class": "form-control", "rows": 2})
    )


# Создаем formset на основе формы
from django.forms import formset_factory

HarmfulFactorNormFormSet = formset_factory(
    HarmfulFactorNormForm,
    extra=1,  # Показывать 1 пустую форму по умолчанию
    can_delete=True  # Позволить удалять формы
)


class PositionNormForm(forms.Form):
    """
    Форма для выбора профессии и добавления вредных факторов через formset
    """
    position_name = forms.ChoiceField(
        label="Профессия (должность)",
        required=True,
        help_text="Выберите общее название без привязки к организации",
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Получаем все уникальные имена должностей
        names = Position.objects.values_list("position_name", flat=True).distinct().order_by("position_name")
        self.fields["position_name"].choices = [("", "-- Выберите профессию/должность --")] + [(n, n) for n in names]
