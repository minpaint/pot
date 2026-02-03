# -*- coding: utf-8 -*-
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('production_training', '0012_add_responsible_person_to_productiontraining'),
    ]

    operations = [
        migrations.AddField(
            model_name='trainingprogram',
            name='practical_work_hours',
            field=models.PositiveIntegerField(
                null=True,
                blank=True,
                verbose_name='Часов на пробную работу',
                help_text='Норматив часов на пробную работу',
            ),
        ),
    ]
