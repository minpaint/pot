# -*- coding: utf-8 -*-
"""
Упрощённая админка для production_training (5 моделей).
"""

from django import forms
from django.contrib import admin
from django.utils.html import format_html
from django.utils import timezone
from django.http import HttpResponse
from django.urls import reverse
from django.contrib import messages
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
            'fields': ('total_hours', 'weeks_distribution_csv'),
            'description': 'Всего часов и распределение по неделям (например: 40,40,40,40,32)'
        }),
        ('Дополнительно', {
            'fields': ('diary_template', 'description', 'is_active'),
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


class ProductionTrainingForm(OrganizationRestrictionFormMixin, forms.ModelForm):
    class Meta:
        model = ProductionTraining
        fields = (
            'organization',
            'employee',
            'training_type',
            'program',
            'profession',
            'qualification_grade',
            'theory_consultant',
            'commission_chairman',
            'instructor',
            'commission',
        )
        widgets = {
            'organization': autocomplete.ModelSelect2(
                url='directory:organization-autocomplete',
                attrs={'data-placeholder': '🏢 Выберите организацию', 'class': 'select2-basic'}
            ),
            'employee': autocomplete.ModelSelect2(
                url='directory:employee-autocomplete',
                forward=['organization'],
                attrs={'data-placeholder': '👤 Сотрудник', 'class': 'select2-basic'}
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
            'commission': autocomplete.ModelSelect2(
                url='directory:qualification-commission-autocomplete',
                forward=['organization'],
                attrs={'data-placeholder': '🧾 Выберите квалификационную комиссию', 'class': 'select2-basic'}
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Инициализация queryset'ов по выбранной организации (для первичного рендера/редактирования)
        org_id = (
            self.data.get('organization')
            or getattr(self.instance, 'organization_id', None)
            or self.initial.get('organization')
        )

        try:
            org_id_int = int(org_id) if org_id else None
        except (TypeError, ValueError):
            org_id_int = None

        # Подставить эталонные роли из организации при создании новой карточки
        if not self.instance.pk and org_id_int:
            from directory.models import Organization
            try:
                org = Organization.objects.get(pk=org_id_int)
                if org.default_theory_consultant and not self.initial.get('theory_consultant'):
                    self.initial['theory_consultant'] = org.default_theory_consultant
                if org.default_commission_chairman and not self.initial.get('commission_chairman'):
                    self.initial['commission_chairman'] = org.default_commission_chairman
                if org.default_instructor and not self.initial.get('instructor'):
                    self.initial['instructor'] = org.default_instructor
            except Organization.DoesNotExist:
                pass

        if org_id_int:
            # Подстрахуем связанные справочники, если они понадобятся при редактировании
            if 'commission' in self.fields:
                self.fields['commission'].queryset = (
                    self.fields['commission'].queryset.filter(
                        organization_id=org_id_int,
                        commission_type='qualification'
                    )
                )
            for staff_field in ('employee', 'theory_consultant', 'commission_chairman', 'instructor'):
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
            for staff_field in ('employee', 'theory_consultant', 'commission_chairman', 'instructor'):
                if staff_field in self.fields:
                    self.fields[staff_field].queryset = self.fields[staff_field].queryset.none()


@admin.register(ProductionTraining)
class ProductionTrainingAdmin(admin.ModelAdmin):
    form = ProductionTrainingForm
    list_display = (
        'get_employee_link',
        'get_current_position',
        'get_training_profession',
        'organization',
        'start_date',
        'end_date',
        'get_days_left',
    )
    list_filter = ('organization', 'training_type', 'profession')
    search_fields = (
        'organization__full_name_ru',
        'organization__short_name_ru',
        'employee__full_name_nominative',
        'current_position__position_name',
        'profession__name_ru_nominative',
        'training_type__name_ru',
    )
    ordering = ('organization__full_name_ru', '-start_date', 'profession__name_ru_nominative')
    date_hierarchy = 'start_date'
    list_display_links = ('get_training_profession',)
    list_select_related = ('employee', 'employee__position', 'current_position', 'organization', 'profession')

    fieldsets = (
        ('Основная информация', {
            'fields': ('organization', 'employee', 'status')
        }),
        ('Программа обучения', {
            'fields': (
                'training_type',
                'program',
                'profession',
                'qualification_grade'
            )
        }),
        ('📅 Даты обучения', {
            'fields': (
                'start_date',
                'end_date',
                'exam_date',
                'practical_date',
                'protocol_date',
            ),
            'description': 'Установите дату начала — остальные даты рассчитаются автоматически при сохранении.'
        }),
        ('Роли', {
            'fields': (
                'theory_consultant',
                'commission_chairman',
                'instructor',
            ),
            'description': 'Роли подставляются автоматически из эталонных ролей организации, но их можно переопределить.',
            'classes': ('collapse',)
        }),
        ('Комиссия', {
            'fields': ('commission',),
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

    def get_employee_link(self, obj):
        """Показать ссылку на карточку сотрудника."""
        if not obj.employee_id:
            return '-'
        url = reverse('admin:directory_employee_change', args=[obj.employee_id])
        return format_html('<a href="{}">{}</a>', url, obj.employee.full_name_nominative)
    get_employee_link.short_description = 'Сотрудник'

    def get_current_position(self, obj):
        """Показать текущую должность сотрудника."""
        position = obj.current_position or (obj.employee.position if obj.employee else None)
        return position.position_name if position else '-'
    get_current_position.short_description = 'Текущая должность'

    def get_training_profession(self, obj):
        """Показать профессию обучения."""
        return obj.profession.name_ru_nominative if obj.profession else '-'
    get_training_profession.short_description = 'Профессия обучения'
    get_training_profession.admin_order_field = 'profession__name_ru_nominative'

    def get_days_left(self, obj):
        """Сколько дней осталось до конца обучения."""
        if not obj.end_date:
            return '-'
        today = timezone.localdate()
        days_left = (obj.end_date - today).days
        if days_left < 0:
            return f'Просрочено на {abs(days_left)}'
        return days_left
    get_days_left.short_description = 'До окончания, дней'
    get_days_left.admin_order_field = 'end_date'

    def get_instructor(self, obj):
        """Показать инструктора."""
        if obj.instructor:
            return obj.instructor.full_name_nominative
        return '-'
    get_instructor.short_description = 'Инструктор'

    # ========================================================================
    # ACTIONS ДЛЯ ГЕНЕРАЦИИ ДОКУМЕНТОВ
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

    def action_recalculate_dates(self, request, queryset):
        """
        📅 Пересчитать все даты по дате начала.

        Позволяет массово пересчитать даты для выбранных карточек обучения.
        Работает только для карточек с заполненной датой начала.
        """
        updated_count = 0
        skipped_count = 0

        for training in queryset:
            if training.start_date:
                # Принудительно пересчитываем все даты
                training.recalculate_dates(force=True)
                training.save()
                updated_count += 1
            else:
                skipped_count += 1

        if updated_count > 0:
            self.message_user(
                request,
                f'✅ Пересчитаны даты для {updated_count} карточек обучения',
                level=messages.SUCCESS
            )

        if skipped_count > 0:
            self.message_user(
                request,
                f'⚠️ Пропущено {skipped_count} карточек (не заполнена дата начала)',
                level=messages.WARNING
            )

    action_recalculate_dates.short_description = '📅 Пересчитать даты по дате начала'

    def _download_document(self, request, result, doc_type):
        """Вспомогательная функция для скачивания документа."""
        if result:
            response = HttpResponse(
                result['content'].getvalue(),
                content_type='application/vnd.openxmlformats-officedocument.wordprocessingml.document'
            )
            response['Content-Disposition'] = f'attachment; filename="{result["filename"]}"'
            return response
        else:
            self.message_user(request, f'Ошибка при генерации документа "{doc_type}"', level=messages.ERROR)
            return None

    def action_generate_application(self, request, queryset):
        """Сгенерировать заявление."""
        if queryset.count() != 1:
            self.message_user(request, 'Выберите ровно одно обучение', level=messages.WARNING)
            return
        training = queryset.first()
        result = generate_application(training, user=request.user)
        return self._download_document(request, result, 'Заявление')
    action_generate_application.short_description = '📄 Сгенерировать заявление'

    def action_generate_order(self, request, queryset):
        """Сгенерировать приказ."""
        if queryset.count() != 1:
            self.message_user(request, 'Выберите ровно одно обучение', level=messages.WARNING)
            return
        training = queryset.first()
        result = generate_order(training, user=request.user)
        return self._download_document(request, result, 'Приказ')
    action_generate_order.short_description = '📄 Сгенерировать приказ'

    def action_generate_theory_card(self, request, queryset):
        """Сгенерировать карточку теории."""
        if queryset.count() != 1:
            self.message_user(request, 'Выберите ровно одно обучение', level=messages.WARNING)
            return
        training = queryset.first()
        result = generate_theory_card(training, user=request.user)
        return self._download_document(request, result, 'Карточка теории')
    action_generate_theory_card.short_description = '📄 Сгенерировать карточку теории'

    def action_generate_presentation(self, request, queryset):
        """Сгенерировать представление."""
        if queryset.count() != 1:
            self.message_user(request, 'Выберите ровно одно обучение', level=messages.WARNING)
            return
        training = queryset.first()
        result = generate_presentation(training, user=request.user)
        return self._download_document(request, result, 'Представление')
    action_generate_presentation.short_description = '📄 Сгенерировать представление'

    def action_generate_protocol(self, request, queryset):
        """Сгенерировать протокол комиссии."""
        if queryset.count() != 1:
            self.message_user(request, 'Выберите ровно одно обучение', level=messages.WARNING)
            return
        training = queryset.first()
        result = generate_protocol(training, user=request.user)
        return self._download_document(request, result, 'Протокол')
    action_generate_protocol.short_description = '📄 Сгенерировать протокол комиссии'

    def action_generate_trial_application(self, request, queryset):
        """Сгенерировать заявление на пробную работу."""
        if queryset.count() != 1:
            self.message_user(request, 'Выберите ровно одно обучение', level=messages.WARNING)
            return
        training = queryset.first()
        result = generate_trial_application(training, user=request.user)
        return self._download_document(request, result, 'Заявление на пробную работу')
    action_generate_trial_application.short_description = '📄 Сгенерировать заявление на пробную работу'

    def action_generate_trial_conclusion(self, request, queryset):
        """Сгенерировать заключение по пробной работе."""
        if queryset.count() != 1:
            self.message_user(request, 'Выберите ровно одно обучение', level=messages.WARNING)
            return
        training = queryset.first()
        result = generate_trial_conclusion(training, user=request.user)
        return self._download_document(request, result, 'Заключение по пробной работе')
    action_generate_trial_conclusion.short_description = '📄 Сгенерировать заключение по пробной работе'

    def action_generate_diary(self, request, queryset):
        """Сгенерировать дневник обучения."""
        if queryset.count() != 1:
            self.message_user(request, 'Выберите ровно одно обучение', level=messages.WARNING)
            return
        training = queryset.first()
        result = generate_diary(training, user=request.user)
        return self._download_document(request, result, 'Дневник')
    action_generate_diary.short_description = '📄 Сгенерировать дневник обучения'

    def action_generate_all_documents(self, request, queryset):
        """Сгенерировать все документы (архив ZIP)."""
        if queryset.count() != 1:
            self.message_user(request, 'Выберите ровно одно обучение', level=messages.WARNING)
            return

        training = queryset.first()
        results = generate_all_training_documents(training, user=request.user)

        # Подсчёт успешных и неудачных
        success_count = sum(1 for r in results.values() if r is not None)
        total_count = len(results)

        if success_count == 0:
            self.message_user(
                request,
                f'Не удалось сгенерировать ни один документ из {total_count}',
                level=messages.ERROR
            )
            return

        # Создание ZIP-архива
        import zipfile
        from io import BytesIO

        zip_buffer = BytesIO()
        with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
            for doc_type, result in results.items():
                if result:
                    zip_file.writestr(result['filename'], result['content'].getvalue())

        zip_buffer.seek(0)

        # Генерация имени ZIP-файла
        employee_name = training.employee.full_name_nominative if training.employee else 'Без_сотрудника'
        safe_name = employee_name.replace(' ', '_')
        import datetime
        timestamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
        zip_filename = f"Документы_обучения_{safe_name}_{timestamp}.zip"

        # Отправка ZIP-файла
        response = HttpResponse(zip_buffer.getvalue(), content_type='application/zip')
        response['Content-Disposition'] = f'attachment; filename="{zip_filename}"'

        self.message_user(
            request,
            f'Сгенерировано {success_count} из {total_count} документов',
            level=messages.SUCCESS if success_count == total_count else messages.WARNING
        )

        return response
    action_generate_all_documents.short_description = '📦 Сгенерировать все документы (ZIP)'
