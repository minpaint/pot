# -*- coding: utf-8 -*-
"""
Формы для модуля production_training.
"""

from django import forms
from dal import autocomplete

from directory.models import Employee
from .models import (
    TrainingType,
    TrainingProfession,
    TrainingProgram,
    TrainingQualificationGrade,
)


class AssignTrainingForm(forms.Form):
    """
    Форма для массового назначения обучения сотрудникам.

    Позволяет выбрать:
    - Тип обучения
    - Профессию обучения
    - Программу обучения
    - Разряд квалификации
    - Дату начала обучения

    Остальные даты рассчитываются автоматически.
    """

    training_type = forms.ModelChoiceField(
        queryset=TrainingType.objects.filter(is_active=True),
        label="Тип обучения",
        widget=forms.Select(attrs={'class': 'form-control'}),
    )

    profession = forms.ModelChoiceField(
        queryset=TrainingProfession.objects.filter(is_active=True),
        label="Профессия обучения",
        widget=forms.Select(attrs={'class': 'form-control'}),
    )

    program = forms.ModelChoiceField(
        queryset=TrainingProgram.objects.filter(is_active=True),
        required=False,
        label="Программа обучения",
        widget=forms.Select(attrs={'class': 'form-control'}),
        help_text="Опционально. Если не выбрана, будет использован стандартный план часов."
    )

    qualification_grade = forms.ModelChoiceField(
        queryset=TrainingQualificationGrade.objects.filter(is_active=True),
        required=False,
        label="Разряд квалификации",
        widget=forms.Select(attrs={'class': 'form-control'}),
    )

    start_date = forms.DateField(
        label="Дата начала обучения",
        widget=forms.DateInput(
            attrs={
                'type': 'date',
                'class': 'form-control',
            }
        ),
        help_text="Все остальные даты рассчитаются автоматически с учетом графика работы"
    )

    # === Данные сотрудника (опционально) ===
    full_name_by = forms.CharField(
        required=False,
        label="ФИО (бел.)",
        widget=forms.TextInput(attrs={'class': 'form-control'}),
    )

    education_level = forms.CharField(
        required=False,
        label="Образование",
        widget=forms.TextInput(attrs={'class': 'form-control'}),
    )

    prior_qualification = forms.CharField(
        required=False,
        label="Имеющаяся квалификация",
        widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
    )

    def __init__(self, *args, organization=None, **kwargs):
        super().__init__(*args, **kwargs)

        # Если передана организация, можно фильтровать программы
        if organization:
            # Программы не привязаны к организации, но можно добавить логику
            pass


class RecalculateDatesForm(forms.Form):
    """
    Форма для пересчёта дат обучения.

    Позволяет:
    - Изменить дату начала
    - Принудительно пересчитать все даты
    """

    start_date = forms.DateField(
        label="Новая дата начала",
        widget=forms.DateInput(
            attrs={
                'type': 'date',
                'class': 'form-control',
            }
        ),
    )

    force_recalculate = forms.BooleanField(
        required=False,
        initial=True,
        label="Перезаписать существующие даты",
        help_text="Если включено, все даты будут пересчитаны, даже если они уже заполнены"
    )
