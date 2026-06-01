from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('directory', '0078_add_employee_gender'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='TaskList',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('title', models.CharField(max_length=200, verbose_name='Название')),
                ('color', models.CharField(default='#3498db', help_text='HEX-цвет заголовка списка, например #3498db', max_length=7, verbose_name='Цвет')),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name='Создан')),
                ('is_archived', models.BooleanField(default=False, verbose_name='Архивирован')),
                ('organization', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='task_lists', to='directory.organization', verbose_name='Организация')),
                ('created_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='created_task_lists', to=settings.AUTH_USER_MODEL, verbose_name='Создал')),
            ],
            options={
                'verbose_name': 'Список задач',
                'verbose_name_plural': 'Списки задач',
                'ordering': ['-created_at'],
            },
        ),
        migrations.CreateModel(
            name='TaskItem',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('text', models.CharField(max_length=500, verbose_name='Задача')),
                ('is_done', models.BooleanField(default=False, verbose_name='Выполнена')),
                ('priority', models.CharField(choices=[('high', '🔴 Высокий'), ('normal', '🟡 Обычный'), ('low', '🟢 Низкий')], default='normal', max_length=10, verbose_name='Приоритет')),
                ('due_date', models.DateField(blank=True, null=True, verbose_name='Срок')),
                ('done_at', models.DateTimeField(blank=True, null=True, verbose_name='Выполнена в')),
                ('order', models.PositiveIntegerField(default=0, verbose_name='Порядок')),
                ('task_list', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='items', to='tasks.tasklist', verbose_name='Список')),
            ],
            options={
                'verbose_name': 'Задача',
                'verbose_name_plural': 'Задачи',
                'ordering': ['is_done', 'order', 'due_date'],
            },
        ),
    ]
