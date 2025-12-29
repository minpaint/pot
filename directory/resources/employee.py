"""
👥 Resource для импорта/экспорта сотрудников
"""
from import_export import resources, fields, widgets
from directory.models import Employee, Organization, StructuralSubdivision, Department, Position
from django.core.exceptions import ValidationError
from datetime import datetime


class RussianDateWidget(widgets.DateWidget):
    """Виджет для обработки дат в формате DD.MM.YYYY"""

    def clean(self, value, row=None, *args, **kwargs):
        if not value:
            return None

        # Если уже datetime
        if isinstance(value, datetime):
            return value.date()

        # Если date
        from datetime import date
        if isinstance(value, date):
            return value

        # Пробуем разные форматы (включая ISO формат из JSON)
        for fmt in ['%Y-%m-%dT%H:%M:%S', '%d.%m.%Y', '%Y-%m-%d', '%d/%m/%Y']:
            try:
                return datetime.strptime(str(value).strip(), fmt).date()
            except (ValueError, TypeError):
                continue

        return None


class SafeRelatedField(fields.Field):
    """
    Безопасное поле для связей, которое не падает при None значениях.
    Используется для экспорта связанных объектов через __ нотацию.
    При импорте значение не устанавливается (используется before_import_row).
    """
    def __init__(self, attribute_path=None, *args, **kwargs):
        self.attribute_path = attribute_path
        # Отключаем автоматическое сохранение атрибута при импорте
        kwargs['attribute'] = None
        kwargs['column_name'] = kwargs.get('column_name', attribute_path)
        super().__init__(*args, **kwargs)

    def export(self, obj):
        """Безопасный экспорт значения через цепочку атрибутов"""
        if not self.attribute_path:
            return ''

        try:
            value = obj
            for attr in self.attribute_path.split('__'):
                if value is None:
                    return ''
                value = getattr(value, attr, None)
            return value if value is not None else ''
        except (AttributeError, TypeError):
            return ''

    def clean(self, data, **kwargs):
        """
        При импорте просто возвращаем значение без обработки.
        Реальная установка связи происходит в before_import_row.
        """
        return data.get(self.column_name, '')


class EmployeeResource(resources.ModelResource):
    """
    👥 Ресурс для импорта/экспорта сотрудников.

    Простой подход: создаем organization/subdivision/department/position в before_import_row.
    """

    hire_date = fields.Field(
        column_name='hire_date',
        attribute='hire_date',
        widget=RussianDateWidget(format='%d.%m.%Y')
    )

    org_short_name_ru = SafeRelatedField(
        column_name='org_short_name_ru',
        attribute_path='organization__short_name_ru'
    )

    subdivision_name = SafeRelatedField(
        column_name='subdivision_name',
        attribute_path='subdivision__name'
    )

    department_name = SafeRelatedField(
        column_name='department_name',
        attribute_path='department__name'
    )

    position_name = SafeRelatedField(
        column_name='position_name',
        attribute_path='position__position_name'
    )

    full_name_nominative = fields.Field(
        column_name='full_name_nominative',
        attribute='full_name_nominative',
        widget=widgets.CharWidget()
    )

    class Meta:
        model = Employee
        fields = (
            'hire_date',
            'org_short_name_ru',
            'subdivision_name',
            'department_name',
            'position_name',
            'full_name_nominative',
        )
        export_order = (
            'hire_date',
            'full_name_nominative',
            'position_name',
            'subdivision_name',
            'department_name',
        )
        import_id_fields = []
        skip_unchanged = False

    def before_import_row(self, row, **kwargs):
        """Создаем organization/subdivision/department/position перед импортом каждой строки"""

        # 1. Получаем данные из строки
        org_short_name = row.get('org_short_name_ru', '').strip() if row.get('org_short_name_ru') else ''
        subdivision_name = row.get('subdivision_name', '').strip() if row.get('subdivision_name') else ''
        department_name = row.get('department_name', '').strip() if row.get('department_name') else ''
        position_name = row.get('position_name', '').strip() if row.get('position_name') else ''
        full_name = row.get('full_name_nominative', '').strip() if row.get('full_name_nominative') else ''

        # 2. Валидация
        if not org_short_name:
            raise ValidationError('Не указана организация')
        if not position_name:
            raise ValidationError('Не указана должность')
        if not full_name:
            raise ValidationError('Не указано ФИО сотрудника')
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

        # 6. Создаем или находим должность
        position, _ = Position.objects.get_or_create(
            position_name=position_name,
            organization=organization,
            subdivision=subdivision,
            department=department,
            defaults={'position_name': position_name}
        )

        # 7. Сохраняем связанные объекты в специальных полях row
        # Эти поля будут доступны в after_init_instance
        row['__organization'] = organization
        row['__subdivision'] = subdivision
        row['__department'] = department
        row['__position'] = position

    def after_init_instance(self, instance, new, row, **kwargs):
        """
        Устанавливаем связанные объекты после инициализации instance
        """
        # Устанавливаем связанные объекты из before_import_row
        if '__organization' in row:
            instance.organization = row['__organization']
        if '__subdivision' in row:
            instance.subdivision = row['__subdivision']
        if '__department' in row:
            instance.department = row['__department']
        if '__position' in row:
            instance.position = row['__position']

        # Автозаполнение полей по умолчанию
        if instance.hire_date and not instance.start_date:
            instance.start_date = instance.hire_date
        if not instance.contract_type:
            instance.contract_type = 'standard'
        if not instance.status:
            instance.status = 'active'

    def get_instance(self, instance_loader, row):
        """Ищем существующего сотрудника по ФИО"""
        full_name = row.get('full_name_nominative')
        if full_name:
            try:
                return Employee.objects.get(full_name_nominative=full_name)
            except Employee.DoesNotExist:
                pass
        return None

    def get_export_queryset(self, queryset=None):
        """Оптимизация для экспорта"""
        qs = super().get_export_queryset(queryset)
        return qs.select_related('organization', 'subdivision', 'department', 'position')
