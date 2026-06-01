# 📁 directory/models/siz_issued.py
from django.db import models
from django.utils import timezone
from django.core.exceptions import ValidationError
from datetime import timedelta


class SIZIssued(models.Model):
    """
    🛡️ Модель для хранения информации о выданных сотрудникам СИЗ

    Хранит информацию о каждой выдаче СИЗ сотруднику, включая:
    - Кому выдано
    - Какое СИЗ выдано
    - Когда выдано
    - Количество
    - Процент износа
    - Срок использования и т.д.
    """
    employee = models.ForeignKey(
        'directory.Employee',
        on_delete=models.CASCADE,
        related_name='issued_siz',
        verbose_name="Сотрудник"
    )
    siz = models.ForeignKey(
        'directory.SIZ',
        on_delete=models.CASCADE,
        related_name='issues',
        verbose_name="СИЗ"
    )
    issue_date = models.DateField(
        verbose_name="Дата выдачи",
        default=timezone.now
    )
    quantity = models.PositiveIntegerField(
        verbose_name="Количество",
        default=1
    )
    wear_percentage = models.PositiveIntegerField(
        verbose_name="Процент износа",
        default=0,
        help_text="Укажите процент износа от 0 до 100"
    )
    cost = models.DecimalField(
        verbose_name="Стоимость",
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True
    )
    replacement_date = models.DateField(
        verbose_name="Дата замены/списания",
        null=True,
        blank=True
    )
    is_returned = models.BooleanField(
        verbose_name="Возвращено",
        default=False
    )
    return_date = models.DateField(
        verbose_name="Дата возврата",
        null=True,
        blank=True
    )
    notes = models.TextField(
        verbose_name="Примечания",
        blank=True
    )

    # Для учета условий выдачи (например, "При работе на высоте")
    condition = models.CharField(
        verbose_name="Условие выдачи",
        max_length=255,
        blank=True,
        help_text="Условие, при котором выдано СИЗ"
    )

    # Для подписи о получении
    received_signature = models.BooleanField(
        verbose_name="Подпись о получении",
        default=False
    )

    class Meta:
        verbose_name = "📦 Выданное СИЗ"
        verbose_name_plural = "📦 Выданные СИЗ"
        ordering = ['-issue_date', 'employee__full_name_nominative']

    def __str__(self):
        return f"{self.siz} - {self.employee} ({self.issue_date})"

    def clean(self):
        """
        🧪 Валидация данных перед сохранением

        Проверки:
        - Если СИЗ возвращено, должна быть указана дата возврата
        - Дата возврата не может быть раньше даты выдачи
        - Процент износа не может быть больше 100
        """
        if self.is_returned and not self.return_date:
            raise ValidationError({
                'return_date': 'Если СИЗ возвращено, необходимо указать дату возврата'
            })

        if self.return_date and self.issue_date and self.return_date < self.issue_date:
            raise ValidationError({
                'return_date': 'Дата возврата не может быть раньше даты выдачи'
            })

        if self.wear_percentage > 100:
            raise ValidationError({
                'wear_percentage': 'Процент износа не может быть больше 100'
            })

    def save(self, *args, **kwargs):
        """
        💾 Переопределение метода сохранения

        - Автоматически вычисляет дату замены на основе срока носки СИЗ
        - Выполняет валидацию перед сохранением
        """
        # Если дата замены не указана, вычисляем на основе срока носки
        if not self.replacement_date and self.siz and self.siz.wear_period > 0 and self.issue_date:
            wear_period_days = self.siz.wear_period * 30  # Примерное количество дней
            self.replacement_date = self.issue_date + timedelta(days=wear_period_days)

        # Выполняем валидацию
        self.clean()

        super().save(*args, **kwargs)

    @property
    def days_until_replacement(self):
        """
        📅 Возвращает количество дней до замены СИЗ

        Returns:
            int или None: Количество дней до замены или None, если "До износа"
        """
        if self.is_returned or not self.replacement_date:
            return None

        today = timezone.now().date()
        return (self.replacement_date - today).days if self.replacement_date > today else 0

    @property
    def status(self):
        """
        🔄 Возвращает текущий статус выданного СИЗ

        Returns:
            str: Статус СИЗ (В использовании, Возвращено, Требует замены, и т.д.)
        """
        if self.is_returned:
            return "Возвращено"

        days = self.days_until_replacement
        if days is not None and days <= 0:
            return "Требует замены"

        if self.wear_percentage >= 80:
            return "Сильный износ"
        elif self.wear_percentage >= 50:
            return "Средний износ"

        return "В использовании"