# deadline_control/apps_notifications.py

from django.apps import AppConfig


class NotificationsConfig(AppConfig):
    """Конфигурация раздела 'Уведомления'"""
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'deadline_control'
    label = 'notifications'
    verbose_name = '📧 Уведомления'
