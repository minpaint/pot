"""
📧 Модель для хранения email-адресов структурных подразделений.

Email-адреса используются для отправки уведомлений ответственным лицам
в подразделениях (главный инженер, мастер участка, служба ОТ и т.д.).
"""
from django.db import models
from django.core.validators import validate_email
from django.core.exceptions import ValidationError


class SubdivisionEmail(models.Model):
    """
    Email-адреса для уведомлений структурного подразделения.

    Примеры использования:
    - Главный инженер цеха
    - Мастер участка
    - Служба охраны труда подразделения
    - Начальник отдела

    Связь: Одно подразделение может иметь несколько email-адресов.
    """

    subdivision = models.ForeignKey(
        'directory.StructuralSubdivision',
        on_delete=models.CASCADE,
        related_name='notification_emails',
        verbose_name="Структурное подразделение",
        help_text="Подразделение, для которого настраивается email"
    )

    email = models.EmailField(
        verbose_name="Email для уведомлений",
        help_text="Email-адрес получателя уведомлений (например: engineer@company.com)"
    )

    description = models.CharField(
        max_length=255,
        blank=True,
        default='',
        verbose_name="Описание",
        help_text='Роль получателя: "Главный инженер", "Мастер участка", "Служба ОТ" и т.д.'
    )

    is_active = models.BooleanField(
        default=True,
        verbose_name="Активен",
        help_text="Если отключено, уведомления на этот адрес отправляться не будут"
    )

    # Метаданные
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Дата создания"
    )

    updated_at = models.DateTimeField(
        auto_now=True,
        verbose_name="Дата изменения"
    )

    class Meta:
        verbose_name = "Email для уведомлений"
        verbose_name_plural = "Email для уведомлений"
        ordering = ['subdivision__name', 'email']
        # Один и тот же email не может быть добавлен дважды для одного подразделения
        unique_together = [['subdivision', 'email']]
        indexes = [
            models.Index(fields=['subdivision', 'is_active']),
        ]

    def clean(self):
        """Валидация email-адреса"""
        super().clean()

        if self.email:
            # Убираем лишние пробелы сразу
            self.email = self.email.strip().lower()

            # Проверяем базовый формат email
            try:
                validate_email(self.email)
            except ValidationError:
                raise ValidationError({
                    'email': 'Введите корректный email-адрес'
                })

            # Проверка на двойные точки (IDNA защита)
            if '..' in self.email:
                raise ValidationError({
                    'email': f'Неверный формат email: найдены двойные точки (..) в "{self.email}"'
                })

            # Проверка IDNA кодирования домена
            if '@' in self.email:
                try:
                    _, domain = self.email.rsplit('@', 1)

                    # Проверка на точку в начале/конце домена
                    if domain.startswith('.') or domain.endswith('.'):
                        raise ValidationError({
                            'email': f'Неверный формат домена: не может начинаться или заканчиваться точкой в "{self.email}"'
                        })

                    # Проверка на пустые метки в домене
                    if '..' in domain:
                        raise ValidationError({
                            'email': f'Неверный формат домена: двойные точки (..) в "{self.email}"'
                        })

                    # Попытка IDNA кодирования
                    domain.encode('idna')

                except UnicodeError as e:
                    raise ValidationError({
                        'email': f'Ошибка IDNA кодирования домена в "{self.email}": {str(e)}'
                    })
                except Exception as e:
                    # Пропускаем ValidationError выше
                    if isinstance(e, ValidationError):
                        raise
                    raise ValidationError({
                        'email': f'Ошибка проверки домена в "{self.email}": {str(e)}'
                    })

    def save(self, *args, **kwargs):
        self.clean()
        super().save(*args, **kwargs)

    def __str__(self):
        """Строковое представление"""
        if self.description:
            return f"{self.email} ({self.description})"
        return self.email

    def get_display_name(self):
        """Возвращает красивое имя для отображения в админке"""
        parts = [self.email]
        if self.description:
            parts.append(f"— {self.description}")
        if not self.is_active:
            parts.append("(отключен)")
        return " ".join(parts)
