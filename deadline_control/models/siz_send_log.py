from django.db import models
from django.contrib.auth import get_user_model

User = get_user_model()


class SIZCardSendLog(models.Model):
    STATUS_CHOICES = [
        ('in_progress', 'В процессе'),
        ('completed', 'Завершено успешно'),
        ('partial', 'Завершено частично'),
        ('failed', 'Ошибка'),
    ]

    organization = models.ForeignKey(
        'directory.Organization',
        on_delete=models.CASCADE,
        related_name='siz_card_send_logs',
        verbose_name='Организация'
    )
    initiated_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        related_name='initiated_siz_card_sends',
        verbose_name='Инициатор'
    )
    issue_date = models.DateField(null=True, blank=True, verbose_name='Дата выдачи')
    total_subdivisions = models.IntegerField(default=0, verbose_name='Всего подразделений')
    successful_count = models.IntegerField(default=0, verbose_name='Успешных отправок')
    failed_count = models.IntegerField(default=0, verbose_name='Ошибок отправки')
    skipped_count = models.IntegerField(default=0, verbose_name='Пропущено')
    total_cards = models.IntegerField(default=0, verbose_name='Всего карточек')
    test_mode = models.BooleanField(default=False, verbose_name='Тестовый режим')
    status = models.CharField(
        max_length=20, choices=STATUS_CHOICES, default='in_progress', verbose_name='Статус'
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Дата запуска')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='Дата обновления')

    class Meta:
        verbose_name = '🛡️ Карточки СИЗ'
        verbose_name_plural = '🛡️ Карточки СИЗ'
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.organization.short_name_ru} - {self.created_at.strftime('%d.%m.%Y %H:%M')}"

    def get_total_processed(self):
        return self.successful_count + self.failed_count + self.skipped_count

    def get_success_rate(self):
        total = self.get_total_processed()
        return 0 if total == 0 else round((self.successful_count / total) * 100, 1)
