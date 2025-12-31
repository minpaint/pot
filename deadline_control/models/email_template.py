# deadline_control/models/email_template.py

from django.db import models
from django_ckeditor_5.fields import CKEditor5Field
from directory.models import Organization


class EmailTemplateType(models.Model):
    """
    📑 Типы шаблонов писем (справочник)

    Определяет типы уведомлений, которые могут быть отправлены:
    - Образец журнала инструктажей
    - Уведомление о медосмотре
    - Уведомление о дедлайне
    и т.д.
    """

    name = models.CharField(
        max_length=100,
        unique=True,
        verbose_name="Название типа",
        help_text="Например: 'Образец журнала инструктажей'"
    )

    code = models.CharField(
        max_length=50,
        unique=True,
        verbose_name="Код типа",
        help_text="Уникальный код для использования в коде (например: 'instruction_journal')"
    )

    description = models.TextField(
        blank=True,
        verbose_name="Описание",
        help_text="Описание назначения этого типа шаблона"
    )

    available_variables = models.JSONField(
        default=dict,
        blank=True,
        verbose_name="Доступные переменные",
        help_text="JSON с доступными переменными и их описанием"
    )

    is_active = models.BooleanField(
        default=True,
        verbose_name="Активен"
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Дата создания"
    )

    updated_at = models.DateTimeField(
        auto_now=True,
        verbose_name="Дата обновления"
    )

    class Meta:
        verbose_name = "📧 Вид шаблона письма"
        verbose_name_plural = "📧 Виды шаблонов"
        ordering = ['name']

    def __str__(self):
        return self.name


class EmailTemplate(models.Model):
    """
    📝 Шаблоны писем

    Хранит шаблоны писем для различных типов уведомлений
    с привязкой к организации.
    """

    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name='email_templates',
        verbose_name="Организация",
        null=True,
        blank=True,
        help_text="Организация, для которой предназначен шаблон. Если не указана, шаблон считается эталонным."
    )

    template_type = models.ForeignKey(
        EmailTemplateType,
        on_delete=models.PROTECT,
        related_name='templates',
        verbose_name="Тип шаблона"
    )

    name = models.CharField(
        max_length=255,
        verbose_name="Название шаблона",
        help_text="Произвольное название для удобства (например: 'Шаблон для ППП')"
    )

    subject = models.CharField(
        max_length=255,
        verbose_name="Тема письма",
        help_text="Тема письма. Используйте переменные в фигурных скобках: {organization_name}, {date} и т.д."
    )

    body = CKEditor5Field(
        verbose_name="Текст письма",
        config_name='email_template',
        help_text="Текст письма в формате HTML. Используйте переменные в фигурных скобках."
    )

    is_active = models.BooleanField(
        default=True,
        verbose_name="Активен",
        help_text="Только активные шаблоны используются при отправке"
    )

    is_default = models.BooleanField(
        default=False,
        verbose_name="Эталонный шаблон",
        help_text="Указывает, является ли шаблон эталонным для всех организаций. Эталонный шаблон не может быть привязан к организации."
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Дата создания"
    )

    updated_at = models.DateTimeField(
        auto_now=True,
        verbose_name="Дата обновления"
    )

    created_by = models.ForeignKey(
        'auth.User',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='created_email_templates',
        verbose_name="Создал"
    )

    class Meta:
        verbose_name = "📝 Шаблон письма"
        verbose_name_plural = "📝 Шаблоны писем"
        ordering = ['organization', 'template_type', '-is_default', 'name']
        constraints = [
            models.UniqueConstraint(
                fields=['template_type'],
                condition=models.Q(is_default=True, organization__isnull=True),
                name='email_unique_default_template_per_type'
            )
        ]

    def __str__(self):
        default_mark = " [эталонный]" if self.is_default else ""
        org_name = self.organization.short_name_ru if self.organization else "Эталон"
        return f"{org_name} - {self.template_type.name} - {self.name}{default_mark}"

    def clean(self):
        """Валидация: эталонный шаблон не может быть привязан к организации"""
        from django.core.exceptions import ValidationError
        super().clean()

        if self.is_default and self.organization:
            raise ValidationError({
                'is_default': 'Эталонный шаблон не может быть привязан к организации'
            })

    def save(self, *args, **kwargs):
        """При установке is_default=True снимаем флаг с других шаблонов"""
        if self.is_default:
            # Для эталонных шаблонов (organization=None):
            # снимаем флаг с других эталонных шаблонов этого типа
            if self.organization is None:
                EmailTemplate.objects.filter(
                    organization__isnull=True,
                    template_type=self.template_type,
                    is_default=True
                ).exclude(pk=self.pk).update(is_default=False)
            else:
                # Для организационных шаблонов:
                # снимаем флаг is_default с других шаблонов этого типа для данной организации
                EmailTemplate.objects.filter(
                    organization=self.organization,
                    template_type=self.template_type,
                    is_default=True
                ).exclude(pk=self.pk).update(is_default=False)

        super().save(*args, **kwargs)

    def get_formatted_subject(self, context):
        """Форматирует тему письма с подстановкой переменных"""
        try:
            return self.subject.format(**context)
        except KeyError as e:
            return f"Ошибка в шаблоне темы: отсутствует переменная {e}"

    def get_formatted_body(self, context):
        """Форматирует текст письма с подстановкой переменных"""
        try:
            return self.body.format(**context)
        except KeyError as e:
            return f"Ошибка в шаблоне текста: отсутствует переменная {e}"
