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

    def reload_gunicorn_view(self, request):
        context = self.admin_site.each_context(request)
        script_path = Path(settings.BASE_DIR) / 'reload_gunicorn.sh'

        if not request.user.is_superuser:
            messages.error(request, 'Доступ разрешен только суперпользователям.')
            return redirect('admin:index')

        if request.method == 'POST':
            if not script_path.exists():
                messages.error(request, f'Скрипт {script_path} не найден.')
                logger.error('Gunicorn reload script not found at %s', script_path)
                return redirect('admin:index')

            logger.info('User %s requested Gunicorn reload via admin', request.user.username)
            try:
                result = subprocess.run(
                    ['bash', str(script_path)],
                    capture_output=True,
                    text=True,
                    check=True,
                    cwd=settings.BASE_DIR,
                    timeout=30,
                )
                clean_output = self._strip_ansi(result.stdout)
                messages.success(
                    request,
                    format_html(
                        'Gunicorn перезапущен.<br><pre style="white-space: pre-wrap;">{}</pre>',
                        escape(clean_output.strip() or 'Скрипт выполнен без вывода.'),
                    ),
                )
                logger.info('Gunicorn reload completed for %s', request.user.username)
            except subprocess.CalledProcessError as exc:
                output = f'{exc.stdout or ""}\n{exc.stderr or ""}'
                clean_output = self._strip_ansi(output)
                messages.error(
                    request,
                    format_html(
                        'Ошибка перезапуска.<br><pre style="white-space: pre-wrap;">{}</pre>',
                        escape(clean_output.strip() or str(exc)),
                    ),
                )
                logger.exception('Gunicorn reload failed for %s', request.user.username)
            except subprocess.TimeoutExpired:
                messages.error(request, 'Перезагрузка не завершилась за отведенное время.')
                logger.exception('Gunicorn reload timed out for %s', request.user.username)

            return redirect('admin:reload_gunicorn')

        context.update({
            'title': 'Перезагрузка Gunicorn',
            'script_path': script_path,
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
