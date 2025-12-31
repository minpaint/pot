"""
🔧 Сервисные действия в админке (перезагрузка Gunicorn).

Кнопка доступна только суперпользователям, использует фиксированный скрипт
reload_gunicorn.sh и пишет результат в сообщения и лог.
"""
import logging
import subprocess
from pathlib import Path

from django.conf import settings
from django.contrib import admin, messages
from django.shortcuts import redirect, render
from django.urls import path
from django.utils.html import escape, format_html

logger = logging.getLogger(__name__)


class SystemMaintenanceAdmin:
    """Псевдо-админка для сервисных операций."""

    def __init__(self, admin_site: admin.AdminSite):
        self.admin_site = admin_site
        self.actions = {
            'reload_gunicorn': {
                'title': 'Gunicorn перезапущен.',
                'error': 'Ошибка перезапуска.',
                'script': Path(settings.BASE_DIR) / 'reload_gunicorn.sh',
            },
            'backup_db': {
                'title': 'Бэкап базы создан.',
                'error': 'Ошибка бэкапа базы.',
                'script': Path('/home/django/backups/pg_backup.sh'),
            },
            'backup_files': {
                'title': 'Бэкап файлов создан.',
                'error': 'Ошибка бэкапа файлов.',
                'script': Path('/home/django/backups/file_backup.sh'),
            },
        }

    def get_urls(self):
        return [
            path(
                'system/reload-gunicorn/',
                self.admin_site.admin_view(self.reload_gunicorn_view),
                name='reload_gunicorn',
            ),
        ]

    @staticmethod
    def _strip_ansi(output: str) -> str:
        """Убираем цветовые коды из вывода Bash."""
        import re

        return re.sub(r'\x1B\[[0-9;]*[mK]', '', output or '')

    def _execute_action(self, request, action_key: str):
        action = self.actions.get(action_key)
        if not action:
            messages.error(request, 'Неизвестное действие.')
            return False

        script_path = action['script']
        if not script_path.exists():
            messages.error(request, f'Скрипт {script_path} не найден.')
            logger.error('Script for %s not found at %s', action_key, script_path)
            return False

        logger.info('User %s requested %s via admin', request.user.username, action_key)
        try:
            result = subprocess.run(
                ['bash', str(script_path)],
                capture_output=True,
                text=True,
                check=True,
                cwd=settings.BASE_DIR,
                timeout=60,
            )
            clean_output = self._strip_ansi(result.stdout)
            messages.success(
                request,
                format_html(
                    '{}<br><pre style="white-space: pre-wrap;">{}</pre>',
                    action['title'],
                    escape(clean_output.strip() or 'Скрипт выполнен без вывода.'),
                ),
            )
            logger.info('%s completed for %s', action_key, request.user.username)
        except subprocess.CalledProcessError as exc:
            output = f'{exc.stdout or ""}\n{exc.stderr or ""}'
            clean_output = self._strip_ansi(output)
            messages.error(
                request,
                format_html(
                    '{}<br><pre style="white-space: pre-wrap;">{}</pre>',
                    action['error'],
                    escape(clean_output.strip() or str(exc)),
                ),
            )
            logger.exception('%s failed for %s', action_key, request.user.username)
        except subprocess.TimeoutExpired:
            messages.error(request, 'Операция не завершилась за отведенное время.')
            logger.exception('%s timed out for %s', action_key, request.user.username)

        return True

    def reload_gunicorn_view(self, request):
        context = self.admin_site.each_context(request)

        if not request.user.is_superuser:
            messages.error(request, 'Доступ разрешен только суперпользователям.')
            return redirect('admin:index')

        if request.method == 'POST':
            action_key = request.POST.get('action', 'reload_gunicorn')
            self._execute_action(request, action_key)
            return redirect('admin:reload_gunicorn')

        context.update({
            'title': 'Перезагрузка Gunicorn',
            'script_paths': {
                'reload_gunicorn': self.actions['reload_gunicorn']['script'],
                'backup_db': self.actions['backup_db']['script'],
                'backup_files': self.actions['backup_files']['script'],
            },
        })
        return render(request, 'admin/system/reload_gunicorn.html', context)


def register_system_tools(admin_site):
    """
    Регистрирует сервисные действия в админке.
    Вызывается до объявления urlpatterns, чтобы примешать кастомные URL.
    """
    system_admin = SystemMaintenanceAdmin(admin_site)
    original_get_urls = admin_site.get_urls

    def get_urls_with_system_tools():
        urls = original_get_urls()
        custom_urls = system_admin.get_urls()
        return custom_urls + urls

    admin_site.get_urls = get_urls_with_system_tools
