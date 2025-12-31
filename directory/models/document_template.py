# directory/models/document_template.py
import os
from django.db import models
from django.core.exceptions import ValidationError
from django.core.files.storage import FileSystemStorage
from django.utils.translation import gettext_lazy as _
from django.conf import settings

# Настраиваем хранилище для файлов шаблонов: файлы будут сохраняться в MEDIA_ROOT/document_templates,
# а URL для доступа к ним будет /media/document_templates/
document_storage = FileSystemStorage(
    location=os.path.join(settings.MEDIA_ROOT, 'document_templates'),
    base_url=os.path.join(settings.MEDIA_URL, 'document_templates/')
)

class DocumentTemplateType(models.Model):
    """
    📑 Виды шаблонов документов (справочник)
    """

    name = models.CharField(
        max_length=100,
        unique=True,
        verbose_name="Название вида",
        help_text="Например: '🛡️ Карточка учета СИЗ'"
    )

    code = models.CharField(
        max_length=50,
        unique=True,
        verbose_name="Код вида",
        help_text="Код для использования в коде (например: 'siz_card')"
    )

    description = models.TextField(
        blank=True,
        verbose_name="Описание",
        help_text="Описание назначения данного вида шаблона"
    )

    is_active = models.BooleanField(
        default=True,
        verbose_name="Активен"
    )
    show_in_hiring = models.BooleanField(
        default=True,
        verbose_name="Показывать при приеме",
        help_text="Определяет, отображается ли этот тип документа в списке для скачивания при приеме на работу"
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
        verbose_name = "📄 Вид шаблона документа"
        verbose_name_plural = "📄 Виды шаблонов документов"
        ordering = ['name']

    def __str__(self):
        return self.name


class DocumentTemplate(models.Model):
    """
    📃 Модель для хранения шаблонов документов (DOCX файлы)

    Хранит информацию о шаблонах документов, которые используются
    для генерации документов на основе данных сотрудников.
    """

    name = models.CharField(_("Название шаблона"), max_length=255)
    description = models.TextField(_("Описание"), blank=True)

    # Связь с типом документа через справочник
    document_type = models.ForeignKey(
        'DocumentTemplateType',
        on_delete=models.PROTECT,
        related_name='templates',
        verbose_name=_("Тип документа"),
        help_text=_("Выберите тип документа из справочника")
    )
    template_file = models.FileField(
        _("Файл шаблона"),
        upload_to='',  # Пустая строка, т.к. storage уже указывает на document_templates
        storage=document_storage
    )
    is_active = models.BooleanField(_("Активен"), default=True)
    created_at = models.DateTimeField(_("Дата создания"), auto_now_add=True)
    updated_at = models.DateTimeField(_("Дата обновления"), auto_now=True)

    # Привязка к организации
    organization = models.ForeignKey(
        'directory.Organization',
        on_delete=models.CASCADE,
        related_name="document_templates",
        verbose_name=_("Организация"),
        null=True,
        blank=True,
        help_text=_("Организация, для которой предназначен шаблон. Если не указана, шаблон считается эталонным.")
    )
    is_default = models.BooleanField(
        verbose_name=_("Эталонный шаблон"),
        default=False,
        help_text=_("Указывает, является ли шаблон эталонным для всех организаций")
    )

    class Meta:
        verbose_name = _("📝 Шаблон документа")
        verbose_name_plural = _("📝 Шаблоны документов")
        ordering = ['-updated_at']
        constraints = [
            models.UniqueConstraint(
                fields=['document_type'],
                condition=models.Q(is_default=True),
                name='unique_default_template_per_type'
            )
        ]

    def __str__(self):
        type_name = self.document_type.name if self.document_type else "Без типа"
        return f"{self.name} ({type_name})"

    def clean(self):
        super().clean()
        # Проверяем, что не может быть одновременно эталонным и привязанным к организации
        if self.is_default and self.organization:
            raise ValidationError(
                {'is_default': _('Эталонный шаблон не может быть привязан к организации')}
            )


class GeneratedDocument(models.Model):
    """
    📄 Модель для хранения сгенерированных документов

    Хранит информацию о документах, сгенерированных на основе шаблонов.
    """
    template = models.ForeignKey(
        DocumentTemplate,
        verbose_name=_("Шаблон"),
        on_delete=models.SET_NULL,
        null=True
    )
    document_file = models.FileField(
        _("Файл документа"),
        upload_to='generated_documents/%Y/%m/%d/'
    )
    employee = models.ForeignKey(
        'directory.Employee',
        verbose_name=_("Сотрудник"),
        on_delete=models.CASCADE,
        related_name="documents"
    )
    created_by = models.ForeignKey(
        'auth.User',
        verbose_name=_("Создан пользователем"),
        on_delete=models.SET_NULL,
        null=True,
        blank=True
    )
    created_at = models.DateTimeField(_("Дата создания"), auto_now_add=True)
    document_data = models.JSONField(
        _("Данные документа"),
        default=dict,
        blank=True,
        help_text=_("Данные, использованные для генерации документа")
    )

    class Meta:
        verbose_name = _("📄 Сгенерированный документ")
        verbose_name_plural = _("📄 Сгенерированные документы")
        ordering = ['-created_at']

    def __str__(self):
        return f"Документ для {self.employee} ({self.created_at.strftime('%d.%m.%Y')})"


class DocumentGenerationLog(models.Model):
    """
    📋 Лог генерации документов для сотрудника

    Записывает факт генерации документов без сохранения файлов.
    """
    employee = models.ForeignKey(
        'directory.Employee',
        verbose_name=_("Сотрудник"),
        on_delete=models.CASCADE,
        related_name="document_generation_logs"
    )
    document_types = models.JSONField(
        _("Типы документов"),
        default=list,
        help_text=_("Список типов сгенерированных документов")
    )
    created_by = models.ForeignKey(
        'auth.User',
        verbose_name=_("Создан пользователем"),
        on_delete=models.SET_NULL,
        null=True,
        blank=True
    )
    created_at = models.DateTimeField(_("Дата генерации"), auto_now_add=True)

    class Meta:
        verbose_name = _("📋 Лог генерации документов")
        verbose_name_plural = _("📋 Логи генерации документов")
        ordering = ['-created_at']

    def __str__(self):
        return f"Документы для {self.employee} ({self.created_at.strftime('%d.%m.%Y %H:%M')})"

    def get_document_types_display(self):
        """Возвращает читаемые названия типов документов"""
        if not self.document_types:
            return ""

        # document_types содержит список кодов типов
        types_by_code = {
            template_type.code: template_type.name
            for template_type in DocumentTemplateType.objects.all()
        }
        return ', '.join([types_by_code.get(t, t) for t in self.document_types])
