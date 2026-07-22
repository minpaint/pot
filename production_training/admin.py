# -*- coding: utf-8 -*-
"""
Упрощённая админка для production_training (5 моделей).
"""

import re
from urllib.parse import quote

from django import forms
from django.contrib import admin
from django.utils.html import format_html
from django.http import HttpResponse
from django.urls import reverse, path
from django.contrib import messages
from django.shortcuts import get_object_or_404
from dal import autocomplete
from directory.forms.mixins import OrganizationRestrictionFormMixin
from directory.admin.mixins.org_filter import apply_session_org_filter
from directory.models import Employee

from .models import (
    TrainingType,
    TrainingQualificationGrade,
    TrainingProfession,
    TrainingProgram,
    ProductionTraining,
    TrainingAssignment,
)
from .document_generators.training_documents import (
    generate_application,
    generate_order,
    generate_theory_card,
    generate_presentation,
    generate_protocol,
    generate_trial_application,
    generate_trial_conclusion,
    generate_diary,
    generate_all_training_documents,
    generate_merged_document,
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


class TrainingProgramForm(forms.ModelForm):
    """Форма программы обучения с удобным вводом распределения по неделям."""

    weeks_distribution_csv = forms.CharField(
        required=False,
        label="Часы по неделям",
        help_text="Введите через запятую: 40,40,40,40,32",
        widget=forms.TextInput(attrs={'placeholder': '40,40,40,40,32', 'style': 'width: 300px;'})
    )

    class Meta:
        model = TrainingProgram
        fields = '__all__'
        # Deprecated поля + weeks_distribution (заменён на csv-поле)
        exclude = ['content', 'weekly_hours', 'duration_days', 'weeks_distribution']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.weeks_distribution:
            self.fields['weeks_distribution_csv'].initial = ','.join(
                str(x) for x in self.instance.weeks_distribution
            )

    def clean_weeks_distribution_csv(self):
        value = self.cleaned_data.get('weeks_distribution_csv', '')
        if not value:
            return []
        parts = [p.strip() for p in value.split(',') if p.strip()]
        hours = []
        for p in parts:
            try:
                hours.append(int(p))
            except ValueError:
                raise forms.ValidationError("Используйте целые числа, разделенные запятой.")
        return hours

    def save(self, commit=True):
        hours = self.cleaned_data.get('weeks_distribution_csv', [])
        self.instance.weeks_distribution = hours
        # Автозаполнение total_hours если не задано
        if hours and not self.instance.total_hours:
            self.instance.total_hours = sum(hours)
        return super().save(commit=commit)


@admin.register(TrainingProgram)
class TrainingProgramAdmin(admin.ModelAdmin):
    form = TrainingProgramForm
    list_display = (
        'name',
        'training_type',
        'profession',
        'qualification_grade',
        'total_hours',
        'get_weeks_count',
        'get_weeks_display',
        'is_active'
    )
    list_filter = ('training_type', 'profession', 'is_active')
    search_fields = ('name',)
    ordering = ('training_type', 'profession', 'name')

    fieldsets = (
        ('Основная информация', {
            'fields': ('name', 'training_type', 'profession', 'qualification_grade')
        }),
        ('📊 Часы программы', {
            'fields': ('total_hours', 'practical_work_hours', 'weeks_distribution_csv'),
            'description': 'Всего часов и распределение по неделям (например: 40,40,40,40,32)'
        }),
        ('Дополнительно', {
            'fields': ('practical_work_topic', 'diary_template', 'description', 'is_active'),
            'classes': ('collapse',)
        }),
    )

    def get_weeks_count(self, obj):
        """Показать количество недель."""
        return obj.get_weeks_count()
    get_weeks_count.short_description = 'Недель'

    def get_weeks_display(self, obj):
        """Показать распределение по неделям."""
        weeks = obj.get_weeks_distribution()
        if weeks:
            return ' + '.join(str(x) for x in weeks)
        return '-'
    get_weeks_display.short_description = 'По неделям'


# ============================================================================
# INLINE ДЛЯ СОТРУДНИКОВ В КУРСЕ ОБУЧЕНИЯ (перед ProductionTrainingAdmin)
# ============================================================================

class TrainingAssignmentInline(admin.TabularInline):
    """Inline для сотрудников внутри курса обучения."""
    model = TrainingAssignment
    extra = 1
    fields = (
        'employee',
        'start_date',
        'end_date',
        'get_days_left_inline',
        'theory_score',
        'exam_score',
        'practical_score',
        'planned_hours',
        'actual_hours',
    )
    readonly_fields = ('end_date', 'get_days_left_inline')
    autocomplete_fields = ['employee']

    def formfield_for_dbfield(self, db_field, request, **kwargs):
        """Сузить поля оценок и часов."""
        field = super().formfield_for_dbfield(db_field, request, **kwargs)
        if db_field.name in ('theory_score', 'exam_score', 'practical_score'):
            field.widget.attrs['style'] = 'width: 60px;'
        elif db_field.name in ('planned_hours', 'actual_hours'):
            field.widget.attrs['style'] = 'width: 70px;'
        return field

    def get_days_left_inline(self, obj):
        """Дней до окончания."""
        if not obj or not obj.end_date:
            return '-'
        days = obj.get_days_left()
        if days is None:
            return '-'
        if days < 0:
            return format_html('<span style="color: red;">Просрочено на {}</span>', abs(days))
        elif days <= 7:
            return format_html('<span style="color: orange;">{}</span>', days)
        return days
    get_days_left_inline.short_description = 'До окончания'


class ProductionTrainingForm(OrganizationRestrictionFormMixin, forms.ModelForm):
    """Форма курса обучения."""

    class Meta:
        model = ProductionTraining
        fields = (
            'organization',
            'training_type',
            'program',
            'profession',
            'qualification_grade',
            'theory_consultant',
            'commission_chairman',
            'instructor',
            'responsible_person',
            'commission',
            'training_city_ru',
            'training_city_by',
            'notes',
        )
        widgets = {
            'organization': autocomplete.ModelSelect2(
                url='directory:organization-autocomplete',
                attrs={'data-placeholder': '🏢 Выберите организацию', 'class': 'select2-basic'}
            ),
            'theory_consultant': autocomplete.ModelSelect2(
                url='directory:employee-autocomplete',
                forward=['organization'],
                attrs={'data-placeholder': '👨‍🏫 Консультант теоретического обучения', 'class': 'select2-basic'}
            ),
            'commission_chairman': autocomplete.ModelSelect2(
                url='directory:employee-autocomplete',
                forward=['organization'],
                attrs={'data-placeholder': '👔 Руководитель производственного обучения', 'class': 'select2-basic'}
            ),
            'instructor': autocomplete.ModelSelect2(
                url='directory:employee-autocomplete',
                forward=['organization'],
                attrs={'data-placeholder': '🧑‍🏭 Инструктор производственного обучения', 'class': 'select2-basic'}
            ),
            'responsible_person': autocomplete.ModelSelect2(
                url='directory:employee-autocomplete',
                forward=['organization'],
                attrs={'data-placeholder': '👤 Ответственный за обучение', 'class': 'select2-basic'}
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
            for staff_field in ('theory_consultant', 'commission_chairman', 'instructor', 'responsible_person'):
                if staff_field in self.fields:
                    qs = self.fields[staff_field].queryset
                    current_obj = getattr(self.instance, staff_field, None)
                    current_value = getattr(current_obj, 'pk', None)
                    filtered_qs = qs.filter(organization_id=org_id_int)
                    if current_value:
                        filtered_qs = filtered_qs | qs.filter(pk=current_value)
                    self.fields[staff_field].queryset = filtered_qs.distinct()
        else:
            if 'commission' in self.fields:
                self.fields['commission'].queryset = self.fields['commission'].queryset.filter(
                    commission_type='qualification'
                ).none()
            for staff_field in ('theory_consultant', 'commission_chairman', 'instructor', 'responsible_person'):
                if staff_field in self.fields:
                    self.fields[staff_field].queryset = self.fields[staff_field].queryset.none()


@admin.register(ProductionTraining)
class ProductionTrainingAdmin(admin.ModelAdmin):
    form = ProductionTrainingForm
    list_display = (
        'get_training_profession',
        'organization',
        'get_assignments_count',
        'get_instructor_name',
    )
    list_filter = ('organization', 'training_type', 'profession')
    search_fields = (
        'organization__full_name_ru',
        'organization__short_name_ru',
        'profession__name_ru_nominative',
        'training_type__name_ru',
    )
    ordering = ('organization__full_name_ru', 'profession__name_ru_nominative')
    list_display_links = ('get_training_profession',)
    list_select_related = ('organization', 'profession', 'training_type', 'instructor')
    inlines = [TrainingAssignmentInline]

    class Media:
        js = (
            'production_training/js/training_dates.js',
            'production_training/js/training_days_left.js',
        )

    fieldsets = (
        ('Основная информация', {
            'fields': ('organization', 'training_type', 'profession', 'qualification_grade')
        }),
        ('Программа', {
            'fields': ('program',),
            'classes': ('collapse',)
        }),
        ('Роли', {
            'fields': (
                'theory_consultant',
                'commission_chairman',
                'instructor',
                'responsible_person',
            ),
            'description': 'Роли подставляются автоматически из эталонных ролей организации.',
            'classes': ('collapse',)
        }),
        ('Комиссия', {
            'fields': ('commission',),
            'classes': ('collapse',)
        }),
        ('Место проведения', {
            'fields': ('training_city_ru', 'training_city_by'),
            'classes': ('collapse',)
        }),
        ('Примечания', {
            'fields': ('notes',),
            'classes': ('collapse',)
        }),
    )

    def get_form(self, request, obj=None, **kwargs):
        Form = super().get_form(request, obj, **kwargs)

        class FormWithUser(Form):
            def __init__(self2, *args, **inner_kwargs):
                inner_kwargs['user'] = request.user
                if not obj and not inner_kwargs.get('initial_org_id'):
                    selected_org_id = request.session.get('selected_org_id')
                    if selected_org_id:
                        try:
                            inner_kwargs['initial_org_id'] = int(selected_org_id)
                        except (ValueError, TypeError):
                            pass
                super().__init__(*args, **inner_kwargs)

        return FormWithUser

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if not request.user.is_superuser and hasattr(request.user, 'profile'):
            allowed_orgs = request.user.profile.organizations.all()
            qs = qs.filter(organization__in=allowed_orgs)
        return apply_session_org_filter(request, qs)

    def get_training_profession(self, obj):
        """Профессия обучения с разрядом."""
        name = obj.profession.name_ru_nominative if obj.profession else '-'
        if obj.qualification_grade:
            name += f" ({obj.qualification_grade.label_ru})"
        type_label = obj.training_type.name_ru if obj.training_type else ''
        if type_label:
            return format_html(
                '<div>{}<br><span style="color: #666; font-size: 11px;">{}</span></div>',
                name,
                type_label
            )
        return name
    get_training_profession.short_description = 'Курс обучения'
    get_training_profession.admin_order_field = 'profession__name_ru_nominative'

    def get_assignments_count(self, obj):
        """Количество назначенных сотрудников."""
        count = obj.assignments.count()
        if count == 0:
            return format_html('<span style="color: #999;">0</span>')
        url = reverse('admin:production_training_trainingassignment_changelist') + f'?training__id__exact={obj.pk}'
        return format_html('<a href="{}">{} сотр.</a>', url, count)
    get_assignments_count.short_description = 'Сотрудники'

    def get_instructor_name(self, obj):
        """Инструктор."""
        if obj.instructor:
            return obj.instructor.full_name_nominative
        return '-'
    get_instructor_name.short_description = 'Инструктор'


# ============================================================================
# АДМИНКА ДЛЯ СОТРУДНИКОВ НА ОБУЧЕНИИ
# ============================================================================

class TrainingAssignmentForm(OrganizationRestrictionFormMixin, forms.ModelForm):
    """Форма назначения сотрудника на обучение."""

    class Meta:
        model = TrainingAssignment
        fields = '__all__'
        widgets = {
            'employee': autocomplete.ModelSelect2(
                url='production_training:employee-for-assignment-autocomplete',
                attrs={'data-placeholder': '👤 Выберите сотрудника', 'class': 'select2-basic'}
            ),
            'current_position': autocomplete.ModelSelect2(
                url='production_training:position-for-assignment-autocomplete',
                attrs={'data-placeholder': '💼 Текущая должность', 'class': 'select2-basic'}
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Фильтруем сотрудников по организации курса
        training_id = (
            self.data.get('training')
            or getattr(self.instance, 'training_id', None)
            or self.initial.get('training')
        )
        if training_id:
            try:
                training = ProductionTraining.objects.get(pk=training_id)
                if 'employee' in self.fields and training.organization_id:
                    self.fields['employee'].queryset = Employee.objects.filter(
                        organization_id=training.organization_id
                    )
            except ProductionTraining.DoesNotExist:
                pass


@admin.register(TrainingAssignment)
class TrainingAssignmentAdmin(admin.ModelAdmin):
    """
    Админка для сотрудников на обучении.

    Позволяет:
    - Просматривать список всех сотрудников на обучении
    - Редактировать дату начала прямо в списке (list_editable)
    - Генерировать документы для сотрудника
    """
    form = TrainingAssignmentForm
    list_display = (
        'get_employee_link',
        'get_current_position',
        'get_training_with_type',
        'start_date',
        'get_end_date',
        'get_days_left',
        'get_status_badge',
        'get_documents_button',
    )
    list_display_links = ('get_training_with_type',)
    list_editable = ('start_date',)
    list_filter = (
        'training__organization',
        'training__profession',
        'training__training_type',
    )
    search_fields = (
        'employee__full_name_nominative',
        'training__profession__name_ru_nominative',
        'training__organization__full_name_ru',
    )
    ordering = ('-start_date', 'employee__full_name_nominative')
    date_hierarchy = 'start_date'
    list_select_related = (
        'employee',
        'employee__position',
        'training',
        'training__organization',
        'training__profession',
        'training__training_type',
        'current_position',
    )

    class Media:
        js = (
            'production_training/js/training_dates.js',
            'production_training/js/training_days_left.js',
        )

    fieldsets = (
        ('Основная информация', {
            'fields': ('training', 'employee', 'current_position')
        }),
        ('📅 Даты обучения', {
            'fields': (
                'start_date',
                'end_date',
                'exam_date',
                'practical_date',
                'protocol_date',
                'issue_date',
            ),
            'description': 'Установите дату начала — остальные даты рассчитаются автоматически.'
        }),
        ('📊 Результаты', {
            'fields': (
                'theory_score',
                'exam_score',
                'practical_score',
                'practical_work_topic',
            ),
            'classes': ('collapse',)
        }),
        ('📄 Документы', {
            'fields': (
                'registration_number',
                'protocol_number',
            ),
            'classes': ('collapse',)
        }),
        ('Дополнительно', {
            'fields': (
                'prior_qualification',
                'workplace',
                'notes',
            ),
            'classes': ('collapse',)
        }),
    )

    readonly_fields = ('end_date', 'exam_date', 'practical_date', 'protocol_date')

    def get_form(self, request, obj=None, **kwargs):
        Form = super().get_form(request, obj, **kwargs)

        class FormWithUser(Form):
            def __init__(self2, *args, **inner_kwargs):
                inner_kwargs['user'] = request.user
                super().__init__(*args, **inner_kwargs)

        return FormWithUser

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if not request.user.is_superuser and hasattr(request.user, 'profile'):
            allowed_orgs = request.user.profile.organizations.all()
            qs = qs.filter(training__organization__in=allowed_orgs)
        qs = apply_session_org_filter(
            request,
            qs,
            organization_lookup='training__organization_id',
            get_filter_keys=('training__organization__id__exact', 'training__organization_id'),
        )
        return qs

    def save_model(self, request, obj, form, change):
        """Автоматический пересчёт дат при сохранении."""
        super().save_model(request, obj, form, change)

        if obj.start_date:
            obj.refresh_from_db()
            obj.recalculate_dates(force=True)
            TrainingAssignment.objects.filter(pk=obj.pk).update(
                end_date=obj.end_date,
                exam_date=obj.exam_date,
                practical_date=obj.practical_date,
                protocol_date=obj.protocol_date,
            )

    def get_employee_link(self, obj):
        """Ссылка на карточку сотрудника."""
        if not obj.employee_id:
            return '-'
        url = reverse('admin:directory_employee_change', args=[obj.employee_id])
        return format_html('<a href="{}">{}</a>', url, obj.employee.full_name_nominative)
    get_employee_link.short_description = 'Сотрудник'
    get_employee_link.admin_order_field = 'employee__full_name_nominative'

    def get_current_position(self, obj):
        """Текущая должность."""
        position = obj.current_position or (obj.employee.position if obj.employee else None)
        return position.position_name if position else '-'
    get_current_position.short_description = 'Должность'

    def get_training_with_type(self, obj):
        """Курс обучения с типом."""
        training = obj.training
        if not training:
            return '-'
        type_label = training.training_type.name_ru if training.training_type else ''
        if type_label:
            return format_html(
                '<div>{}<br><span style="color: #666; font-size: 11px;">{}</span></div>',
                training,
                type_label
            )
        return training
    get_training_with_type.short_description = 'Курс обучения'
    get_training_with_type.admin_order_field = 'training__profession__name_ru_nominative'

    def get_end_date(self, obj):
        """Дата окончания."""
        return obj.end_date.strftime('%d.%m.%Y') if obj.end_date else '-'
    get_end_date.short_description = 'Окончание'
    get_end_date.admin_order_field = 'end_date'

    def get_days_left(self, obj):
        """Дней до окончания с цветовой индикацией."""
        if not obj.end_date:
            return '-'
        days = obj.get_days_left()
        if days < 0:
            return format_html(
                '<span class="pt-days-left" data-end-date="{}" style="color: red;">Просрочено на {}</span>',
                obj.end_date.isoformat(),
                abs(days)
            )
        elif days <= 7:
            return format_html(
                '<span class="pt-days-left" data-end-date="{}" style="color: orange;">{}</span>',
                obj.end_date.isoformat(),
                days
            )
        return format_html(
            '<span class="pt-days-left" data-end-date="{}">{}</span>',
            obj.end_date.isoformat(),
            days
        )
    get_days_left.short_description = 'До окончания'
    get_days_left.admin_order_field = 'end_date'

    def get_status_badge(self, obj):
        """Бейдж статуса."""
        status = obj.get_status()
        colors = {
            'draft': '#999',
            'scheduled': '#17a2b8',
            'active': '#28a745',
            'completed': '#6c757d',
        }
        return format_html(
            '<span style="padding: 2px 8px; border-radius: 10px; '
            'background: {}; color: white; font-size: 11px;">{}</span>',
            colors.get(status, '#999'),
            obj.get_status_display()
        )
    get_status_badge.short_description = 'Статус'

    def get_documents_button(self, obj):
        """Кнопка генерации документов."""
        if not obj.start_date:
            return format_html(
                '<span style="color: #999;" title="Установите дату начала">—</span>'
            )
        url = reverse('admin:production_training_trainingassignment_generate_docs', args=[obj.pk])
        return format_html(
            '<a class="button" href="{}" style="padding: 3px 10px; '
            'background: #417690; color: white; border-radius: 4px; '
            'text-decoration: none; font-size: 11px; white-space: nowrap;" '
            'title="Скачать все документы в одном файле">📄 Документы</a>',
            url
        )
    get_documents_button.short_description = 'Документы'

    def get_urls(self):
        """Добавляем URL для генерации документов."""
        urls = super().get_urls()
        custom_urls = [
            path(
                '<int:pk>/generate-docs/',
                self.admin_site.admin_view(self.generate_documents_view),
                name='production_training_trainingassignment_generate_docs'
            ),
            path(
                'calculate-dates/',
                self.admin_site.admin_view(self.calculate_dates_view),
                name='production_training_trainingassignment_calculate_dates'
            ),
        ]
        return custom_urls + urls

    def calculate_dates_view(self, request):
        """AJAX endpoint для расчёта дат."""
        from django.http import JsonResponse
        from . import schedule

        start_date_str = request.GET.get('start_date')
        training_id = request.GET.get('training_id')
        employee_id = request.GET.get('employee_id')

        if not start_date_str:
            return JsonResponse({'error': 'start_date required'}, status=400)

        try:
            from datetime import datetime
            start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
        except ValueError:
            return JsonResponse({'error': 'Invalid date format'}, status=400)

        # Получаем weekly_hours из программы курса/типа обучения
        weekly_hours = None
        if training_id:
            try:
                training = ProductionTraining.objects.get(pk=training_id)
                if training.program:
                    weekly_hours = training.program.get_weeks_distribution() or None
                if not weekly_hours and training.training_type:
                    weekly_hours = schedule.get_weekly_hours(training.training_type.code)
                if not weekly_hours and training.training_type:
                    weekly_hours = schedule.get_weekly_hours(training.training_type.name_ru)
                if not weekly_hours and training.program and training.program.training_type:
                    weekly_hours = schedule.get_weekly_hours(training.program.training_type.code)
                if not weekly_hours and training.program and training.program.training_type:
                    weekly_hours = schedule.get_weekly_hours(training.program.training_type.name_ru)
            except ProductionTraining.DoesNotExist:
                pass
        if not weekly_hours:
            weekly_hours = [40]

        # Получаем график работы сотрудника
        work_schedule = '5/2'
        schedule_start = None
        if employee_id:
            try:
                employee = Employee.objects.get(pk=employee_id)
                work_schedule = employee.work_schedule or '5/2'
                schedule_start = employee.start_date or employee.hire_date
            except Employee.DoesNotExist:
                pass

        dates = schedule.compute_all_dates(
            start_date,
            weekly_hours,
            work_schedule=work_schedule,
            schedule_start=schedule_start,
        )

        return JsonResponse({
            'end_date': dates['end_date'].strftime('%d.%m.%Y') if dates.get('end_date') else '',
            'exam_date': dates['exam_date'].strftime('%d.%m.%Y') if dates.get('exam_date') else '',
            'practical_date': dates['practical_date'].strftime('%d.%m.%Y') if dates.get('practical_date') else '',
            'protocol_date': dates['protocol_date'].strftime('%d.%m.%Y') if dates.get('protocol_date') else '',
        })

    def generate_documents_view(self, request, pk):
        """View для генерации всех документов в один DOCX файл."""
        assignment = get_object_or_404(TrainingAssignment, pk=pk)

        # Генерируем объединённый документ
        result = generate_merged_document(assignment, user=request.user)

        if not result:
            messages.error(request, 'Не удалось сгенерировать документы')
            return HttpResponse(status=302, headers={'Location': request.META.get('HTTP_REFERER', '../')})

        filename = result.get('filename', 'Документы_обучения.docx')
        fallback_name = re.sub(r'[^A-Za-z0-9._-]+', '_', filename).strip('_')
        if not fallback_name:
            fallback_name = 'documents.docx'
        elif not fallback_name.lower().endswith('.docx'):
            fallback_name = f'{fallback_name}.docx'
        filename_encoded = quote(filename)

        response = HttpResponse(
            result['content'].getvalue(),
            content_type='application/vnd.openxmlformats-officedocument.wordprocessingml.document'
        )
        response['Content-Disposition'] = (
            f'attachment; filename="{fallback_name}"; filename*=UTF-8\'\'{filename_encoded}'
        )
        response['X-Content-Type-Options'] = 'nosniff'
        return response

    # ========================================================================
    # ACTIONS
    # ========================================================================

    actions = [
        'action_recalculate_dates',
        'action_generate_application',
        'action_generate_order',
        'action_generate_theory_card',
        'action_generate_presentation',
        'action_generate_protocol',
        'action_generate_trial_application',
        'action_generate_trial_conclusion',
        'action_generate_diary',
        'action_generate_all_documents',
    ]

    def _get_single_assignment(self, request, queryset):
        if queryset.count() != 1:
            self.message_user(request, 'Выберите ровно одного сотрудника', level=messages.WARNING)
            return None
        return queryset.first()

    def _download_document(self, request, result, doc_type):
        if result:
            filename = result.get('filename') or f'{doc_type}.docx'
            fallback_name = re.sub(r'[^A-Za-z0-9._-]+', '_', filename).strip('_')
            if not fallback_name:
                fallback_name = 'document.docx'
            elif not fallback_name.lower().endswith('.docx'):
                fallback_name = f'{fallback_name}.docx'
            filename_encoded = quote(filename)
            response = HttpResponse(
                result['content'].getvalue(),
                content_type='application/vnd.openxmlformats-officedocument.wordprocessingml.document'
            )
            response['Content-Disposition'] = (
                f'attachment; filename="{fallback_name}"; filename*=UTF-8\'\'{filename_encoded}'
            )
            response['X-Content-Type-Options'] = 'nosniff'
            return response
        self.message_user(request, f'Ошибка при генерации документа "{doc_type}"', level=messages.ERROR)
        return None

    def action_recalculate_dates(self, request, queryset):
        """Пересчитать даты для выбранных сотрудников."""
        updated_count = 0
        skipped_count = 0

        for assignment in queryset:
            if assignment.start_date:
                assignment.recalculate_dates(force=True)
                assignment.save()
                updated_count += 1
            else:
                skipped_count += 1

        if updated_count > 0:
            self.message_user(
                request,
                f'✅ Пересчитаны даты для {updated_count} сотрудников',
                level=messages.SUCCESS
            )

        if skipped_count > 0:
            self.message_user(
                request,
                f'⚠️ Пропущено {skipped_count} (не заполнена дата начала)',
                level=messages.WARNING
            )
    action_recalculate_dates.short_description = '📅 Пересчитать даты'

    def action_generate_application(self, request, queryset):
        """Сгенерировать заявление."""
        assignment = self._get_single_assignment(request, queryset)
        if not assignment:
            return
        result = generate_application(assignment, user=request.user)
        return self._download_document(request, result, 'Заявление')
    action_generate_application.short_description = '📄 Сгенерировать заявление'

    def action_generate_order(self, request, queryset):
        """Сгенерировать приказ."""
        assignment = self._get_single_assignment(request, queryset)
        if not assignment:
            return
        result = generate_order(assignment, user=request.user)
        return self._download_document(request, result, 'Приказ')
    action_generate_order.short_description = '📄 Сгенерировать приказ'

    def action_generate_theory_card(self, request, queryset):
        """Сгенерировать карточку теории."""
        assignment = self._get_single_assignment(request, queryset)
        if not assignment:
            return
        result = generate_theory_card(assignment, user=request.user)
        return self._download_document(request, result, 'Карточка теории')
    action_generate_theory_card.short_description = '📄 Сгенерировать карточку теории'

    def action_generate_presentation(self, request, queryset):
        """Сгенерировать представление."""
        assignment = self._get_single_assignment(request, queryset)
        if not assignment:
            return
        result = generate_presentation(assignment, user=request.user)
        return self._download_document(request, result, 'Представление')
    action_generate_presentation.short_description = '📄 Сгенерировать представление'

    def action_generate_protocol(self, request, queryset):
        """Сгенерировать протокол комиссии."""
        assignment = self._get_single_assignment(request, queryset)
        if not assignment:
            return
        result = generate_protocol(assignment, user=request.user)
        return self._download_document(request, result, 'Протокол')
    action_generate_protocol.short_description = '📄 Сгенерировать протокол комиссии'

    def action_generate_trial_application(self, request, queryset):
        """Сгенерировать заявление на пробную работу."""
        assignment = self._get_single_assignment(request, queryset)
        if not assignment:
            return
        result = generate_trial_application(assignment, user=request.user)
        return self._download_document(request, result, 'Заявление на пробную работу')
    action_generate_trial_application.short_description = '📄 Сгенерировать заявление на пробную работу'

    def action_generate_trial_conclusion(self, request, queryset):
        """Сгенерировать заключение по пробной работе."""
        assignment = self._get_single_assignment(request, queryset)
        if not assignment:
            return
        result = generate_trial_conclusion(assignment, user=request.user)
        return self._download_document(request, result, 'Заключение по пробной работе')
    action_generate_trial_conclusion.short_description = '📄 Сгенерировать заключение по пробной работе'

    def action_generate_diary(self, request, queryset):
        """Сгенерировать дневник обучения."""
        assignment = self._get_single_assignment(request, queryset)
        if not assignment:
            return
        result = generate_diary(assignment, user=request.user)
        return self._download_document(request, result, 'Дневник')
    action_generate_diary.short_description = '📄 Сгенерировать дневник обучения'

    def action_generate_all_documents(self, request, queryset):
        """Сгенерировать все документы (архив ZIP)."""
        assignment = self._get_single_assignment(request, queryset)
        if not assignment:
            return
        results = generate_all_training_documents(assignment, user=request.user)

        success_count = sum(1 for r in results.values() if r is not None)
        total_count = len(results)
        if success_count == 0:
            self.message_user(
                request,
                f'Не удалось сгенерировать ни один документ из {total_count}',
                level=messages.ERROR
            )
            return

        import zipfile
        from io import BytesIO

        zip_buffer = BytesIO()
        with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
            for result in results.values():
                if result:
                    zip_file.writestr(result['filename'], result['content'].getvalue())
        zip_buffer.seek(0)

        employee_name = assignment.employee.full_name_nominative if assignment.employee else 'Без_сотрудника'
        safe_name = employee_name.replace(' ', '_')
        from django.utils import timezone
        timestamp = timezone.now().strftime('%Y%m%d_%H%M%S')
        zip_filename = f"Документы_обучения_{safe_name}_{timestamp}.zip"

        response = HttpResponse(zip_buffer.getvalue(), content_type='application/zip')
        response['Content-Disposition'] = f'attachment; filename="{zip_filename}"'

        self.message_user(
            request,
            f'Сгенерировано {success_count} из {total_count} документов',
            level=messages.SUCCESS if success_count == total_count else messages.WARNING
        )
        return response
    action_generate_all_documents.short_description = '📦 Сгенерировать все документы (ZIP)'
