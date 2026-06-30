from django.db import models
from django.core.exceptions import ValidationError
from django.db.models import Count


class ResponsibilityType(models.Model):
    """
    📋 Справочник видов ответственных.

    Примеры:
    - Ответственный за электрохозяйство
    - Ответственный за пожарную безопасность
    - Ответственный за газовое хозяйство
    - Ответственный за лифтовое хозяйство
    """
    name = models.CharField(
        max_length=255,
        unique=True,
        verbose_name="Название вида ответственности"
    )

    description = models.TextField(
        blank=True,
        verbose_name="Описание",
        help_text="Дополнительная информация о виде ответственности"
    )

    order = models.PositiveIntegerField(
        default=0,
        verbose_name="Порядок сортировки",
        help_text="Используется для упорядочивания в списках"
    )

    is_active = models.BooleanField(
        default=True,
        verbose_name="Активен",
        help_text="Неактивные виды ответственности не отображаются в формах"
    )

    class Meta:
        verbose_name = "⚖️ Вид ответственного"
        verbose_name_plural = "⚖️ Виды ответственных"
        ordering = ['order', 'name']

    def __str__(self):
        return self.name


class Position(models.Model):
    """
    👔 Модель для хранения информации о должностях.
    """
    ELECTRICAL_GROUP_CHOICES = [
        ("I", "I"),
        ("II", "II"),
        ("III", "III"),
        ("IV", "IV"),
        ("V", "V"),
    ]

    contract_work_name = models.TextField(
        "🔨 Наименование работы по договору подряда",
        blank=True,
        help_text="Укажите наименование работы, выполняемой по договору подряда"
    )

    contract_safety_instructions = models.CharField(
        "⚠️ Инструкции по охране труда по договору подряда",
        max_length=255,
        blank=True,
        help_text="Укажите номера инструкций по охране труда для данного вида работ"
    )

    company_vehicle_instructions = models.CharField(
        max_length=255,
        blank=True,
        verbose_name="🚗 Инструкции при управлении служебным автомобилем",
        help_text="Укажите номера инструкций по охране труда для водителей служебного транспорта"
    )

    position_name = models.CharField(
        max_length=255,
        verbose_name="Название"
    )
    organization = models.ForeignKey(
        'directory.Organization',
        on_delete=models.PROTECT,
        related_name="positions",
        verbose_name="Организация"
    )
    subdivision = models.ForeignKey(
        'directory.StructuralSubdivision',
        on_delete=models.PROTECT,
        related_name="positions",
        verbose_name="Структурное подразделение",
        null=True,
        blank=True
    )
    department = models.ForeignKey(
        'directory.Department',
        on_delete=models.PROTECT,
        related_name="positions",
        verbose_name="Отдел",
        null=True,
        blank=True
    )

    safety_instructions_numbers = models.CharField(
        max_length=255,
        blank=True,
        verbose_name="Номера инструкций по ОТ"
    )
    electrical_safety_group = models.CharField(
        max_length=4,
        choices=ELECTRICAL_GROUP_CHOICES,
        blank=True,
        verbose_name="Группа по электробезопасности"
    )

    height_group_1 = models.BooleanField(
        default=False,
        verbose_name="⛰️ Группа 1 (работа на высоте)"
    )
    height_group_2 = models.BooleanField(
        default=False,
        verbose_name="⛰️ Группа 2 (работа на высоте)"
    )
    height_group_3 = models.BooleanField(
        default=False,
        verbose_name="⛰️ Группа 3 (работа на высоте)"
    )

    internship_period_days = models.PositiveIntegerField(
        default=0,
        verbose_name="Срок стажировки (дни)"
    )

    is_responsible_for_safety = models.BooleanField(
        default=False,
        verbose_name="Ответственный за ОТ"
    )
    is_electrical_personnel = models.BooleanField(
        default=False,
        verbose_name="Электротехнический персонал"
    )
    can_be_internship_leader = models.BooleanField(
        default=False,
        verbose_name="Может быть руководителем стажировки"
    )

    can_sign_orders = models.BooleanField(
        default=False,
        verbose_name="Может подписывать распоряжения",
        help_text="Указывает, может ли сотрудник с этой должностью подписывать распоряжения"
    )

    drives_company_vehicle = models.BooleanField(
        default=False,
        verbose_name="🚗 Управляет служебным автомобилем",
        help_text="Отметьте, если должность предполагает управление служебным автомобилем"
    )

    requires_siz = models.BooleanField(
        default=True,
        verbose_name="🛡️ Требуются СИЗ",
        help_text="Если отключено, для этой должности не будут создаваться карточки СИЗ"
    )

    siz_norms_overridden = models.BooleanField(
        default=False,
        verbose_name="🛡️ Нормы СИЗ переопределены",
        help_text="Если включено, используются только нормы из таблицы ниже. Если нет норм - СИЗ не положены."
    )

    medical_norms_overridden = models.BooleanField(
        default=False,
        verbose_name="🏥 Нормы медосмотров переопределены",
        help_text="Если включено, используются только нормы из таблицы ниже. Если нет норм - медосмотры не требуются."
    )

    documents = models.ManyToManyField(
        'directory.Document',
        blank=True,
        related_name="positions",
        verbose_name="Документы"
    )
    equipment = models.ManyToManyField(
        'deadline_control.Equipment',
        blank=True,
        related_name="positions",
        verbose_name="Оборудование"
    )
    medical_harmful_factors = models.ManyToManyField(
        'deadline_control.HarmfulFactor',
        through='deadline_control.PositionMedicalFactor',
        related_name='positions',
        verbose_name="Вредные факторы медосмотров",
        blank=True
    )

    responsibility_types = models.ManyToManyField(
        'ResponsibilityType',
        blank=True,
        related_name='positions',
        verbose_name="📋 Виды ответственности",
        help_text="Выберите виды ответственности для данной должности"
    )

    class Meta:
        verbose_name = "💼 Профессия/должность"
        verbose_name_plural = "💼 Профессии/должности"
        ordering = ['position_name']
        unique_together = [
            ['position_name', 'organization', 'subdivision', 'department']
        ]
        indexes = [
            # Индексы для древовидной структуры (организация → подразделение → отдел)
            models.Index(fields=['organization', 'subdivision', 'department'], name='pos_tree_idx'),
            # Индекс для поиска и сортировки по названию должности
            models.Index(fields=['position_name'], name='pos_name_idx'),
            # Индекс для эталонных норм (поиск по названию должности)
            models.Index(fields=['position_name', 'organization'], name='pos_name_org_idx'),
        ]

    def clean(self):
        if self.department:
            if not self.subdivision:
                raise ValidationError({
                    'department': 'Нельзя указать отдел без структурного подразделения'
                })
            if self.department.organization != self.organization:
                raise ValidationError({
                    'department': 'Отдел должен принадлежать выбранной организации'
                })
            if self.department.subdivision != self.subdivision:
                raise ValidationError({
                    'department': 'Отдел должен принадлежать выбранному подразделению'
                })

        if self.subdivision and self.subdivision.organization != self.organization:
            raise ValidationError({
                'subdivision': 'Подразделение должно принадлежать выбранной организации'
            })

        # Валидация полей служебного автомобиля
        if self.drives_company_vehicle and not self.company_vehicle_instructions:
            raise ValidationError({
                'company_vehicle_instructions': 'Необходимо указать инструкции при управлении служебным автомобилем'
            })

        # Валидация групп для работы на высоте: 1 группа несовместима с 2 и 3
        if self.height_group_1 and (self.height_group_2 or self.height_group_3):
            raise ValidationError({
                'height_group_1': '1 группа не совместима со 2-й и 3-й группами. '
                                  'Совместно могут устанавливаться только 2 и 3 группы.'
            })

    def save(self, *args, **kwargs):
        self.clean()
        super().save(*args, **kwargs)

    def __str__(self):
        parts = [self.position_name]
        if not self.department:
            if self.subdivision:
                parts.append(f"({self.subdivision.name})")
            else:
                parts.append(f"({self.organization.short_name_ru})")
        return " ".join(parts)

    def get_full_path(self):
        parts = [self.organization.short_name_ru or self.organization.full_name_ru]
        if self.subdivision:
            parts.append(self.subdivision.name)
        if self.department:
            parts.append(self.department.name)
        parts.append(self.position_name)
        return " → ".join(parts)

    @classmethod
    def find_reference_norms(cls, position_name):
        """
        Возвращает QuerySet эталонных норм СИЗ (ProfessionSIZNorm)
        для указанного названия должности (без учёта регистра).
        """
        from directory.models.siz import ProfessionSIZNorm
        return ProfessionSIZNorm.objects.filter(
            profession_name__iexact=position_name
        )
