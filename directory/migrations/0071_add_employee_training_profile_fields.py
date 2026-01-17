from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('directory', '0070_add_employee_work_schedule'),
    ]

    operations = [
        migrations.AddField(
            model_name='employee',
            name='full_name_by',
            field=models.CharField(blank=True, max_length=255, verbose_name='ФИО (бел.)'),
        ),
        migrations.AddField(
            model_name='employee',
            name='qualification_document_number',
            field=models.CharField(blank=True, max_length=100, verbose_name='Номер диплома/свидетельства'),
        ),
        migrations.AddField(
            model_name='employee',
            name='qualification_document_date',
            field=models.DateField(blank=True, null=True, verbose_name='Дата диплома/свидетельства'),
        ),
    ]
