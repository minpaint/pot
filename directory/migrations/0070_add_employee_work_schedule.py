from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('directory', '0069_add_default_training_roles_to_organization'),
    ]

    operations = [
        migrations.AddField(
            model_name='employee',
            name='work_schedule',
            field=models.CharField(
                choices=[('5/2', '5/2 (пн-пт)'), ('2/2', '2/2 (сменный)')],
                default='5/2',
                max_length=3,
                verbose_name='График работы',
            ),
        ),
    ]
