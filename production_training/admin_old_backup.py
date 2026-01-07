from django.contrib import admin

from .models import (
    TrainingType,
    TrainingQualificationGrade,
    TrainingProfession,
    EducationLevel,
    TrainingProgram,
    TrainingProgramSection,
    TrainingEntryType,
    TrainingProgramEntry,
    TrainingScheduleRule,
    TrainingRoleType,
    ProductionTraining,
    TrainingRoleAssignment,
    TrainingDiaryEntry,
    TrainingTheoryConsultation,
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


class TrainingProgramEntryInline(admin.TabularInline):
    model = TrainingProgramEntry
    extra = 0


class TrainingProgramSectionInline(admin.TabularInline):
    model = TrainingProgramSection
    extra = 0
    show_change_link = True


@admin.register(TrainingProgram)
class TrainingProgramAdmin(admin.ModelAdmin):
    list_display = ('name', 'training_type', 'profession', 'qualification_grade', 'is_active', 'order')
    list_filter = ('training_type', 'profession', 'is_active')
    search_fields = ('name',)
    ordering = ('order', 'name')
    inlines = [TrainingProgramSectionInline]


@admin.register(TrainingProgramSection)
class TrainingProgramSectionAdmin(admin.ModelAdmin):
    list_display = ('title', 'program', 'order')
    list_filter = ('program',)
    search_fields = ('title',)
    ordering = ('program', 'order')
    inlines = [TrainingProgramEntryInline]


@admin.register(TrainingEntryType)
class TrainingEntryTypeAdmin(admin.ModelAdmin):
    list_display = ('name', 'code', 'is_active', 'order')
    list_filter = ('is_active',)
    search_fields = ('name', 'code')
    ordering = ('order', 'name')


@admin.register(TrainingScheduleRule)
class TrainingScheduleRuleAdmin(admin.ModelAdmin):
    list_display = ('name', 'use_workdays', 'start_offset_days', 'is_active')
    list_filter = ('use_workdays', 'is_active')
    search_fields = ('name',)


@admin.register(TrainingRoleType)
class TrainingRoleTypeAdmin(admin.ModelAdmin):
    list_display = ('name', 'code', 'is_required', 'is_multi', 'is_active', 'order')
    list_filter = ('is_active', 'is_required', 'is_multi')
    search_fields = ('name', 'code')
    ordering = ('order', 'name')


class TrainingRoleAssignmentInline(admin.TabularInline):
    model = TrainingRoleAssignment
    extra = 0


class TrainingDiaryEntryInline(admin.TabularInline):
    model = TrainingDiaryEntry
    extra = 0


class TrainingTheoryConsultationInline(admin.TabularInline):
    model = TrainingTheoryConsultation
    extra = 0


@admin.register(ProductionTraining)
class ProductionTrainingAdmin(admin.ModelAdmin):
    list_display = (
        'employee', 'profession', 'training_type', 'start_date', 'end_date', 'status'
    )
    list_filter = ('training_type', 'status', 'profession')
    search_fields = ('employee__full_name_nominative',)
    ordering = ('-created_at',)
    inlines = [
        TrainingRoleAssignmentInline,
        TrainingTheoryConsultationInline,
        TrainingDiaryEntryInline,
    ]


@admin.register(TrainingRoleAssignment)
class TrainingRoleAssignmentAdmin(admin.ModelAdmin):
    list_display = ('training', 'role_type', 'employee', 'is_active', 'order')
    list_filter = ('role_type', 'is_active')
    search_fields = ('training__employee__full_name_nominative', 'employee__full_name_nominative')
    ordering = ('training', 'order')


@admin.register(TrainingDiaryEntry)
class TrainingDiaryEntryAdmin(admin.ModelAdmin):
    list_display = ('training', 'entry_date', 'entry_type', 'hours', 'score', 'order')
    list_filter = ('entry_type',)
    search_fields = ('training__employee__full_name_nominative', 'topic')
    ordering = ('training', 'order')


@admin.register(TrainingTheoryConsultation)
class TrainingTheoryConsultationAdmin(admin.ModelAdmin):
    list_display = ('training', 'date', 'consultant', 'hours', 'order')
    list_filter = ('consultant',)
    search_fields = ('training__employee__full_name_nominative', 'consultant__full_name_nominative')
    ordering = ('training', 'order')
