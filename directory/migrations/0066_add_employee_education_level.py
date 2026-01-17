from django.db import migrations, models


def copy_education_level_from_training(apps, schema_editor):
    Employee = apps.get_model('directory', 'Employee')
    ProductionTraining = apps.get_model('production_training', 'ProductionTraining')

    trainings = ProductionTraining.objects.select_related('employee', 'education_level').exclude(
        education_level__isnull=True
    )

    for training in trainings:
        employee = training.employee
        if employee and employee.education_level_id is None:
            employee.education_level_id = training.education_level_id
            employee.save(update_fields=['education_level'])


class Migration(migrations.Migration):

    dependencies = [
        ('production_training', '0004_trainingprogram_diary_template'),
        ('directory', '0065_fix_commission_type_max_length'),
    ]

    operations = [
        migrations.AddField(
            model_name='employee',
            name='education_level',
            field=models.ForeignKey(blank=True, null=True, on_delete=models.SET_NULL, related_name='employees', to='production_training.educationlevel', verbose_name='Уровень образования'),
        ),
        migrations.RunPython(copy_education_level_from_training, migrations.RunPython.noop),
    ]
