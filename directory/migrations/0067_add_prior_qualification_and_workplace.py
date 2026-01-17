from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('directory', '0066_add_employee_education_level'),
    ]

    operations = [
        migrations.AddField(
            model_name='employee',
            name='prior_qualification',
            field=models.TextField(
                blank=True,
                help_text='Например: автослесарь, А№0584083 от 09.02.2009',
                verbose_name='Имеющаяся квалификация'
            ),
        ),
        migrations.AddField(
            model_name='employee',
            name='workplace',
            field=models.CharField(
                blank=True,
                help_text='Например: склад, цех №1',
                max_length=255,
                verbose_name='Место работы'
            ),
        ),
    ]
