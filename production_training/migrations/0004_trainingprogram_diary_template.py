from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('production_training', '0003_seed_forklift_programs'),
    ]

    operations = [
        migrations.AddField(
            model_name='trainingprogram',
            name='diary_template',
            field=models.FileField(blank=True, null=True, upload_to='document_templates/learning/', verbose_name='Шаблон дневника (DOCX)'),
        ),
    ]
