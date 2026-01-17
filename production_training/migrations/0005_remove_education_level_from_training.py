from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('directory', '0066_add_employee_education_level'),
        ('production_training', '0004_trainingprogram_diary_template'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='productiontraining',
            name='education_level',
        ),
    ]
