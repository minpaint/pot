from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('directory', '0068_remove_employee_workplace'),
        ('production_training', '0005_remove_education_level_from_training'),
    ]

    operations = [
        migrations.AlterField(
            model_name='productiontraining',
            name='employee',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='production_trainings', to='directory.employee', verbose_name='Сотрудник'),
        ),
        migrations.AddField(
            model_name='productiontraining',
            name='commission',
            field=models.ForeignKey(blank=True, limit_choices_to={'commission_type': 'qualification'}, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='production_trainings', to='directory.commission', verbose_name='Квалификационная комиссия'),
        ),
    ]
