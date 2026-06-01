# -*- coding: utf-8 -*-
from django.db import models
from django.contrib.auth import get_user_model
from django.utils import timezone

User = get_user_model()

PRIORITY_CHOICES = [
    ('high',   '🔴 Высокий'),
    ('normal', '🟡 Обычный'),
    ('low',    '🟢 Низкий'),
]

PRIORITY_ORDER = {'high': 0, 'normal': 1, 'low': 2}


class TaskList(models.Model):
    """Список задач, привязанный к организации."""
    organization = models.ForeignKey(
        'directory.Organization',
        on_delete=models.CASCADE,
        related_name='task_lists',
        verbose_name='Организация',
    )
    title = models.CharField('Название', max_length=200)
    color = models.CharField(
        'Цвет', max_length=7, default='#3498db',
        help_text='HEX-цвет заголовка списка, например #3498db',
    )
    created_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='created_task_lists', verbose_name='Создал',
    )
    created_at = models.DateTimeField('Создан', auto_now_add=True)
    is_archived = models.BooleanField('Архивирован', default=False)

    class Meta:
        verbose_name = 'Список задач'
        verbose_name_plural = 'Списки задач'
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.title} ({self.organization.short_name_ru})'

    @property
    def done_count(self):
        return self.items.filter(is_done=True).count()

    @property
    def total_count(self):
        return self.items.count()

    @property
    def overdue_count(self):
        today = timezone.now().date()
        return self.items.filter(is_done=False, due_date__lt=today).count()


class TaskItem(models.Model):
    """Задача внутри списка."""
    task_list = models.ForeignKey(
        TaskList, on_delete=models.CASCADE,
        related_name='items', verbose_name='Список',
    )
    text = models.CharField('Задача', max_length=500)
    is_done = models.BooleanField('Выполнена', default=False)
    priority = models.CharField(
        'Приоритет', max_length=10,
        choices=PRIORITY_CHOICES, default='normal',
    )
    due_date = models.DateField('Срок', null=True, blank=True)
    done_at = models.DateTimeField('Выполнена в', null=True, blank=True)
    order = models.PositiveIntegerField('Порядок', default=0)

    class Meta:
        verbose_name = 'Задача'
        verbose_name_plural = 'Задачи'
        ordering = ['is_done', 'order', 'due_date']

    def __str__(self):
        return self.text

    @property
    def is_overdue(self):
        if self.is_done or not self.due_date:
            return False
        return self.due_date < timezone.now().date()
