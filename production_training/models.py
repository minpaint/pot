# -*- coding: utf-8 -*-
"""
Упрощённые модели для модуля "Обучение на производстве"

Изменения по сравнению с production_training/models.py:
- 14 моделей → 6 моделей (-57%)
- TrainingProgram: содержание программы в JSON вместо Section+Entry
- ProductionTraining: роли как прямые поля вместо отдельной модели
- Удалены: TrainingEntryType, TrainingScheduleRule, TrainingProgramSection,
  TrainingProgramEntry, TrainingRoleType, TrainingRoleAssignment,
  TrainingDiaryEntry, TrainingTheoryConsultation
"""

from django.db import models
from django.core.exceptions import ValidationError


# ============================================================================
# СПРАВОЧНИКИ (4 модели - БЕЗ ИЗМЕНЕНИЙ)
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


class EducationLevel(models.Model):
    """
    Уровень образования: среднее, среднее специальное, высшее.

    БЕЗ ИЗМЕНЕНИЙ.
    """
    name_ru = models.CharField(
        max_length=255,
        unique=True,
        verbose_name="Образование (рус)"
    )
    name_by = models.CharField(
        max_length=255,
        blank=True,
        verbose_name="Образование (бел)"
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
        verbose_name = "🎓 Уровень образования"
        verbose_name_plural = "🎓 Уровни образования"
        ordering = ['order', 'name_ru']

    def __str__(self):
        return self.name_ru


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
        verbose_name="Сотрудник"
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
    education_level = models.ForeignKey(
        EducationLevel,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='trainings',
        verbose_name="Образование"
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
        return f"{self.employee.full_name_nominative} — {self.profession.name_ru_nominative}"

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
# ИТОГО: 6 МОДЕЛЕЙ вместо 14 (-57%)
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

ОСТАВЛЕНО (6 моделей):
1. TrainingType — типы обучения (подготовка, переподготовка)
2. TrainingQualificationGrade — разряды (2, 3, 4, 5, 6)
3. TrainingProfession — профессии
4. EducationLevel — уровни образования
5. TrainingProgram — программы обучения (с JSON вместо 3 моделей)
6. ProductionTraining — карточки обучения (с прямыми полями ролей)
"""
