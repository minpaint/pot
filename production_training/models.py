# -*- coding: utf-8 -*-
"""
Упрощённые модели для модуля "Обучение на производстве"

Изменения по сравнению с production_training/models.py:
- 14 моделей → 5 моделей (-64%)
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
    Карточка обучения сотрудника на производстве.

    УПРОЩЕНИЯ:
    1. Роли (инструктор, консультант, комиссия) — прямые поля вместо
       отдельных моделей TrainingRoleType + TrainingRoleAssignment
    2. Удалено поле schedule_rule (YAGNI)
    3. Добавлены поля для форм собственности организации
    4. Добавлены недостающие поля из Excel (prior_qualification, workplace)
    """

    STATUS_CHOICES = [
        ('draft', 'Черновик'),
        ('active', 'В процессе'),
        ('completed', 'Завершено'),
    ]

    # === ОСНОВНЫЕ ДАННЫЕ ===
    employee = models.ForeignKey(
        'directory.Employee',
        on_delete=models.PROTECT,
        related_name='production_trainings',
        verbose_name="Сотрудник",
        null=True,
        blank=True,
    )
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

    # === ДОПОЛНИТЕЛЬНЫЕ ДАННЫЕ СОТРУДНИКА ===
    current_position = models.ForeignKey(
        'directory.Position',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='production_trainings',
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

    # === РОЛИ (УПРОЩЕНИЕ: прямые поля вместо отдельной модели) ===
    instructor = models.ForeignKey(
        'directory.Employee',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='training_as_instructor',
        verbose_name="Инструктор производственного обучения"
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
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='draft',
        verbose_name="Статус"
    )
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
        verbose_name = "📒 Обучение на производстве"
        verbose_name_plural = "📒 Обучение на производстве"
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['organization', 'employee'], name='pt_org_emp_idx'),
            models.Index(fields=['start_date', 'end_date'], name='pt_dates_idx'),
            models.Index(fields=['status'], name='pt_status_idx'),
        ]

    def __str__(self):
        employee_name = self.employee.full_name_nominative if self.employee else "Без сотрудника"
        return f"{employee_name} — {self.profession.name_ru_nominative}"

    def clean(self):
        """Валидация полей."""
        super().clean()

        # Проверка дат
        if self.start_date and self.end_date:
            if self.start_date > self.end_date:
                raise ValidationError({
                    'end_date': 'Дата окончания не может быть раньше даты начала'
                })

        # Проверка иерархии организации
        if self.department:
            if self.department.organization != self.organization:
                raise ValidationError({
                    'department': 'Отдел должен принадлежать выбранной организации'
                })
        if self.subdivision:
            if self.subdivision.organization != self.organization:
                raise ValidationError({
                    'subdivision': 'Подразделение должно принадлежать выбранной организации'
                })

    def save(self, *args, **kwargs):
        """
        Автоподстановка дат при установке start_date:
        - end_date: по недельному плану (количество рабочих дней)
        - exam_date: = end_date (экзамен в последний день обучения)
        - practical_date: = exam_date - 1 рабочий день (пробная работа за день до экзамена)
        - protocol_date: = practical_date + 1 день (= exam_date)
        """
        weekly_hours = self._resolve_weekly_hours()
        work_schedule = self._resolve_work_schedule()
        schedule_start = self._resolve_schedule_start(work_schedule)

        # Полный пересчёт всех дат при установке start_date
        if self.start_date and weekly_hours:
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

        # Если practical_date задан вручную, пересчитать protocol_date
        elif self.practical_date and not self.protocol_date:
            self.protocol_date = schedule.compute_protocol_date(self.practical_date)

        super().save(*args, **kwargs)

    def recalculate_dates(self, force: bool = False):
        """
        Пересчитать все даты по дате начала.

        Args:
            force: если True, перезаписать даже уже заполненные даты
        """
        weekly_hours = self._resolve_weekly_hours()
        work_schedule = self._resolve_work_schedule()
        schedule_start = self._resolve_schedule_start(work_schedule)
        if not self.start_date or not weekly_hours:
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

    # === МЕТОДЫ ДЛЯ ГЕНЕРАЦИИ ДОКУМЕНТОВ ===

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

    def get_period(self):
        """Кортеж (start_date, end_date) с учетом автоподстановки."""
        weekly_hours = self._resolve_weekly_hours()
        work_schedule = self._resolve_work_schedule()
        schedule_start = self._resolve_schedule_start(work_schedule)
        if self.start_date and weekly_hours:
            end_date = self.end_date or schedule.compute_end_date(
                self.start_date,
                weekly_hours,
                work_schedule=work_schedule,
                schedule_start=schedule_start,
            )
            return self.start_date, end_date
        return self.start_date, self.end_date

    def get_period_str(self, language='ru'):
        """Строка периода 'с 01.02.2025 по 15.03.2025'."""
        start, end = self.get_period()
        if not start or not end:
            return ''
        fmt = "%d.%m.%Y"
        prefix = "с" if language == 'ru' else "з"
        return f"{prefix} {start.strftime(fmt)} по {end.strftime(fmt)}"

    def get_theory_dates(self):
        """
        Две рабочие даты для карточки теории (детерминированно вместо RANDBETWEEN).
        """
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
        """
        Автогенерация дневника:
        - рабочие дни по недельному плану (8 ч/день);
        - темы последовательно из program.content (если есть).
        """
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

    def _resolve_weekly_hours(self):
        """
        Отдать недельный план: приоритет у программы, иначе дефолт по типу обучения.

        Возвращает список часов по неделям, например: [40, 40, 40, 40, 32]
        """
        if self.program:
            weeks = self.program.get_weeks_distribution()
            if weeks:
                return weeks
        return schedule.get_weekly_hours(
            getattr(self.training_type, 'code', None) if self.training_type else None
        )

    def _resolve_work_schedule(self):
        """Получить график работы сотрудника для расчета дат."""
        if self.employee and getattr(self.employee, 'work_schedule', None):
            return self.employee.work_schedule
        return schedule.DEFAULT_WORK_SCHEDULE

    def _resolve_schedule_start(self, work_schedule):
        """Определить опорную дату цикла для графика 2/2."""
        if work_schedule == '2/2' and self.employee:
            return self.employee.start_date or self.employee.hire_date or self.start_date
        return self.start_date

    def get_diary_template_path(self):
        """
        Вернуть путь к DOCX-шаблону дневника:
        1) Если у программы указан свой шаблон — используем его.
        2) Иначе — дефолт по типу обучения (подготовка/переподготовка).
        """
        if self.program and self.program.diary_template:
            return self.program.diary_template.path

        base = Path(settings.MEDIA_ROOT) / 'document_templates' / 'learning'
        if self.training_type and getattr(self.training_type, 'code', '').lower() == 'retraining':
            # Переподготовка
            candidate = base / '4.diary_perepodgotovka_voditel_pogruzchika.docx'
        else:
            # Подготовка
            candidate = base / '4.1.diary_podgotovka_voditel_pogruzchika.docx'

        return str(candidate) if candidate.exists() else None

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
# ИТОГО: 5 МОДЕЛЕЙ вместо 14 (-64%)
# ============================================================================

"""
УДАЛЕНО (8 моделей):
- TrainingProgramSection → JSON в TrainingProgram.content
- TrainingProgramEntry → JSON в TrainingProgram.content
- TrainingEntryType → choices в коде ('theory', 'practice', 'consultation')
- TrainingScheduleRule → YAGNI (не используется)
- TrainingRoleType → choices в коде (instructor, consultant, chairman, member)
- TrainingRoleAssignment → прямые поля в ProductionTraining
- TrainingDiaryEntry → переделать или удалить (пока удалено)
- TrainingTheoryConsultation → объединить с дневником или удалить (пока удалено)

ОСТАВЛЕНО (5 моделей):
1. TrainingType — типы обучения (подготовка, переподготовка)
2. TrainingQualificationGrade — разряды (2, 3, 4, 5, 6)
3. TrainingProfession — профессии
4. TrainingProgram — программы обучения (с JSON вместо 3 моделей)
5. ProductionTraining — карточки обучения (с прямыми полями ролей)
"""
