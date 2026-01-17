from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('production_training', '0008_remove_unused_hour_fields'),
        ('directory', '0072_change_employee_education_level_to_text'),
    ]

    operations = [
        migrations.DeleteModel(
            name='EducationLevel',
        ),
    ]
