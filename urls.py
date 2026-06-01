from django.contrib import admin
from django.urls import path, include, re_path
from django.conf import settings
from django.conf.urls.static import static
from django.views.static import serve
from django.http import HttpResponse, Http404
from directory.error_handlers import error_400, error_403, error_404, error_500
# Главная страница - обновлённый HomePageView с дашбордом
from directory.views.home import HomePageView
# Импортируем AJAX view для древовидных представлений
from directory.views.admin_tree_ajax import load_tree_children
import os

# ВАЖНО: Регистрируем кастомные admin URLs ДО определения urlpatterns
# Это гарантирует, что monkey-patching применится до создания URLResolver
from directory.admin.global_import_admin import register_global_import_export
from directory.admin.registry_import_admin import register_registry_import
from directory.admin.system_admin import register_system_tools

register_global_import_export(admin.site)
register_registry_import(admin.site)
register_system_tools(admin.site)


def debug_headers(request):
    """Временный endpoint для диагностики CSRF проблем"""
    headers_info = []
    headers_info.append(f"REQUEST METHOD: {request.method}")
    headers_info.append(f"is_secure(): {request.is_secure()}")
    headers_info.append(f"scheme: {request.scheme}")
    headers_info.append("")
    headers_info.append("=== META headers ===")
    for key, value in sorted(request.META.items()):
        if key.startswith('HTTP_') or key in ('REMOTE_ADDR', 'SERVER_NAME', 'SERVER_PORT'):
            headers_info.append(f"{key}: {value}")
    return HttpResponse("\n".join(headers_info), content_type="text/plain")


def serve_verification_file(request, filename):
    """
    Обработчик для файлов верификации поисковых систем и других сервисов
    (yandex_*.html, google*.html, robots.txt и т.д.)
    """
    file_path = os.path.join(settings.BASE_DIR, filename)

    if os.path.exists(file_path) and os.path.isfile(file_path):
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()

        # Определяем content type
        if filename.endswith('.html'):
            content_type = 'text/html; charset=utf-8'
        elif filename == 'robots.txt':
            content_type = 'text/plain; charset=utf-8'
        else:
            content_type = 'text/plain; charset=utf-8'

        return HttpResponse(content, content_type=content_type)

    raise Http404(f"Файл {filename} не найден")


urlpatterns = [
    # Диагностика заголовков (ВРЕМЕННО для отладки CSRF)
    path('debug-headers/', debug_headers, name='debug_headers'),

    # Главная страница - дашборд + быстрый доступ + статистика + сотрудники
    path('', HomePageView.as_view(), name='home'),

    # Admin actions для EmployeeHiring (ВАЖНО: ПЕРЕД admin.site.urls!)
    path('admin/hiring/', include('directory.urls_admin_hiring')),

    # AJAX endpoints для древовидных представлений (ВАЖНО: ПЕРЕД admin.site.urls!)
    path('admin/directory/ajax/tree-children/<str:model_name>/<str:parent_type>/<int:parent_id>/',
         load_tree_children,
         name='admin_tree_ajax_children'),

    # 👨‍💼 Админка Django
    path('admin/', admin.site.urls),

    # 📂 URL приложения directory (включая автодополнение)
    # Ключевое исправление - указываем непосредственно модуль, а не строку
    path('directory/', include('directory.urls')),

    # 💼 Договоры и акты (только для суперпользователя)
    path('contracts/', include('contracts.urls')),

    # 🕐 URL приложения deadline_control (Контроль сроков)
    path('deadline-control/', include('deadline_control.urls')),

    # 🎓 Обучение на производстве
    path('production-training/', include('production_training.urls')),

    # ✅ Задачи (AJAX-эндпоинты для TODO-виджета)
    path('tasks/', include('tasks.urls')),

    # ✍️ CKEditor 5 URL
    path('ckeditor5/', include('django_ckeditor_5.urls')),

    # 🔍 Файлы верификации поисковых систем
    re_path(r'^(?P<filename>yandex_[a-f0-9]+\.html)$', serve_verification_file, name='yandex_verification'),
    re_path(r'^(?P<filename>google[a-f0-9]+\.html)$', serve_verification_file, name='google_verification'),
    path('robots.txt', serve_verification_file, {'filename': 'robots.txt'}, name='robots'),
]

# Обслуживание media файлов для ВСЕХ доменов (включая exam.localhost)
# Используем django.views.static.serve, так как проект работает без внешнего веб-сервера для media.
media_prefix = settings.MEDIA_URL.lstrip('/').rstrip('/')
if media_prefix:
    urlpatterns += [
        re_path(rf'^{media_prefix}/(?P<path>.*)$', serve, {
            'document_root': settings.MEDIA_ROOT,
        }),
    ]

# Настройки для режима разработки
if settings.DEBUG:
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)

    if 'debug_toolbar' in settings.INSTALLED_APPS:
        import debug_toolbar

        urlpatterns.append(path('__debug__/', include(debug_toolbar.urls)))

# Кастомизация админки
admin.site.site_header = '🏢 Система управления ОТ'
admin.site.site_title = '🎛️ Панель управления'
admin.site.index_title = '⚙️ Управление системой'

# Обработчики ошибок
handler400 = error_400
handler403 = error_403
handler404 = error_404
handler500 = error_500
