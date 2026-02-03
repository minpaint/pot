# -*- coding: utf-8 -*-
"""
Упрощённая админка для production_training (5 моделей).
"""

from django import forms
from django.contrib import admin
from django.utils.html import format_html
from dal import autocomplete
from directory.forms.mixins import OrganizationRestrictionFormMixin
from directory.models import StructuralSubdivision, Department, Employee

from .models import (
    TrainingType,
    TrainingQualificationGrade,
    TrainingProfession,
    TrainingProgram,
    ProductionTraining,
)


@admin.register(TrainingType)
class TrainingTypeAdmin(admin.ModelAdmin):
    list_display = ('name_ru', 'code', 'is_active', 'order')
    list_filter = ('is_active',)
    search_fields = ('name_ru', 'code')
    ordering = ('order', 'name_ru')


@admin.register(TrainingQualificationGrade)
class TrainingQualificationGradeAdmin(admin.ModelAdmin):
    list_display = ('grade_number', 'label_ru', 'label_by', 'is_active', 'order')
    list_filter = ('is_active',)
    search_fields = ('label_ru', 'label_by')
    ordering = ('order', 'grade_number')


@admin.register(TrainingProfession)
class TrainingProfessionAdmin(admin.ModelAdmin):
    list_display = ('name_ru_nominative', 'name_ru_genitive', 'is_active', 'order')
    list_filter = ('is_active',)
    search_fields = ('name_ru_nominative', 'name_ru_genitive', 'name_by_nominative')
    ordering = ('order', 'name_ru_nominative')


@admin.register(TrainingProgram)
class TrainingProgramAdmin(admin.ModelAdmin):
    list_display = (
        'name',
        'training_type',
        'profession',
        'qualification_grade',
        'get_total_hours',
        'is_active'
    )
    list_filter = ('training_type', 'profession', 'is_active')
    search_fields = ('name',)
    ordering = ('training_type', 'profession', 'name')

    fieldsets = (
        ('Основная информация', {
            'fields': ('name', 'training_type', 'profession', 'qualification_grade')
        }),
        ('Программа', {
            'fields': ('content', 'duration_days', 'description')
        }),
        ('Настройки', {
            'fields': ('is_active',)
        }),
    )

    def get_total_hours(self, obj):
        """Показать общее количество часов."""
        hours = obj.get_total_hours()
        if hours:
            return f"{hours} ч"
        return '-'
    get_total_hours.short_description = 'Часов'


class ProductionTrainingForm(OrganizationRestrictionFormMixin, forms.ModelForm):
    class Meta:
        model = ProductionTraining
        fields = (
            'organization',
            'subdivision',
            'department',
            'training_type',
            'program',
            'profession',
            'qualification_grade',
            'instructor',
            'theory_consultant',
            'commission_chairman',
            'commission',
            'commission_members',
            'training_city_ru',
            'training_city_by',
            'planned_hours',
            'notes',
        )
        widgets = {
            'organization': autocomplete.ModelSelect2(
                url='directory:organization-autocomplete',
                attrs={'data-placeholder': '🏢 Выберите организацию', 'class': 'select2-basic'}
            ),
            'subdivision': autocomplete.ModelSelect2(
                url='directory:subdivision-autocomplete',
                forward=['organization'],
                attrs={'data-placeholder': '🏭 Выберите подразделение', 'class': 'select2-basic'}
            ),
            'department': autocomplete.ModelSelect2(
                url='directory:department-autocomplete',
                forward=['organization', 'subdivision'],
                attrs={'data-placeholder': '🏬 Выберите отдел', 'class': 'select2-basic'}
            ),
            'instructor': autocomplete.ModelSelect2(
                url='directory:employee-autocomplete',
                forward=['organization'],
                attrs={'data-placeholder': '👨‍🏫 Выберите инструктора', 'class': 'select2-basic'}
            ),
            'theory_consultant': autocomplete.ModelSelect2(
                url='directory:employee-autocomplete',
                forward=['organization'],
                attrs={'data-placeholder': '👨‍🏫 Выберите консультанта', 'class': 'select2-basic'}
            ),
            'commission_chairman': autocomplete.ModelSelect2(
                url='directory:employee-autocomplete',
                forward=['organization'],
                attrs={'data-placeholder': '👔 Выберите председателя', 'class': 'select2-basic'}
            ),
            'commission': autocomplete.ModelSelect2(
                url='directory:qualification-commission-autocomplete',
                forward=['organization'],
                attrs={'data-placeholder': '🧾 Выберите квалификационную комиссию', 'class': 'select2-basic'}
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        org_id = (
            self.data.get('organization')
            or getattr(self.instance, 'organization_id', None)
            or self.initial.get('organization')
        )

        try:
            org_id_int = int(org_id) if org_id else None
        except (TypeError, ValueError):
            org_id_int = None

        if org_id_int:
            if 'commission' in self.fields:
                self.fields['commission'].queryset = (
                    self.fields['commission'].queryset.filter(
                        organization_id=org_id_int,
                        commission_type='qualification'
                    )
                )
        else:
            if 'commission' in self.fields:
                self.fields['commission'].queryset = self.fields['commission'].queryset.filter(
                    commission_type='qualification'
                ).none()


@admin.register(ProductionTraining)
class ProductionTrainingAdmin(admin.ModelAdmin):
    form = ProductionTrainingForm
    list_display = (
        'employee',
        'profession',
        'training_type',
        'start_date',
        'end_date',
        'status',
        'get_instructor'
    )
    list_filter = ('training_type', 'status', 'profession')
    search_fields = ('employee__full_name_nominative',)
    ordering = ('-created_at',)

    def get_form(self, request, obj=None, **kwargs):
        Form = super().get_form(request, obj, **kwargs)

        class FormWithUser(Form):
            def __init__(self2, *args, **inner_kwargs):
                inner_kwargs['user'] = request.user
                super().__init__(*args, **inner_kwargs)

        return FormWithUser

    fieldsets = (
        ('Организация', {
            'fields': ('organization', 'subdivision', 'department')
        }),
        ('Сотрудник', {
            'fields': (
                'employee',
                'current_position',
                'prior_qualification',
                'workplace'
            )
        }),
        ('Программа обучения', {
            'fields': (
                'training_type',
                'program',
                'profession',
                'qualification_grade'
            )
        }),
        ('Даты', {
            'fields': (
                'start_date',
                'end_date',
                'exam_date',
                'practical_date'
            )
        }),
        ('Оценки', {
            'fields': (
                'theory_score',
                'exam_score',
                'practical_score',
                'practical_work_topic'
            ),
            'classes': ('collapse',)
        }),
        ('Роли', {
            'fields': (
                'instructor',
                'theory_consultant',
                'commission_chairman',
                'commission',
                'commission_members'
            ),
            'classes': ('collapse',)
        }),
        ('Документы', {
            'fields': (
                'registration_number',
                'protocol_number',
                'protocol_date',
                'issue_date'
            ),
            'classes': ('collapse',)
        }),
        ('Место проведения', {
            'fields': (
                'training_city_ru',
                'training_city_by'
            ),
            'classes': ('collapse',)
        }),
        ('Часы', {
            'fields': (
                'planned_hours',
                'actual_hours'
            ),
            'classes': ('collapse',)
        }),
        ('Дополнительно', {
            'fields': (
                'status',
                'notes'
            )
        }),
    )

    filter_horizontal = ('commission_members',)

    def get_instructor(self, obj):
        """Показать инструктора."""
        if obj.instructor:
            return obj.instructor.full_name_nominative
        return '-'
    get_instructor.short_description = 'Инструктор'
