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

from django.db import models
from django.core.exceptions import ValidationError


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

    УПРОЩЕНИЕ: Содержание программы хранится в JSON вместо отдельных моделей
    TrainingProgramSection + TrainingProgramEntry + TrainingEntryType.

    Структура JSON:
    {
      "sections": [
        {
          "title": "Раздел 1. Теоретическое обучение",
          "entries": [
            {"type": "theory", "topic": "Тема 1", "hours": 4},
            {"type": "theory", "topic": "Тема 2", "hours": 6}
          ]
        },
        {
          "title": "Раздел 2. Производственное обучение",
          "entries": [
            {"type": "practice", "topic": "Практика 1", "hours": 40}
          ]
        }
      ],
      "total_hours": 50,
      "theory_hours": 10,
      "practice_hours": 40
    }
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

    # === ГЛАВНОЕ УПРОЩЕНИЕ: JSON вместо 3 моделей ===
    content = models.JSONField(
        default=dict,
        blank=True,
        verbose_name="Содержание программы",
        help_text="JSON с разделами, темами и часами"
    )

    duration_days = models.PositiveIntegerField(
        default=0,
        verbose_name="Длительность (дни)"
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
    description = models.TextField(
        blank=True,
        verbose_name="Описание"
    )
    is_active = models.BooleanField(
        default=True,
        verbose_name="Активна"
    )

    class Meta:
        verbose_name = "📘 Программа обучения"
        verbose_name_plural = "📘 Программы обучения"
        ordering = ['training_type', 'profession', 'name']
        unique_together = ['name', 'training_type', 'profession']

    def __str__(self):
        return self.name

    def get_total_hours(self):
        """Получить общее количество часов из JSON."""
        return self.content.get('total_hours', 0)

    def get_theory_hours(self):
        """Получить часы теории из JSON."""
        return self.content.get('theory_hours', 0)

    def get_practice_hours(self):
        """Получить часы практики из JSON."""
        return self.content.get('practice_hours', 0)

    def get_sections(self):
        """Получить список разделов программы."""
        return self.content.get('sections', [])

    def calculate_hours(self):
        """
        Пересчитать общее количество часов из разделов.
        Полезно после импорта или редактирования JSON.
        """
        total = 0
        theory = 0
        practice = 0

        for section in self.get_sections():
            for entry in section.get('entries', []):
                hours = float(entry.get('hours', 0))
                total += hours

                entry_type = entry.get('type', 'theory')
                if entry_type == 'theory':
                    theory += hours
                elif entry_type == 'practice':
                    practice += hours

        self.content['total_hours'] = total
        self.content['theory_hours'] = theory
        self.content['practice_hours'] = practice


# ============================================================================
# ОСНОВНАЯ МОДЕЛЬ ОБУЧЕНИЯ (Курс/программа)
# ============================================================================

class ProductionTraining(models.Model):
    """
    Курс обучения на производстве.

    Это общая программа обучения, к которой могут быть привязаны
    несколько сотрудников через TrainingAssignment.

    Содержит:
    - Организационную структуру (организация, подразделение, отдел)
    - Программу обучения (тип, профессия, разряд)
    - Роли (инструктор, консультант, комиссия)
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

    # === РОЛИ (общие для всего курса) ===
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
        verbose_name="Консультант по теории"
    )
    commission_chairman = models.ForeignKey(
        'directory.Employee',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='training_as_chairman',
        verbose_name="Председатель квалификационной комиссии"
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
        verbose_name="Квалификационная комиссия"
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
        grade_str = f" ({self.qualification_grade.label_ru})" if self.qualification_grade else ""
        return f"{self.profession.name_ru_nominative}{grade_str}"

    def clean(self):
        """Валидация полей."""
        super().clean()

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

    # === ВЫЧИСЛЯЕМЫЕ СВОЙСТВА ===

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
    def training_city_ru(self):
        """Место проведения рус (из курса)."""
        return self.training.training_city_ru if self.training else ''

    @property
    def training_city_by(self):
        """Место проведения бел (из курса)."""
        return self.training.training_city_by if self.training else ''

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
        if not self.start_date or not self.program:
            return []

        from . import schedule
        weeks = self.program.get_weeks_distribution() or [40]

        work_schedule = '5/2'
        schedule_start = None
        if self.employee:
            work_schedule = self.employee.work_schedule or '5/2'
            schedule_start = self.employee.start_date or self.employee.hire_date

        dates = schedule.compute_all_dates(
            self.start_date,
            weeks,
            work_schedule=work_schedule,
            schedule_start=schedule_start,
        )

        return dates.get('theory_dates', [])

    def get_diary_entries(self):
        """Записи дневника обучения."""
        if not self.start_date or not self.program:
            return []

        from . import schedule
        weeks = self.program.get_weeks_distribution() or [40]

        work_schedule = '5/2'
        schedule_start = None
        if self.employee:
            work_schedule = self.employee.work_schedule or '5/2'
            schedule_start = self.employee.start_date or self.employee.hire_date

        dates = schedule.compute_all_dates(
            self.start_date,
            weeks,
            work_schedule=work_schedule,
            schedule_start=schedule_start,
        )

        return dates.get('diary_entries', [])

    def recalculate_dates(self, force=False):
        """Пересчитать все даты на основе start_date и программы."""
        if not self.start_date:
            return

        if not force and self.end_date:
            return

        from . import schedule

        weeks = [40]
        if self.program:
            weeks = self.program.get_weeks_distribution() or [40]

        work_schedule = '5/2'
        schedule_start = None
        if self.employee:
            work_schedule = self.employee.work_schedule or '5/2'
            schedule_start = self.employee.start_date or self.employee.hire_date

        dates = schedule.compute_all_dates(
            self.start_date,
            weeks,
            work_schedule=work_schedule,
            schedule_start=schedule_start,
        )

        self.end_date = dates.get('end_date')
        self.exam_date = dates.get('exam_date')
        self.practical_date = dates.get('practical_date')
        self.protocol_date = dates.get('protocol_date')

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
4. TrainingProgram — программы обучения (с JSON вместо 3 моделей)
5. ProductionTraining — курсы обучения (общие данные: роли, комиссия, место)
6. TrainingAssignment — назначения сотрудников (индивидуальные: даты, оценки)

СВЯЗИ:
ProductionTraining (1) ←→ (N) TrainingAssignment ←→ (1) Employee
- Один курс может иметь много назначенных сотрудников
- У каждого сотрудника свои даты, оценки, документы
"""
