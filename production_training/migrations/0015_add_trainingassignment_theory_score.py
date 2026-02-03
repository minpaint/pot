from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('production_training', '0014_add_trainingprogram_practical_work_topic'),
    ]

    operations = [
        migrations.AddField(
            model_name='trainingassignment',
            name='theory_score',
            field=models.CharField(
                blank=True,
                max_length=50,
                verbose_name='Отметка за теоретический экзамен',
            ),
        ),
    ]
