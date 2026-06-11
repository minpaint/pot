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
from urllib.parse import quote
import os

# ВАЖНО: Регистрируем кастомные admin URLs ДО определения urlpatterns
# Это гарантирует, что monkey-patching применится до создания URLResolver
from directory.admin.global_import_admin import register_global_import_export
from directory.admin.registry_import_admin import register_registry_import
from directory.admin.system_admin import register_system_tools

register_global_import_export(admin.site)
register_registry_import(admin.site)
register_system_tools(admin.site)


def protected_media(request, path):
    """
    Отдаёт media-файлы только авторизованным пользователям.

    Без этой защиты весь MEDIA_ROOT (медосмотры, протоколы, удостоверения,
    шаблоны) был доступен анонимно по угадываемым путям — утечка ПДн.

    Правила доступа (см. directory.utils.media_access.can_access_media):
      - quiz/* — по логину ИЛИ токен-режиму экзамена (exam.* поддомен);
      - файлы с ПДн (medical_referrals/medical_certificates/generated_documents) —
        только если организация связанного сотрудника доступна пользователю
        (горизонтальная изоляция между организациями);
      - generation_jobs/* — только владельцу задачи;
      - document_templates/* и прочее — любому аутентифицированному.

    Запрет отдаём как 404 (а не 403), чтобы не подтверждать существование файла.
    """
    from directory.utils.media_access import can_access_media

    if not can_access_media(request, path):
        raise Http404()

    # В production файл отдаёт сам nginx по внутреннему редиректу (X-Accel-Redirect),
    # чтобы не гонять байты через gunicorn-воркеры. В dev (без nginx) — serve напрямую.
    if getattr(settings, 'MEDIA_X_ACCEL_REDIRECT', False):
        prefix = getattr(settings, 'MEDIA_X_ACCEL_PREFIX', '/protected_media/')
        response = HttpResponse()
        # Пусть nginx сам определит Content-Type/Content-Length из internal-location.
        response['Content-Type'] = ''
        response['X-Accel-Redirect'] = prefix + quote(path)
        return response

    return serve(request, path, document_root=settings.MEDIA_ROOT)


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

# Обслуживание media файлов для ВСЕХ доменов (включая exam.localhost).
# ВАЖНО: только через protected_media (проверка авторизации), НЕ напрямую serve,
# иначе весь MEDIA_ROOT (ПДн, медосмотры, документы) доступен анонимно.
media_prefix = settings.MEDIA_URL.lstrip('/').rstrip('/')
if media_prefix:
    urlpatterns += [
        re_path(rf'^{media_prefix}/(?P<path>.*)$', protected_media),
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
