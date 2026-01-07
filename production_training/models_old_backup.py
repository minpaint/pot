from django.db import models


class TrainingType(models.Model):
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
    assigned_name_ru = models.CharField(
        max_length=255,
        blank=True,
        verbose_name="Присвоенная профессия (рус)",
        help_text="Если пусто, используется значение "
                  "Профессия (рус, им.)"
    )
    assigned_name_by = models.CharField(
        max_length=255,
        blank=True,
        verbose_name="Присвоенная профессия (бел)",
        help_text="Если пусто, используется значение "
                  "Профессия (бел, им.)"
    )
    qualification_grade_default = models.ForeignKey(
        'TrainingQualificationGrade',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name="Разряд по умолчанию"
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

    def get_assigned_name_ru(self):
        return self.assigned_name_ru or self.name_ru_nominative

    def get_assigned_name_by(self):
        return self.assigned_name_by or self.name_by_nominative


class EducationLevel(models.Model):
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


class TrainingProgram(models.Model):
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
    order = models.PositiveIntegerField(
        default=0,
        verbose_name="Порядок"
    )

    class Meta:
        verbose_name = "📘 Программа обучения"
        verbose_name_plural = "📘 Программы обучения"
        ordering = ['order', 'name']
        unique_together = ['name', 'training_type', 'profession']

    def __str__(self):
        return self.name


class TrainingProgramSection(models.Model):
    program = models.ForeignKey(
        TrainingProgram,
        on_delete=models.CASCADE,
        related_name='sections',
        verbose_name="Программа"
    )
    title = models.CharField(
        max_length=255,
        verbose_name="Название раздела"
    )
    order = models.PositiveIntegerField(
        default=0,
        verbose_name="Порядок"
    )

    class Meta:
        verbose_name = "📗 Раздел программы"
        verbose_name_plural = "📗 Разделы программы"
        ordering = ['order', 'title']
        unique_together = ['program', 'title']

    def __str__(self):
        return f"{self.program.name}: {self.title}"


class TrainingEntryType(models.Model):
    code = models.CharField(
        max_length=50,
        unique=True,
        verbose_name="Код типа записи"
    )
    name = models.CharField(
        max_length=255,
        verbose_name="Название"
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
        verbose_name = "🧾 Тип записи программы"
        verbose_name_plural = "🧾 Типы записей программы"
        ordering = ['order', 'name']

    def __str__(self):
        return self.name


class TrainingProgramEntry(models.Model):
    section = models.ForeignKey(
        TrainingProgramSection,
        on_delete=models.CASCADE,
        related_name='entries',
        verbose_name="Раздел"
    )
    entry_type = models.ForeignKey(
        TrainingEntryType,
        on_delete=models.PROTECT,
        related_name='program_entries',
        verbose_name="Тип записи"
    )
    topic = models.TextField(
        verbose_name="Тема"
    )
    hours = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        default=0,
        verbose_name="Часы"
    )
    order = models.PositiveIntegerField(
        default=0,
        verbose_name="Порядок"
    )

    class Meta:
        verbose_name = "📄 Пункт программы"
        verbose_name_plural = "📄 Пункты программы"
        ordering = ['order', 'topic']

    def __str__(self):
        return self.topic


class TrainingScheduleRule(models.Model):
    name = models.CharField(
        max_length=255,
        verbose_name="Название правила"
    )
    start_offset_days = models.IntegerField(
        default=0,
        verbose_name="Смещение старта (дни)"
    )
    pattern_days = models.JSONField(
        default=list,
        verbose_name="Шаги по дням",
        help_text="Список шагов (например: [1,3,1,3])."
    )
    use_workdays = models.BooleanField(
        default=False,
        verbose_name="Только рабочие дни"
    )
    is_active = models.BooleanField(
        default=True,
        verbose_name="Активно"
    )

    class Meta:
        verbose_name = "📅 Правило расписания"
        verbose_name_plural = "📅 Правила расписания"
        ordering = ['name']

    def __str__(self):
        return self.name


class TrainingRoleType(models.Model):
    code = models.CharField(
        max_length=50,
        unique=True,
        verbose_name="Код роли"
    )
    name = models.CharField(
        max_length=255,
        verbose_name="Название роли"
    )
    name_by = models.CharField(
        max_length=255,
        blank=True,
        verbose_name="Название роли (бел)"
    )
    description = models.TextField(
        blank=True,
        verbose_name="Описание"
    )
    is_required = models.BooleanField(
        default=False,
        verbose_name="Обязательна"
    )
    is_multi = models.BooleanField(
        default=False,
        verbose_name="Допускается несколько"
    )
    order = models.PositiveIntegerField(
        default=0,
        verbose_name="Порядок"
    )
    is_active = models.BooleanField(
        default=True,
        verbose_name="Активна"
    )

    class Meta:
        verbose_name = "👤 Роль обучения"
        verbose_name_plural = "👤 Роли обучения"
        ordering = ['order', 'name']

    def __str__(self):
        return self.name


class ProductionTraining(models.Model):
    STATUS_CHOICES = [
        ('draft', 'Черновик'),
        ('active', 'В процессе'),
        ('completed', 'Завершено'),
    ]

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
    schedule_rule = models.ForeignKey(
        TrainingScheduleRule,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='trainings',
        verbose_name="Правило расписания"
    )
    profession = models.ForeignKey(
        TrainingProfession,
        on_delete=models.PROTECT,
        related_name='trainings',
        verbose_name="Профессия обучения"
    )
    current_position = models.ForeignKey(
        'directory.Position',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='production_trainings',
        verbose_name="Профессия на предприятии"
    )
    qualification_grade = models.ForeignKey(
        TrainingQualificationGrade,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='trainings',
        verbose_name="Разряд"
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
        verbose_name="Имеющаяся квалификация"
    )
    start_date = models.DateField(
        null=True,
        blank=True,
        verbose_name="Дата начала"
    )
    end_date = models.DateField(
        null=True,
        blank=True,
        verbose_name="Дата окончания"
    )
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
    issue_date = models.DateField(
        null=True,
        blank=True,
        verbose_name="Дата выдачи"
    )
    training_city_ru = models.CharField(
        max_length=255,
        blank=True,
        verbose_name="Место (рус)"
    )
    training_city_by = models.CharField(
        max_length=255,
        blank=True,
        verbose_name="Место (бел)"
    )
    exam_score = models.CharField(
        max_length=50,
        blank=True,
        verbose_name="Отметка за экзамен"
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
            models.Index(fields=['organization', 'subdivision', 'department'], name='train_tree_idx'),
            models.Index(fields=['employee'], name='train_employee_idx'),
        ]

    def __str__(self):
        return f"{self.employee.full_name_nominative} — {self.profession.name_ru_nominative}"


class TrainingRoleAssignment(models.Model):
    training = models.ForeignKey(
        ProductionTraining,
        on_delete=models.CASCADE,
        related_name='role_assignments',
        verbose_name="Обучение"
    )
    role_type = models.ForeignKey(
        TrainingRoleType,
        on_delete=models.PROTECT,
        related_name='assignments',
        verbose_name="Роль"
    )
    employee = models.ForeignKey(
        'directory.Employee',
        on_delete=models.PROTECT,
        related_name='training_roles',
        verbose_name="Сотрудник"
    )
    position_override = models.CharField(
        max_length=255,
        blank=True,
        verbose_name="Должность (если отличается)"
    )
    name_override = models.CharField(
        max_length=255,
        blank=True,
        verbose_name="ФИО (если отличается)"
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
        verbose_name = "🧑‍🏫 Роль в обучении"
        verbose_name_plural = "🧑‍🏫 Роли в обучении"
        ordering = ['order', 'role_type__order', 'employee__full_name_nominative']
        unique_together = ['training', 'role_type', 'employee']

    def __str__(self):
        return f"{self.role_type.name}: {self.employee.full_name_nominative}"


class TrainingDiaryEntry(models.Model):
    training = models.ForeignKey(
        ProductionTraining,
        on_delete=models.CASCADE,
        related_name='diary_entries',
        verbose_name="Обучение"
    )
    entry_date = models.DateField(
        null=True,
        blank=True,
        verbose_name="Дата"
    )
    entry_type = models.ForeignKey(
        TrainingEntryType,
        on_delete=models.PROTECT,
        related_name='diary_entries',
        verbose_name="Тип записи"
    )
    topic = models.TextField(
        verbose_name="Тема"
    )
    hours = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        default=0,
        verbose_name="Часы"
    )
    score = models.CharField(
        max_length=50,
        blank=True,
        verbose_name="Оценка"
    )
    order = models.PositiveIntegerField(
        default=0,
        verbose_name="Порядок"
    )

    class Meta:
        verbose_name = "🗒️ Запись дневника"
        verbose_name_plural = "🗒️ Записи дневника"
        ordering = ['order', 'entry_date']

    def __str__(self):
        return self.topic


class TrainingTheoryConsultation(models.Model):
    training = models.ForeignKey(
        ProductionTraining,
        on_delete=models.CASCADE,
        related_name='theory_consultations',
        verbose_name="Обучение"
    )
    date = models.DateField(
        null=True,
        blank=True,
        verbose_name="Дата"
    )
    hours = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        default=0,
        verbose_name="Часы"
    )
    consultant = models.ForeignKey(
        'directory.Employee',
        on_delete=models.PROTECT,
        related_name='theory_consultations',
        verbose_name="Консультант"
    )
    signature_required = models.BooleanField(
        default=True,
        verbose_name="Требуется подпись"
    )
    order = models.PositiveIntegerField(
        default=0,
        verbose_name="Порядок"
    )

    class Meta:
        verbose_name = "🧾 Теоретическая консультация"
        verbose_name_plural = "🧾 Теоретические консультации"
        ordering = ['order', 'date']

    def __str__(self):
        return f"{self.consultant.full_name_nominative} ({self.date})"
