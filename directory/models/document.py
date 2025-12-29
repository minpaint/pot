from django.db import models


class Document(models.Model):
    """
    📄 Модель для хранения документов.
    Документы привязаны к организации, подразделению и отделу.
    """
    name = models.CharField("Наименование документа", max_length=255)
    organization = models.ForeignKey(
        'directory.Organization',
        on_delete=models.CASCADE,
        related_name="documents",
        verbose_name="Организация"
    )
    subdivision = models.ForeignKey(
        'directory.StructuralSubdivision',
        on_delete=models.CASCADE,
        verbose_name="Структурное подразделение",
        null=True,
        blank=True
    )
    department = models.ForeignKey(
        'directory.Department',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name="Отдел"
    )

    def __str__(self):
        return self.name

    class Meta:
        verbose_name = "📄 Документ для ознакомления"
        verbose_name_plural = "📄 Документы для ознакомления"
