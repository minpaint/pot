# -*- coding: utf-8 -*-
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('production_training', '0013_add_trainingprogram_practical_work_hours'),
    ]

    operations = [
        migrations.AddField(
            model_name='trainingprogram',
            name='practical_work_topic',
            field=models.TextField(
                blank=True,
                verbose_name='Тема пробной работы',
                help_text='Стандартная тема пробной работы для программы',
            ),
        ),
    ]
