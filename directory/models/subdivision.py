"""
🏭 Модель для хранения структурных подразделений.
Убрали наследование от MPTTModel, теперь это обычная Model
(без поля parent). Т.о. у нас одноуровневое подразделение,
привязанное напрямую к Organization.
"""
from django.db import models
from django.core.exceptions import ValidationError

class StructuralSubdivision(models.Model):
    name = models.CharField(
        "Наименование",
        max_length=255
    )
    short_name = models.CharField(
        "Сокращенное наименование",
        max_length=255,
        blank=True
    )
    organization = models.ForeignKey(
        'directory.Organization',
        on_delete=models.PROTECT,
        related_name="subdivisions",
        verbose_name="Организация"
    )
    skip_email_notifications = models.BooleanField(
        default=False,
        verbose_name='Пропустить email-уведомления',
        help_text='Если включено, рассылки по подразделению и его отделам будут пропущены'
    )

    class Meta:
        verbose_name = "🏭 Структурное подразделение"
        verbose_name_plural = "🏭 Структурные подразделения"
        ordering = ['name']
        unique_together = ['name', 'organization']

    def clean(self):
        # Если нужна логика валидации, напишите здесь 👇
        pass

    def save(self, *args, **kwargs):
        self.clean()
        super().save(*args, **kwargs)

    def __str__(self):
        # 👷 Возвращаем название + организацию
        return f"{self.name} ({self.organization.short_name_ru})"
