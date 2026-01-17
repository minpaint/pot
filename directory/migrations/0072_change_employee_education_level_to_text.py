from django.db import migrations, models


def copy_education_level_to_text(apps, schema_editor):
    Employee = apps.get_model('directory', 'Employee')
    for employee in Employee.objects.select_related('education_level').all():
        if employee.education_level_id:
            education = employee.education_level
            employee.education_level_text = getattr(education, 'name_ru', str(education))
            employee.save(update_fields=['education_level_text'])


class Migration(migrations.Migration):

    dependencies = [
        ('directory', '0071_add_employee_training_profile_fields'),
    ]

    operations = [
        migrations.AddField(
            model_name='employee',
            name='education_level_text',
            field=models.CharField(
                blank=True,
                null=True,
                max_length=255,
                verbose_name='Уровень образования',
                help_text='Например: среднее специальное',
            ),
        ),
        migrations.RunPython(copy_education_level_to_text, migrations.RunPython.noop),
        migrations.RemoveField(
            model_name='employee',
            name='education_level',
        ),
        migrations.RenameField(
            model_name='employee',
            old_name='education_level_text',
            new_name='education_level',
        ),
    ]
