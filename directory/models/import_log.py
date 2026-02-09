"""
📜 Модель для хранения истории импортов

Позволяет отслеживать импорты и откатывать созданные объекты.
"""
from django.db import models
from django.conf import settings


class ImportLog(models.Model):
    """
    📋 Лог импорта данных

    Хранит информацию о каждом импорте для возможности отката.
    Упрощённая версия: только удаление созданных объектов.
    """

    IMPORT_TYPE_CHOICES = [
        ('global', 'Единый импорт'),
        ('registry', 'Реестр сотрудников'),
        ('quiz', 'Вопросы экзаменов'),
    ]

    STATUS_CHOICES = [
        ('success', 'Успешно'),
        ('rolled_back', 'Откачен'),
        ('partial', 'Частично откачен'),
    ]

    # Основная информация
    import_type = models.CharField(
        'Тип импорта',
        max_length=20,
        choices=IMPORT_TYPE_CHOICES,
        default='global'
    )
    organization = models.ForeignKey(
        'directory.Organization',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name='Организация'
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        verbose_name='Выполнил'
    )
    created_at = models.DateTimeField('Дата импорта', auto_now_add=True)
    status = models.CharField(
        'Статус',
        max_length=20,
        choices=STATUS_CHOICES,
        default='success'
    )

    # Статистика импорта
    total_created = models.PositiveIntegerField('Создано объектов', default=0)
    total_updated = models.PositiveIntegerField('Обновлено объектов', default=0)
    total_errors = models.PositiveIntegerField('Ошибок', default=0)

    # Данные для отката (JSON с ID созданных объектов)
    # Формат: {"Position": [1, 2, 3], "Employee": [10, 11], "Equipment": [100]}
    created_objects = models.JSONField(
        'Созданные объекты',
        default=dict,
        blank=True,
        help_text='ID созданных объектов по моделям'
    )

    # Информация об откате
    rolled_back_at = models.DateTimeField('Дата отката', null=True, blank=True)
    rolled_back_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='rollback_logs',
        verbose_name='Откатил'
    )
    rollback_details = models.TextField(
        'Детали отката',
        blank=True,
        help_text='Что было удалено при откате'
    )

    class Meta:
        verbose_name = 'Лог импорта'
        verbose_name_plural = 'Логи импортов'
        ordering = ['-created_at']

    def __str__(self):
        org_name = self.organization.short_name_ru if self.organization else 'Все организации'
        return f'{self.get_import_type_display()} - {org_name} - {self.created_at.strftime("%d.%m.%Y %H:%M")}'

    @property
    def can_rollback(self):
        """Можно ли откатить этот импорт"""
        return self.status == 'success' and self.total_created > 0

    def get_created_count_by_model(self):
        """Возвращает количество созданных объектов по моделям"""
        return {
            model: len(ids)
            for model, ids in self.created_objects.items()
        }
