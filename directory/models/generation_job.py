"""
⚙️ Модель для отслеживания асинхронных задач массовой генерации документов.

Каждая POST-запрос на массовую генерацию создаёт GenerationJob и ставит task в очередь.
Пользователь видит прогресс и скачивает готовый файл с этой же страницы.
"""
from django.db import models
from django.conf import settings


def _job_upload_path(instance, filename):
    return f'generation_jobs/{instance.created_at:%Y/%m/%d}/{instance.id}_{filename}'


class GenerationJob(models.Model):
    JOB_TYPE_CHOICES = [
        ('periodic_protocol',           'Протокол периодической проверки знаний (один файл)'),
        ('periodic_protocol_by_sub',    'Протоколы по подразделениям (архив)'),
        ('periodic_certificates',       'Удостоверения по ОТ (один файл)'),
        ('periodic_certificates_by_sub','Удостоверения по ОТ по подразделениям (архив)'),
        ('ot_card_bulk',                'Личные карточки по ОТ (архив)'),
        ('instruction_journal_unified', 'Журнал инструктажей (один файл)'),
        ('instruction_journal_by_sub',  'Журнал инструктажей по подразделениям (архив)'),
        ('siz_cards_bulk',              'Карточки СИЗ по подразделениям (архив)'),
        ('siz_cards_org',               'Карточки СИЗ по организации (архив)'),
        ('admin_hiring_generate',       'Документы приёма из админки (архив)'),
    ]

    STATUS_CHOICES = [
        ('pending',   'Ожидает'),
        ('running',   'Выполняется'),
        ('done',      'Готово'),
        ('failed',    'Ошибка'),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='generation_jobs',
        verbose_name='Пользователь',
    )
    job_type = models.CharField(max_length=64, choices=JOB_TYPE_CHOICES, verbose_name='Тип задачи')
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default='pending', db_index=True)

    title = models.CharField(max_length=255, blank=True, verbose_name='Название (для UI)')
    params = models.JSONField(default=dict, blank=True, verbose_name='Параметры задачи')

    progress_current = models.PositiveIntegerField(default=0)
    progress_total = models.PositiveIntegerField(default=0)

    result_file = models.FileField(upload_to=_job_upload_path, blank=True, null=True)
    result_filename = models.CharField(max_length=512, blank=True)
    content_type = models.CharField(max_length=128, blank=True)

    error_message = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = 'Задача генерации'
        verbose_name_plural = 'Задачи генерации'
        ordering = ['-created_at']

    def __str__(self):
        return f'#{self.pk} {self.get_job_type_display()} [{self.status}]'

    @property
    def progress_percent(self):
        if not self.progress_total:
            return 0
        return int(self.progress_current * 100 / self.progress_total)

    @property
    def is_finished(self):
        return self.status in ('done', 'failed')
