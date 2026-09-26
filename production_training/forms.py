# -*- coding: utf-8 -*-
"""
Формы для модуля production_training.
"""

from django import forms

from directory.models import Employee
from .models import ProductionTraining


class AssignTrainingForm(forms.Form):
    """
    Форма для назначения сотрудников на уже существующий курс обучения.

    Курс (ProductionTraining) создаётся заранее в разделе «Обучение на
    производстве» — там же указываются инструктор, ответственный,
    консультант и комиссия. Здесь эти данные не запрашиваются: они
    автоматически подтягиваются из выбранного курса при генерации
    документов.
    """

    training = forms.ModelChoiceField(
        queryset=ProductionTraining.objects.select_related(
            'organization', 'training_type', 'profession', 'qualification_grade'
        ).order_by('-created_at'),
        label="Курс обучения",
        widget=forms.Select(attrs={'class': 'form-control'}),
        help_text="Инструктор, ответственный, консультант и комиссия берутся из карточки курса. "
                   "Если подходящего курса нет — создайте его в разделе «Обучение на производстве».",
    )

    start_date = forms.DateField(
        label="Дата начала обучения",
        widget=forms.DateInput(
            attrs={
                'type': 'date',
                'class': 'form-control',
            },
            format='%Y-%m-%d',
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

    def __init__(self, *args, organization=None, employee=None, **kwargs):
        super().__init__(*args, **kwargs)

        # Сужаем список курсов до организации сотрудника/сотрудников —
        # иначе легко перепутать курс из чужой организации.
        if organization:
            self.fields['training'].queryset = self.fields['training'].queryset.filter(
                organization=organization
            )

        # График работы редактируем только когда форма открыта для одного
        # конкретного сотрудника (например, при приёме на работу) — при
        # массовом назначении на разных сотрудников поле неоднозначно.
        if employee is not None:
            self.fields['work_schedule'] = forms.ChoiceField(
                choices=Employee.WORK_SCHEDULE_CHOICES,
                initial=employee.work_schedule,
                label="График работы",
                widget=forms.Select(attrs={'class': 'form-control'}),
                help_text="Используется для расчёта дат обучения (рабочие/нерабочие дни). "
                           "При изменении будет сохранён в карточке сотрудника.",
            )


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
            },
            format='%Y-%m-%d',
        ),
    )

    force_recalculate = forms.BooleanField(
        required=False,
        initial=True,
        label="Перезаписать существующие даты",
        help_text="Если включено, все даты будут пересчитаны, даже если они уже заполнены"
    )
