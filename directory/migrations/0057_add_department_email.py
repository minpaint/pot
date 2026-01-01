from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('directory', '0056_add_show_in_hiring_flag'),
    ]

    operations = [
        migrations.CreateModel(
            name='DepartmentEmail',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('email', models.EmailField(help_text='Email-адрес получателя уведомлений (например: master@company.com)', max_length=254, verbose_name='Email для уведомлений')),
                ('description', models.CharField(blank=True, default='', help_text='Роль получателя: "Начальник отдела", "Бригадир" и т.д.', max_length=255, verbose_name='Описание')),
                ('is_active', models.BooleanField(default=True, help_text='Если отключено, уведомления на этот адрес отправляться не будут', verbose_name='Активен')),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name='Дата создания')),
                ('updated_at', models.DateTimeField(auto_now=True, verbose_name='Дата изменения')),
                ('department', models.ForeignKey(help_text='Отдел, для которого настраивается email', on_delete=django.db.models.deletion.CASCADE, related_name='notification_emails', to='directory.department', verbose_name='Отдел')),
            ],
            options={
                'verbose_name': 'Email отдела',
                'verbose_name_plural': 'Email отдела',
                'ordering': ['department__name', 'email'],
            },
        ),
        migrations.AddIndex(
            model_name='departmentemail',
            index=models.Index(fields=['department', 'is_active'], name='directory_d_departm_d9af5f_idx'),
        ),
        migrations.AlterUniqueTogether(
            name='departmentemail',
            unique_together={('department', 'email')},
        ),
    ]
