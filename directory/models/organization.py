# directory/models/organization.py

from django.db import models

class Organization(models.Model):
    """
    🏢 Модель для хранения информации об организациях.
    """
    full_name_ru = models.CharField(max_length=255, verbose_name="Полное наименование (рус)")
    short_name_ru = models.CharField(max_length=100, verbose_name="Краткое наименование (рус)")
    full_name_by = models.CharField(max_length=255, verbose_name="Полное наименование (бел)")
    short_name_by = models.CharField(max_length=100, verbose_name="Краткое наименование (бел)")
    requisites_ru = models.TextField(verbose_name="Реквизиты (рус)", blank=True)
    requisites_by = models.TextField(verbose_name="Реквизиты (бел)", blank=True)
    # Добавляем новое поле для места нахождения
    location = models.CharField(max_length=100, verbose_name="Место нахождения",
                              default="г. Минск", blank=True,
                              help_text="Например: г. Минск, г. Брест и т.д.")

    # Эталонные роли для обучения на производстве
    default_theory_consultant = models.ForeignKey(
        'Employee',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='org_default_theory_consultant',
        verbose_name="Эталонный консультант теоретического обучения",
        help_text="Будет подставляться по умолчанию при создании обучения"
    )
    default_commission_chairman = models.ForeignKey(
        'Employee',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='org_default_commission_chairman',
        verbose_name="Эталонный руководитель производственного обучения",
        help_text="Будет подставляться по умолчанию при создании обучения"
    )
    default_instructor = models.ForeignKey(
        'Employee',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='org_default_instructor',
        verbose_name="Эталонный инструктор производственного обучения",
        help_text="Будет подставляться по умолчанию при создании обучения"
    )

    class Meta:
        verbose_name = "🏢 Организация"
        verbose_name_plural = "🏢 Организации"
        ordering = ['full_name_ru']

    def __str__(self):
        return self.short_name_ru or self.full_name_ru