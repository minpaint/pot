"""
📧 Email-адреса для уведомлений отдела.
"""
from django.db import models
from django.core.validators import validate_email
from django.core.exceptions import ValidationError


class DepartmentEmail(models.Model):
    """
    Email-адреса, привязанные к отделу.
    """

    department = models.ForeignKey(
        'directory.Department',
        on_delete=models.CASCADE,
        related_name='notification_emails',
        verbose_name="Отдел",
        help_text="Отдел, для которого настраивается email"
    )

    email = models.EmailField(
        verbose_name="Email для уведомлений",
        help_text="Email-адрес получателя уведомлений (например: master@company.com)"
    )

    description = models.CharField(
        max_length=255,
        blank=True,
        default='',
        verbose_name="Описание",
        help_text='Роль получателя: "Начальник отдела", "Бригадир" и т.д.'
    )

    is_active = models.BooleanField(
        default=True,
        verbose_name="Активен",
        help_text="Если отключено, уведомления на этот адрес отправляться не будут"
    )

    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Дата создания")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Дата изменения")

    class Meta:
        verbose_name = "Email отдела"
        verbose_name_plural = "Email отдела"
        ordering = ['department__name', 'email']
        unique_together = [['department', 'email']]
        indexes = [
            models.Index(fields=['department', 'is_active']),
        ]

    def clean(self):
        """Валидация email-адреса."""
        super().clean()

        if self.email:
            self.email = self.email.strip().lower()
            try:
                validate_email(self.email)
            except ValidationError:
                raise ValidationError({'email': 'Введите корректный email-адрес'})

            if '..' in self.email:
                raise ValidationError({'email': f'Неверный формат email: двойные точки в "{self.email}"'})

            if '@' in self.email:
                _, domain = self.email.rsplit('@', 1)
                if domain.startswith('.') or domain.endswith('.') or '..' in domain:
                    raise ValidationError({'email': f'Неверный формат домена в "{self.email}"'})
                try:
                    domain.encode('idna')
                except Exception as exc:
                    raise ValidationError({'email': f'Ошибка проверки домена в "{self.email}": {exc}'})

    def save(self, *args, **kwargs):
        self.clean()
        return super().save(*args, **kwargs)

    def __str__(self):
        if self.description:
            return f"{self.email} ({self.description})"
        return self.email
