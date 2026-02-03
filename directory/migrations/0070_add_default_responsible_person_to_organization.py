# -*- coding: utf-8 -*-
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('directory', '0069_add_default_training_roles_to_organization'),
    ]

    operations = [
        migrations.AddField(
            model_name='organization',
            name='default_responsible_person',
            field=models.ForeignKey(
                blank=True,
                help_text='Будет подставляться как ответственный в документах обучения',
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='org_default_responsible_person',
                to='directory.employee',
                verbose_name='Эталонный ответственный за обучение',
            ),
        ),
    ]
