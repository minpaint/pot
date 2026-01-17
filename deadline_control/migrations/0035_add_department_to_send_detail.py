from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('directory', '0065_fix_commission_type_max_length'),
        ('deadline_control', '0034_add_bulk_email_settings'),
    ]

    operations = [
        migrations.AddField(
            model_name='instructionjournalsenddetail',
            name='department',
            field=models.ForeignKey(
                blank=True,
                help_text='Если не указан - отправка для основного подразделения',
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name='instruction_send_details',
                to='directory.department',
                verbose_name='Отдел'
            ),
        ),
        migrations.AlterModelOptions(
            name='instructionjournalsenddetail',
            options={
                'ordering': ['subdivision__name', 'department__name'],
                'verbose_name': '📋 Деталь отправки',
                'verbose_name_plural': '📋 Детали отправок'
            },
        ),
        migrations.RemoveIndex(
            model_name='instructionjournalsenddetail',
            name='deadline_co_send_lo_922a23_idx',
        ),
        migrations.RemoveIndex(
            model_name='instructionjournalsenddetail',
            name='deadline_co_subdivi_02c90d_idx',
        ),
        migrations.AddIndex(
            model_name='instructionjournalsenddetail',
            index=models.Index(fields=['send_log', 'status'], name='deadli_deadli_send_lo_e9f079_idx'),
        ),
        migrations.AddIndex(
            model_name='instructionjournalsenddetail',
            index=models.Index(fields=['subdivision'], name='deadli_deadli_subdivi_3cc136_idx'),
        ),
        migrations.AddIndex(
            model_name='instructionjournalsenddetail',
            index=models.Index(fields=['department'], name='deadli_deadli_departm_9e34ab_idx'),
        ),
    ]
