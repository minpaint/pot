from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('production_training', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='trainingprogram',
            name='weekly_hours',
            field=models.JSONField(blank=True, default=list, help_text='Список часов по неделям (пример: [40, 40, 40, 40, 32])', verbose_name='Недельные часы'),
        ),
    ]
