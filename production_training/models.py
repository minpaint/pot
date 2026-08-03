# -*- coding: utf-8 -*-
"""
Упрощённые модели для модуля "Обучение на производстве"

Изменения:
- 14 моделей → 6 моделей
- TrainingProgram: содержание программы в JSON вместо Section+Entry
- ProductionTraining: роли как прямые поля вместо отдельной модели
- Удалены: TrainingEntryType, TrainingScheduleRule, TrainingProgramSection,
  TrainingProgramEntry, TrainingRoleType, TrainingRoleAssignment,
  TrainingDiaryEntry, TrainingTheoryConsultation
"""

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from pathlib import Path

from . import schedule


# ============================================================================
# СПРАВОЧНИКИ (3 модели - БЕЗ ИЗМЕНЕНИЙ)
# ============================================================================

class TrainingType(models.Model):
    """
    Тип обучения: подготовка, переподготовка.

    Примеры:
    - preparation (Подготовка / Падрыхтоўка)
    - retraining (Переподготовка / Перападрыхтоўка)
    """
    code = models.CharField(
        max_length=50,
        unique=True,
        verbose_name="Код",
        help_text="Код типа обучения (например: preparation, retraining)"
    )
    name_ru = models.CharField(
        max_length=255,
        verbose_name="Название (рус)"
    )
    name_by = models.CharField(
        max_length=255,
        blank=True,
        verbose_name="Название (бел)"
    )
    description = models.TextField(
        blank=True,
        verbose_name="Описание"
    )
    is_active = models.BooleanField(
        default=True,
        verbose_name="Активен"
    )
    order = models.PositiveIntegerField(
        default=0,
        verbose_name="Порядок"
    )

    class Meta:
        verbose_name = "🎓 Тип обучения"
        verbose_name_plural = "🎓 Типы обучения"
        ordering = ['order', 'name_ru']

    def __str__(self):
        return self.name_ru


class TrainingQualificationGrade(models.Model):
    """
    Разряд квалификации: 2, 3, 4, 5, 6.

    Примеры:
    - 2 (второй)
    - 3 (третий)
    - 4 (четвёртый)
    """
    grade_number = models.PositiveIntegerField(
        verbose_name="Номер разряда"
    )
    label_ru = models.CharField(
        max_length=255,
        verbose_name="Разряд (рус)",
        help_text="Например: 3 (третий)"
    )
    label_by = models.CharField(
        max_length=255,
        blank=True,
        verbose_name="Разряд (бел)"
    )
    is_active = models.BooleanField(
        default=True,
        verbose_name="Активен"
    )
    order = models.PositiveIntegerField(
        default=0,
        verbose_name="Порядок"
    )

    class Meta:
        verbose_name = "🧩 Разряд квалификации"
        verbose_name_plural = "🧩 Разряды квалификации"
        ordering = ['order', 'grade_number']
        unique_together = ['grade_number', 'label_ru']

    def __str__(self):
        return self.label_ru


class TrainingProfession(models.Model):
    """
    Профессия для обучения.

    УПРОЩЕНИЕ: Удалены поля assigned_name_ru/by, qualification_grade_default.
    Разряд теперь указывается в ProductionTraining.
    """
    name_ru_nominative = models.CharField(
        max_length=255,
        verbose_name="Профессия (рус, им.)"
    )
    name_ru_genitive = models.CharField(
        max_length=255,
        verbose_name="Профессия (рус, род.)"
    )
    name_by_nominative = models.CharField(
        max_length=255,
        blank=True,
        verbose_name="Профессия (бел, им.)"
    )
    name_by_genitive = models.CharField(
        max_length=255,
        blank=True,
        verbose_name="Профессия (бел, род.)"
    )
    is_active = models.BooleanField(
        default=True,
        verbose_name="Активна"
    )
    order = models.PositiveIntegerField(
        default=0,
        verbose_name="Порядок"
    )

    class Meta:
        verbose_name = "🧑‍🏭 Профессия обучения"
        verbose_name_plural = "🧑‍🏭 Профессии обучения"
        ordering = ['order', 'name_ru_nominative']
        unique_together = ['name_ru_nominative', 'name_ru_genitive']

    def __str__(self):
        return self.name_ru_nominative


# ============================================================================
# ПРОГРАММА ОБУЧЕНИЯ (1 модель - КАРДИНАЛЬНО УПРОЩЕНА)
# ============================================================================

class TrainingProgram(models.Model):
    """
    Программа обучения (шаблон).

    Структура часов соответствует плану обучения:
    - Профессиональный компонент (теория + практика)
    - Консультации
    - Квалификационный экзамен

    Распределение по неделям хранится в weeks_distribution.

    Примеры:
    - Переподготовка: 192 ч (5 недель: 40+40+40+40+32)
    - Подготовка: 320 ч (8 недель: 40+40+40+40+40+40+40+40)
    """
    name = models.CharField(
        max_length=255,
        verbose_name="Название программы"
    )
    training_type = models.ForeignKey(
        TrainingType,
        on_delete=models.PROTECT,
        related_name='programs',
        verbose_name="Тип обучения"
    )
    profession = models.ForeignKey(
        TrainingProfession,
        on_delete=models.PROTECT,
        related_name='programs',
        verbose_name="Профессия"
    )
    qualification_grade = models.ForeignKey(
        TrainingQualificationGrade,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='programs',
        verbose_name="Разряд"
    )

    # === ОСНОВНЫЕ ПОЛЯ ДЛЯ РАСЧЁТОВ ===
    total_hours = models.PositiveIntegerField(
        default=0,
        verbose_name="Всего часов",
        help_text="Общее количество часов программы"
    )
    practical_work_topic = models.TextField(
        blank=True,
        verbose_name="Тема пробной работы",
        help_text="Стандартная тема пробной работы для программы"
    )
    practical_work_hours = models.PositiveIntegerField(
        null=True,
        blank=True,
        verbose_name="Часов на пробную работу",
        help_text="Норматив часов на пробную работу"
    )
    weeks_distribution = models.JSONField(
        default=list,
        blank=True,
        verbose_name="Часы по неделям",
        help_text="Распределение часов: [40, 40, 40, 40, 32]"
    )

    # === ДОПОЛНИТЕЛЬНО ===
    diary_template = models.FileField(
        upload_to='document_templates/learning/',
        null=True,
        blank=True,
        verbose_name="Шаблон дневника (DOCX)"
    )
    description = models.TextField(
        blank=True,
        verbose_name="Описание"
    )
    is_active = models.BooleanField(
        default=True,
        verbose_name="Активна"
    )

    # === DEPRECATED: JSON-поля (для совместимости) ===
    content = models.JSONField(
        default=dict,
        blank=True,
        verbose_name="Содержание (deprecated)",
        help_text="Устаревшее поле. Используйте простые поля выше."
    )
    weekly_hours = models.JSONField(
        default=list,
        blank=True,
        verbose_name="Недельные часы (deprecated)",
        help_text="Устаревшее. Используйте weeks_distribution."
    )
    duration_days = models.PositiveIntegerField(
        default=0,
        verbose_name="Длительность (deprecated)"
    )

    class Meta:
        verbose_name = "📘 Программа обучения"
        verbose_name_plural = "📘 Программы обучения"
        ordering = ['training_type', 'profession', 'name']
        unique_together = ['name', 'training_type', 'profession']

    def __str__(self):
        return self.name

    def get_total_hours(self):
        """Получить общее количество часов."""
        if self.total_hours:
            return self.total_hours
        # Fallback: сумма по неделям
        weeks = self.get_weeks_distribution()
        if weeks:
            return sum(weeks)
        return self.content.get('total_hours', 0)

    def get_theory_hours(self):
        """Получить часы теории (из deprecated content)."""
        return self.content.get('theory_hours', 0)

    def get_practice_hours(self):
        """Получить часы практики (из deprecated content)."""
        return self.content.get('practice_hours', 0)

    def get_weeks_count(self):
        """Вычислить количество недель."""
        return len(self.get_weeks_distribution())

    def get_weeks_distribution(self):
        """Получить распределение часов по неделям."""
        return self.weeks_distribution or self.weekly_hours or []

    def get_sections(self):
        """Получить список разделов программы (для совместимости)."""
        return self.content.get('sections', [])

    def get_workdays_count(self):
        """Рассчитать количество рабочих дней (8 ч/день)."""
        weeks = self.get_weeks_distribution()
        if weeks:
            return sum(weeks) // 8
        return 0

    def save(self, *args, **kwargs):
        """Автозаполнение total_hours и синхронизация deprecated полей."""
        # Синхронизация weeks_distribution → weekly_hours (deprecated)
        if self.weeks_distribution and not self.weekly_hours:
            self.weekly_hours = self.weeks_distribution

        # Автоподсчёт total_hours из weeks_distribution
        if not self.total_hours:
            weeks = self.get_weeks_distribution()
            if weeks:
                self.total_hours = sum(weeks)

        super().save(*args, **kwargs)


# ============================================================================
# ОСНОВНАЯ МОДЕЛЬ ОБУЧЕНИЯ (1 модель - УПРОЩЕНА)
# ============================================================================

class ProductionTraining(models.Model):
    """
    Курс обучения на производстве.

    Общие данные курса:
    - Организация, подразделение, отдел
    - Программа обучения (тип, профессия, разряд)
    - Роли и комиссия
    - Место проведения
    """

    # === ОСНОВНЫЕ ДАННЫЕ ===
    organization = models.ForeignKey(
        'directory.Organization',
        on_delete=models.PROTECT,
        related_name='production_trainings',
        verbose_name="Организация"
    )
    subdivision = models.ForeignKey(
        'directory.StructuralSubdivision',
        on_delete=models.PROTECT,
        related_name='production_trainings',
        verbose_name="Подразделение",
        null=True,
        blank=True
    )
    department = models.ForeignKey(
        'directory.Department',
        on_delete=models.PROTECT,
        related_name='production_trainings',
        verbose_name="Отдел",
        null=True,
        blank=True
    )

    # === ПРОГРАММА ОБУЧЕНИЯ ===
    training_type = models.ForeignKey(
        TrainingType,
        on_delete=models.PROTECT,
        related_name='trainings',
        verbose_name="Тип обучения"
    )
    program = models.ForeignKey(
        TrainingProgram,
        on_delete=models.SET_NULL,
        related_name='trainings',
        null=True,
        blank=True,
        verbose_name="Программа"
    )
    profession = models.ForeignKey(
        TrainingProfession,
        on_delete=models.PROTECT,
        related_name='trainings',
        verbose_name="Профессия обучения"
    )
    qualification_grade = models.ForeignKey(
        TrainingQualificationGrade,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='trainings',
        verbose_name="Разряд"
    )

    # === РОЛИ ===
    instructor = models.ForeignKey(
        'directory.Employee',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='training_as_instructor',
        verbose_name="Инструктор производственного обучения"
    )
    responsible_person = models.ForeignKey(
        'directory.Employee',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='training_as_responsible',
        verbose_name="Ответственный за обучение"
    )
    theory_consultant = models.ForeignKey(
        'directory.Employee',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='training_as_consultant',
        verbose_name="Консультант теоретического обучения"
    )
    commission_chairman = models.ForeignKey(
        'directory.Employee',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='training_as_chairman',
        verbose_name="Руководитель производственного обучения"
    )
    commission_members = models.ManyToManyField(
        'directory.Employee',
        blank=True,
        related_name='training_as_member',
        verbose_name="Члены комиссии"
    )
    commission = models.ForeignKey(
        'directory.Commission',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='production_trainings',
        verbose_name="Квалификационная комиссия",
        limit_choices_to={'commission_type': 'qualification'}
    )

    # === МЕСТО ПРОВЕДЕНИЯ ===
    training_city_ru = models.CharField(
        max_length=255,
        blank=True,
        verbose_name="Место проведения (рус)"
    )
    training_city_by = models.CharField(
        max_length=255,
        blank=True,
        verbose_name="Место проведения (бел)"
    )

    # === МЕТАДАННЫЕ ===
    notes = models.TextField(
        blank=True,
        verbose_name="Примечания"
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Создано"
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        verbose_name="Обновлено"
    )

    class Meta:
        verbose_name = "📘 Курс обучения"
        verbose_name_plural = "📘 Курсы обучения"
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['organization'], name='pt_org_idx'),
        ]

    def __str__(self):
        grade = f" ({self.qualification_grade.label_ru})" if self.qualification_grade else ""
        return f"{self.training_type.name_ru} — {self.profession.name_ru_nominative}{grade}"

    def clean(self):
        """Валидация полей."""
        super().clean()

        if self.department and self.department.organization != self.organization:
            raise ValidationError({
                'department': 'Отдел должен принадлежать выбранной организации'
            })
        if self.subdivision and self.subdivision.organization != self.organization:
            raise ValidationError({
                'subdivision': 'Подразделение должно принадлежать выбранной организации'
            })

    def get_instructor_name(self):
        """ФИО инструктора."""
        return self.instructor.full_name_nominative if self.instructor else ''

    def get_consultant_name(self):
        """ФИО консультанта."""
        return self.theory_consultant.full_name_nominative if self.theory_consultant else ''

    def get_chairman_name(self):
        """ФИО председателя комиссии."""
        return self.commission_chairman.full_name_nominative if self.commission_chairman else ''

    def get_commission_members_list(self):
        """Список членов комиссии через запятую."""
        return ', '.join([
            member.full_name_nominative
            for member in self.commission_members.all()
        ])

    def get_assignments_count(self):
        """Количество назначенных сотрудников."""
        return self.assignments.count()

    def get_active_assignments_count(self):
        """Количество сотрудников в процессе обучения."""
        from django.utils import timezone
        today = timezone.localdate()
        return self.assignments.filter(
            start_date__lte=today,
            end_date__gte=today
        ).count()


# ============================================================================
# НАЗНАЧЕНИЕ СОТРУДНИКА НА ОБУЧЕНИЕ
# ============================================================================

class TrainingAssignment(models.Model):
    """
    Назначение сотрудника на курс обучения.

    Содержит индивидуальные данные:
    - Сотрудник и его текущая должность
    - Даты обучения (индивидуальные для каждого)
    - Оценки за экзамен и пробную работу
    - Документы (номера протоколов, удостоверений)
    """

    # === СВЯЗИ ===
    training = models.ForeignKey(
        ProductionTraining,
        on_delete=models.CASCADE,
        related_name='assignments',
        verbose_name="Курс обучения"
    )
    employee = models.ForeignKey(
        'directory.Employee',
        on_delete=models.PROTECT,
        related_name='training_assignments',
        verbose_name="Сотрудник"
    )

    # === ДОПОЛНИТЕЛЬНЫЕ ДАННЫЕ СОТРУДНИКА ===
    current_position = models.ForeignKey(
        'directory.Position',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='training_assignments',
        verbose_name="Профессия на предприятии"
    )
    prior_qualification = models.TextField(
        blank=True,
        verbose_name="Имеющаяся квалификация",
        help_text="Например: автослесарь, А№0584083 от 09.02.2009"
    )
    workplace = models.CharField(
        max_length=255,
        blank=True,
        verbose_name="Место работы",
        help_text="Например: склад, цех №1"
    )

    # === ДАТЫ ===
    start_date = models.DateField(
        null=True,
        blank=True,
        verbose_name="Дата начала обучения"
    )
    end_date = models.DateField(
        null=True,
        blank=True,
        verbose_name="Дата окончания обучения"
    )

    # === ЭКЗАМЕН ===
    exam_date = models.DateField(
        null=True,
        blank=True,
        verbose_name="Дата экзамена"
    )
    theory_score = models.CharField(
        max_length=50,
        blank=True,
        verbose_name="Отметка за теоретический экзамен"
    )
    exam_score = models.CharField(
        max_length=50,
        blank=True,
        verbose_name="Отметка за экзамен"
    )

    # === ПРОБНАЯ РАБОТА ===
    practical_date = models.DateField(
        null=True,
        blank=True,
        verbose_name="Дата пробной работы"
    )
    practical_score = models.CharField(
        max_length=50,
        blank=True,
        verbose_name="Отметка за пробную работу"
    )
    practical_work_topic = models.TextField(
        blank=True,
        verbose_name="Тема пробной работы"
    )

    # === ДОКУМЕНТЫ ===
    registration_number = models.CharField(
        max_length=100,
        blank=True,
        verbose_name="Регистрационный номер"
    )
    protocol_number = models.CharField(
        max_length=100,
        blank=True,
        verbose_name="Номер протокола"
    )
    protocol_date = models.DateField(
        null=True,
        blank=True,
        verbose_name="Дата протокола"
    )
    issue_date = models.DateField(
        null=True,
        blank=True,
        verbose_name="Дата выдачи удостоверения"
    )

    # === ЧАСЫ (опционально) ===
    planned_hours = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name="План часов"
    )
    actual_hours = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name="Факт часов"
    )

    # === МЕТАДАННЫЕ ===
    notes = models.TextField(
        blank=True,
        verbose_name="Примечания"
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Создано"
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        verbose_name="Обновлено"
    )

    class Meta:
        verbose_name = "👤 Сотрудник на обучении"
        verbose_name_plural = "👥 Сотрудники на обучении"
        ordering = ['-start_date', 'employee__full_name_nominative']
        indexes = [
            models.Index(fields=['training', 'employee'], name='ta_training_emp_idx'),
            models.Index(fields=['start_date', 'end_date'], name='ta_dates_idx'),
        ]
        unique_together = ['training', 'employee']

    def __str__(self):
        return f"{self.employee.full_name_nominative} — {self.training}"

    def clean(self):
        """Валидация полей."""
        super().clean()

        # Проверка дат
        if self.start_date and self.end_date:
            if self.start_date > self.end_date:
                raise ValidationError({
                    'end_date': 'Дата окончания не может быть раньше даты начала'
                })

    def save(self, *args, **kwargs):
        """Автоподстановка дат при установке start_date."""
        if not self.current_position_id and self.employee_id:
            self.current_position = self.employee.position
        if not self.practical_work_topic:
            program = getattr(self.training, 'program', None)
            program_topic = getattr(program, 'practical_work_topic', '') if program else ''
            if program_topic:
                self.practical_work_topic = program_topic
        if self.planned_hours is None:
            program = getattr(self.training, 'program', None)
            program_hours = getattr(program, 'practical_work_hours', None) if program else None
            if program_hours is not None:
                self.planned_hours = program_hours

        if self.start_date:
            weekly_hours = self._resolve_weekly_hours()
            work_schedule = self._resolve_work_schedule()
            schedule_start = self._resolve_schedule_start(work_schedule)

            if weekly_hours:
                dates = schedule.compute_all_dates(
                    self.start_date,
                    weekly_hours,
                    work_schedule=work_schedule,
                    schedule_start=schedule_start,
                )

                if not self.end_date:
                    self.end_date = dates['end_date']
                if not self.exam_date:
                    self.exam_date = dates['exam_date']
                if not self.practical_date:
                    self.practical_date = dates['practical_date']
                if not self.protocol_date:
                    self.protocol_date = dates['protocol_date']

        super().save(*args, **kwargs)

    def recalculate_dates(self, force=False):
        """Пересчитать все даты на основе start_date и программы."""
        if not self.start_date:
            return

        if not force and self.end_date:
            return

        weekly_hours = self._resolve_weekly_hours()
        work_schedule = self._resolve_work_schedule()
        schedule_start = self._resolve_schedule_start(work_schedule)

        if not weekly_hours:
            return

        dates = schedule.compute_all_dates(
            self.start_date,
            weekly_hours,
            work_schedule=work_schedule,
            schedule_start=schedule_start,
        )

        if force or not self.end_date:
            self.end_date = dates['end_date']
        if force or not self.exam_date:
            self.exam_date = dates['exam_date']
        if force or not self.practical_date:
            self.practical_date = dates['practical_date']
        if force or not self.protocol_date:
            self.protocol_date = dates['protocol_date']

    # === ВЫЧИСЛЯЕМЫЕ СВОЙСТВА (из курса) ===

    @property
    def organization(self):
        """Организация (из курса обучения)."""
        return self.training.organization if self.training else None

    @property
    def program(self):
        """Программа обучения (из курса)."""
        return self.training.program if self.training else None

    @property
    def profession(self):
        """Профессия обучения (из курса)."""
        return self.training.profession if self.training else None

    @property
    def training_type(self):
        """Тип обучения (из курса)."""
        return self.training.training_type if self.training else None

    @property
    def qualification_grade(self):
        """Разряд (из курса)."""
        return self.training.qualification_grade if self.training else None

    @property
    def instructor(self):
        """Инструктор (из курса)."""
        return self.training.instructor if self.training else None

    @property
    def responsible_person(self):
        """Ответственный за обучение (из курса)."""
        return self.training.responsible_person if self.training else None

    @property
    def theory_consultant(self):
        """Консультант по теории (из курса)."""
        return self.training.theory_consultant if self.training else None

    @property
    def commission_chairman(self):
        """Председатель комиссии (из курса)."""
        return self.training.commission_chairman if self.training else None

    @property
    def commission(self):
        """Квалификационная комиссия (из курса)."""
        return self.training.commission if self.training else None

    @property
    def commission_members(self):
        """Члены комиссии (из курса)."""
        return self.training.commission_members if self.training else None

    @property
    def training_city_ru(self):
        """Место проведения рус (из курса)."""
        return self.training.training_city_ru if self.training else ''

    @property
    def training_city_by(self):
        """Место проведения бел (из курса)."""
        return self.training.training_city_by if self.training else ''

    # === ВЫЧИСЛЯЕМЫЕ МЕТОДЫ ===

    def get_status(self):
        """Вычисляемый статус на основе дат."""
        from django.utils import timezone
        today = timezone.localdate()

        if not self.start_date:
            return 'draft'
        if self.start_date > today:
            return 'scheduled'
        if self.end_date and self.end_date < today:
            return 'completed'
        return 'active'

    def get_status_display(self):
        """Отображение статуса."""
        status_labels = {
            'draft': 'Черновик',
            'scheduled': 'Запланировано',
            'active': 'В процессе',
            'completed': 'Завершено',
        }
        return status_labels.get(self.get_status(), 'Неизвестно')

    def get_days_left(self):
        """Количество дней до окончания обучения."""
        if not self.end_date:
            return None
        from django.utils import timezone
        today = timezone.localdate()
        return (self.end_date - today).days

    # === МЕТОДЫ ДЛЯ ГЕНЕРАЦИИ ДОКУМЕНТОВ ===

    def get_exam_date_formatted(self, language='ru'):
        """Дата экзамена в формате: '5 января 2025 г.'"""
        if not self.exam_date:
            return ''
        return self._format_date(self.exam_date, language)

    def get_practical_date_formatted(self, language='ru'):
        """Дата практики в формате: '5 января 2025 г.'"""
        if not self.practical_date:
            return ''
        return self._format_date(self.practical_date, language)

    def get_period_str(self, language='ru'):
        """Период обучения в формате: 'с 01.02.2025 по 15.03.2025'."""
        if not self.start_date or not self.end_date:
            return ''
        start_fmt = self.start_date.strftime('%d.%m.%Y')
        end_fmt = self.end_date.strftime('%d.%m.%Y')
        if language == 'ru':
            return f"с {start_fmt} по {end_fmt}"
        else:
            return f"з {start_fmt} па {end_fmt}"

    def get_theory_dates(self):
        """Даты теоретических консультаций (2 даты)."""
        if not self.start_date:
            return []
        work_schedule = self._resolve_work_schedule()
        schedule_start = self._resolve_schedule_start(work_schedule)
        return schedule.compute_theory_dates(
            self.start_date,
            work_schedule=work_schedule,
            schedule_start=schedule_start,
        )

    def get_diary_entries(self):
        """Записи дневника обучения."""
        if not self.start_date:
            return []
        program_content = None
        if self.program and self.program.content:
            program_content = self.program.content
        work_schedule = self._resolve_work_schedule()
        schedule_start = self._resolve_schedule_start(work_schedule)
        return schedule.build_diary_entries(
            self.start_date,
            getattr(self.training_type, 'code', None) if self.training_type else None,
            program_content=program_content,
            weekly_hours_override=self._resolve_weekly_hours(),
            work_schedule=work_schedule,
            schedule_start=schedule_start,
        )

    def get_diary_template_path(self):
        """Путь к DOCX-шаблону дневника."""
        if self.program and self.program.diary_template:
            return self.program.diary_template.path

        base = Path(settings.MEDIA_ROOT) / 'document_templates' / 'learning'
        if self.training_type and getattr(self.training_type, 'code', '').lower() == 'retraining':
            candidate = base / '4.diary_perepodgotovka_voditel_pogruzchika.docx'
        else:
            candidate = base / '4.1.diary_podgotovka_voditel_pogruzchika.docx'

        return str(candidate) if candidate.exists() else None

    # === ВНУТРЕННИЕ МЕТОДЫ ===

    def _resolve_weekly_hours(self):
        """Отдать недельный план из программы курса."""
        training_type = getattr(self, 'training_type', None)
        program_type = getattr(self.program, 'training_type', None) if self.program else None

        if self.program:
            weeks = self.program.get_weeks_distribution()
            if weeks:
                # Если типы курса и программы не совпадают, предпочитаем тип курса.
                if training_type and program_type and training_type != program_type:
                    weeks = None
                else:
                    return weeks

        weeks = schedule.get_weekly_hours(
            getattr(training_type, 'code', None) if training_type else None
        )
        if not weeks and training_type:
            weeks = schedule.get_weekly_hours(getattr(training_type, 'name_ru', None))
        if not weeks and program_type:
            weeks = schedule.get_weekly_hours(getattr(program_type, 'code', None))
        if not weeks and program_type:
            weeks = schedule.get_weekly_hours(getattr(program_type, 'name_ru', None))
        return weeks

    def _resolve_work_schedule(self):
        """Получить график работы сотрудника."""
        if self.employee and getattr(self.employee, 'work_schedule', None):
            return self.employee.work_schedule
        return schedule.DEFAULT_WORK_SCHEDULE

    def _resolve_schedule_start(self, work_schedule):
        """Определить опорную дату цикла для графика 2/2."""
        if work_schedule == '2/2' and self.employee:
            return self.employee.start_date or self.employee.hire_date or self.start_date
        return self.start_date

    def _format_date(self, date, language='ru'):
        """Форматировать дату с названием месяца."""
        if not date:
            return ''

        if language == 'ru':
            months = [
                '', 'января', 'февраля', 'марта', 'апреля', 'мая', 'июня',
                'июля', 'августа', 'сентября', 'октября', 'ноября', 'декабря'
            ]
        else:  # by
            months = [
                '', 'студзеня', 'лютага', 'сакавіка', 'красавіка', 'мая', 'чэрвеня',
                'ліпеня', 'жніўня', 'верасня', 'кастрычніка', 'лістапада', 'снежня'
            ]

        return f"{date.day} {months[date.month]} {date.year} г."


# ============================================================================
# ИТОГО: 6 МОДЕЛЕЙ
# ============================================================================

"""
СТРУКТУРА:
1. TrainingType — типы обучения (подготовка, переподготовка)
2. TrainingQualificationGrade — разряды (2, 3, 4, 5, 6)
3. TrainingProfession — профессии
4. TrainingProgram — программы обучения
5. ProductionTraining — курсы обучения (общие данные)
6. TrainingAssignment — назначения сотрудников (индивидуальные данные)

СВЯЗИ:
ProductionTraining (1) ←→ (N) TrainingAssignment ←→ (1) Employee
"""
