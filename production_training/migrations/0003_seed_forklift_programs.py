from django.db import migrations


def seed_forklift_programs(apps, schema_editor):
    TrainingType = apps.get_model('production_training', 'TrainingType')
    TrainingQualificationGrade = apps.get_model('production_training', 'TrainingQualificationGrade')
    TrainingProfession = apps.get_model('production_training', 'TrainingProfession')
    TrainingProgram = apps.get_model('production_training', 'TrainingProgram')

    # Типы обучения
    prep_type, _ = TrainingType.objects.get_or_create(
        code='preparation',
        defaults={'name_ru': 'Подготовка', 'is_active': True},
    )
    retrain_type, _ = TrainingType.objects.get_or_create(
        code='retraining',
        defaults={'name_ru': 'Переподготовка', 'is_active': True},
    )

    # Разряд
    grade3, _ = TrainingQualificationGrade.objects.get_or_create(
        grade_number=3,
        defaults={
            'label_ru': '3 (третий)',
            'label_by': '',
            'is_active': True,
        },
    )

    # Профессия
    profession, _ = TrainingProfession.objects.get_or_create(
        name_ru_nominative='Водитель погрузчика',
        name_ru_genitive='водителя погрузчика',
        defaults={
            'name_by_nominative': '',
            'name_by_genitive': '',
            'is_active': True,
        },
    )

    # Планы по часам (недельные)
    weekly_prep = [40, 40, 40, 40, 40, 40, 40, 40]          # подготовка
    weekly_retrain = [40, 40, 40, 40, 32]                   # переподготовка

    # Итоги часов по планам
    total_prep = sum(weekly_prep)                           # 320
    total_retrain = sum(weekly_retrain)                     # 192

    # Простейшее распределение теории/практики из планов по часам (можно уточнить позже)
    practice_prep = 232
    practice_retrain = 128
    theory_prep = total_prep - practice_prep
    theory_retrain = total_retrain - practice_retrain

    # Создаём/обновляем программы
    TrainingProgram.objects.update_or_create(
        name='Подготовка рабочих по профессии «Водитель погрузчика» 3 разряд',
        training_type=prep_type,
        profession=profession,
        defaults={
            'qualification_grade': grade3,
            'weekly_hours': weekly_prep,
            'duration_days': total_prep // 8,
            'content': {
                'sections': [],
                'total_hours': total_prep,
                'theory_hours': theory_prep,
                'practice_hours': practice_prep,
            },
            'description': 'Автосоздано миграцией: план подготовки водителя погрузчика, 3 разряд.',
            'is_active': True,
        }
    )

    TrainingProgram.objects.update_or_create(
        name='Переподготовка рабочих по профессии «Водитель погрузчика» 3 разряд',
        training_type=retrain_type,
        profession=profession,
        defaults={
            'qualification_grade': grade3,
            'weekly_hours': weekly_retrain,
            'duration_days': total_retrain // 8,
            'content': {
                'sections': [],
                'total_hours': total_retrain,
                'theory_hours': theory_retrain,
                'practice_hours': practice_retrain,
            },
            'description': 'Автосоздано миграцией: план переподготовки водителя погрузчика, 3 разряд.',
            'is_active': True,
        }
    )


def noop_reverse(apps, schema_editor):
    # Оставляем данные при откате.
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('production_training', '0002_trainingprogram_weekly_hours'),
    ]

    operations = [
        migrations.RunPython(seed_forklift_programs, noop_reverse),
    ]
