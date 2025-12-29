# Generated manually

from django.db import migrations


def create_default_equipment_types(apps, schema_editor):
    """
    Создание предустановленных типов оборудования
    """
    EquipmentType = apps.get_model('deadline_control', 'EquipmentType')

    default_types = [
        {
            'name': 'Лестница',
            'default_maintenance_period_months': 12,
            'description': 'Приставные и стационарные лестницы',
            'is_active': True
        },
        {
            'name': 'Грузовая тележка',
            'default_maintenance_period_months': 3,
            'description': 'Грузовые тележки и тачки',
            'is_active': True
        },
        {
            'name': 'Погрузчик',
            'default_maintenance_period_months': 6,
            'description': 'Электропогрузчики и автопогрузчики',
            'is_active': True
        },
        {
            'name': 'Автомобиль',
            'default_maintenance_period_months': 12,
            'description': 'Транспортные средства',
            'is_active': True
        },
    ]

    for type_data in default_types:
        EquipmentType.objects.get_or_create(
            name=type_data['name'],
            defaults={
                'default_maintenance_period_months': type_data['default_maintenance_period_months'],
                'description': type_data['description'],
                'is_active': type_data['is_active']
            }
        )


def reverse_func(apps, schema_editor):
    """
    Удаление предустановленных типов оборудования при откате миграции
    """
    EquipmentType = apps.get_model('deadline_control', 'EquipmentType')
    EquipmentType.objects.filter(
        name__in=['Лестница', 'Грузовая тележка', 'Погрузчик', 'Автомобиль']
    ).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('deadline_control', '0029_add_equipment_type'),
    ]

    operations = [
        migrations.RunPython(create_default_equipment_types, reverse_func),
    ]
