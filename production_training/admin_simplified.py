# -*- coding: utf-8 -*-
"""
Упрощённая админка для production_training (6 моделей).
"""

from django.contrib import admin
from django.utils.html import format_html

from .models import (
    TrainingType,
    TrainingQualificationGrade,
    TrainingProfession,
    EducationLevel,
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


@admin.register(EducationLevel)
class EducationLevelAdmin(admin.ModelAdmin):
    list_display = ('name_ru', 'name_by', 'is_active', 'order')
    list_filter = ('is_active',)
    search_fields = ('name_ru', 'name_by')
    ordering = ('order', 'name_ru')


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


@admin.register(ProductionTraining)
class ProductionTrainingAdmin(admin.ModelAdmin):
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

    fieldsets = (
        ('Основная информация', {
            'fields': ('employee', 'organization', 'subdivision', 'department')
        }),
        ('Программа обучения', {
            'fields': (
                'training_type',
                'program',
                'profession',
                'qualification_grade'
            )
        }),
        ('Данные сотрудника', {
            'fields': (
                'current_position',
                'education_level',
                'prior_qualification',
                'workplace'
            ),
            'classes': ('collapse',)
        }),
        ('Даты', {
            'fields': ('start_date', 'end_date')
        }),
        ('Роли', {
            'fields': (
                'instructor',
                'theory_consultant',
                'commission_chairman',
                'commission_members'
            ),
            'classes': ('collapse',)
        }),
        ('Экзамен', {
            'fields': ('exam_date', 'exam_score'),
            'classes': ('collapse',)
        }),
        ('Пробная работа', {
            'fields': ('practical_date', 'practical_score', 'practical_work_topic'),
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
        ('Место и часы', {
            'fields': (
                'training_city_ru',
                'training_city_by',
                'planned_hours',
                'actual_hours'
            ),
            'classes': ('collapse',)
        }),
        ('Статус', {
            'fields': ('status', 'notes')
        }),
    )

    filter_horizontal = ('commission_members',)

    def get_instructor(self, obj):
        """Показать инструктора."""
        if obj.instructor:
            return obj.instructor.full_name_nominative
        return '-'
    get_instructor.short_description = 'Инструктор'
