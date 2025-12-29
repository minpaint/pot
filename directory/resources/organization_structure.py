"""
🏢 Resource для импорта/экспорта организационной структуры
Organization → StructuralSubdivision → Department → Position
"""
from import_export import resources, fields, widgets
from directory.models import Organization, StructuralSubdivision, Department, Position
from django.core.exceptions import ValidationError


class BooleanRussianWidget(widgets.BooleanWidget):
    """Виджет для обработки булевых значений на русском языке"""

    def clean(self, value, row=None, *args, **kwargs):
        if value in self.TRUE_VALUES:
            return True
        if value in self.FALSE_VALUES:
            return False

        # Обработка русских значений
        if isinstance(value, str):
            value_lower = value.lower().strip()
            if value_lower in ['да', 'yes', '1', 'true', 'т', 'y']:
                return True
            if value_lower in ['нет', 'no', '0', 'false', 'н', 'n', '']:
                return False

        return False


class OrganizationStructureResource(resources.ModelResource):
    """
    📊 Ресурс для импорта/экспорта организационной структуры.

    Простой подход: импортируем только поля Position,
    а organization/subdivision/department создаем в before_import_row.
    """

    org_short_name_ru = fields.Field(
        column_name='org_short_name_ru',
        attribute='organization__short_name_ru',
        widget=widgets.CharWidget(),
        readonly=True  # Только для экспорта, не импортируется
    )

    subdivision_name = fields.Field(
        column_name='subdivision_name',
        attribute='subdivision__name',
        widget=widgets.CharWidget(),
        readonly=True  # Только для экспорта, не импортируется
    )

    department_name = fields.Field(
        column_name='department_name',
        attribute='department__name',
        widget=widgets.CharWidget(),
        readonly=True  # Только для экспорта, не импортируется
    )

    is_responsible_for_safety = fields.Field(
        column_name='is_responsible_for_safety',
        attribute='is_responsible_for_safety',
        widget=BooleanRussianWidget()
    )

    can_be_internship_leader = fields.Field(
        column_name='can_be_internship_leader',
        attribute='can_be_internship_leader',
        widget=BooleanRussianWidget()
    )

    can_sign_orders = fields.Field(
        column_name='can_sign_orders',
        attribute='can_sign_orders',
        widget=BooleanRussianWidget()
    )

    drives_company_vehicle = fields.Field(
        column_name='drives_company_vehicle',
        attribute='drives_company_vehicle',
        widget=BooleanRussianWidget()
    )

    class Meta:
        model = Position
        fields = (
            'org_short_name_ru',
            'subdivision_name',
            'department_name',
            'position_name',
            'safety_instructions_numbers',
            'internship_period_days',
            'is_responsible_for_safety',
            'can_be_internship_leader',
            'can_sign_orders',
            'drives_company_vehicle',
            'company_vehicle_instructions',
        )
        export_order = (
            'subdivision_name',
            'department_name',
            'position_name',
            'safety_instructions_numbers',
            'company_vehicle_instructions',
            'drives_company_vehicle',
            'internship_period_days',
            'is_responsible_for_safety',
            'can_be_internship_leader',
            'can_sign_orders',
        )
        import_id_fields = []
        skip_unchanged = False
        skip_diff = True  # Отключаем проверку diff, чтобы не вызывался full_clean() до import_obj

    def before_import_row(self, row, **kwargs):
        """Создаем organization/subdivision/department перед импортом каждой строки"""

        # 1. Получаем данные из строки
        org_short_name = row.get('org_short_name_ru', '').strip() if row.get('org_short_name_ru') else ''
        subdivision_name = row.get('subdivision_name', '').strip() if row.get('subdivision_name') else ''
        department_name = row.get('department_name', '').strip() if row.get('department_name') else ''
        position_name = row.get('position_name', '').strip() if row.get('position_name') else ''

        # 2. Валидация
        # Примечание: org_short_name_ru необязательно, если организация выбрана в форме импорта
        # В этом случае _apply_organization_to_dataset() уже подставила её значение
        if not org_short_name:
            raise ValidationError(
                'Не указано краткое наименование организации. '
                'Либо укажите организацию в файле, либо выберите её в форме импорта.'
            )
        if not position_name:
            raise ValidationError('Не указано название должности')
        if department_name and not subdivision_name:
            raise ValidationError('Нельзя указать отдел без структурного подразделения')

        # 3. Создаем или находим организацию
        organization, _ = Organization.objects.get_or_create(
            short_name_ru=org_short_name,
            defaults={
                'full_name_ru': org_short_name,
                'short_name_by': org_short_name,
                'full_name_by': org_short_name,
                'location': 'г. Минск'
            }
        )

        # 4. Создаем или находим подразделение (если указано)
        subdivision = None
        if subdivision_name:
            subdivision, _ = StructuralSubdivision.objects.get_or_create(
                name=subdivision_name,
                organization=organization,
                defaults={'short_name': subdivision_name}
            )

        # 5. Создаем или находим отдел (если указан)
        department = None
        if department_name:
            department, _ = Department.objects.get_or_create(
                name=department_name,
                organization=organization,
                subdivision=subdivision,
                defaults={'short_name': department_name}
            )

        # 6. Добавляем связанные объекты напрямую (не ID)
        row['_organization'] = organization
        row['_subdivision'] = subdivision
        row['_department'] = department

        # 7. Устанавливаем значения по умолчанию
        if row.get('internship_period_days') in (None, ''):
            row['internship_period_days'] = 0
        if row.get('is_responsible_for_safety') in (None, ''):
            row['is_responsible_for_safety'] = False
        if row.get('can_be_internship_leader') in (None, ''):
            row['can_be_internship_leader'] = False
        if row.get('can_sign_orders') in (None, ''):
            row['can_sign_orders'] = False
        if row.get('drives_company_vehicle') in (None, ''):
            row['drives_company_vehicle'] = False

    def import_obj(self, obj, data, dry_run, **kwargs):
        """
        Переопределяем метод импорта для установки связанных объектов
        """
        # Устанавливаем связанные объекты из before_import_row ДО вызова super()
        # чтобы они были установлены до валидации модели
        if '_organization' in data:
            obj.organization = data['_organization']
        if '_subdivision' in data:
            obj.subdivision = data['_subdivision']
        if '_department' in data:
            obj.department = data['_department']

        # Теперь вызываем родительский метод для обработки остальных полей
        obj = super().import_obj(obj, data, dry_run, **kwargs)

        return obj

    def before_save_instance(self, instance, row, dry_run, **kwargs):
        """
        Дополнительная проверка перед сохранением - гарантируем, что organization установлена
        """
        if '_organization' in row and not instance.organization_id:
            instance.organization = row['_organization']
        if '_subdivision' in row and not instance.subdivision_id:
            instance.subdivision = row['_subdivision']
        if '_department' in row and not instance.department_id:
            instance.department = row['_department']

    def get_instance(self, instance_loader, row):
        """Ищем существующую должность или создаем новую"""
        organization = row.get('_organization')
        subdivision = row.get('_subdivision')
        department = row.get('_department')
        position_name = row.get('position_name')

        if not organization:
            return None

        try:
            return Position.objects.get(
                position_name=position_name,
                organization=organization,
                subdivision=subdivision,
                department=department
            )
        except Position.DoesNotExist:
            return None

    def get_export_queryset(self, queryset=None):
        """Оптимизация для экспорта"""
        qs = super().get_export_queryset(queryset)
        return qs.select_related('organization', 'subdivision', 'department')
