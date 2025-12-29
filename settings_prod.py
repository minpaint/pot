from pathlib import Path

from settings import *

# Production specific settings

DEBUG = False

# Отключаем debug toolbar в production
if 'debug_toolbar' in INSTALLED_APPS:
    INSTALLED_APPS.remove('debug_toolbar')
if 'debug_toolbar.middleware.DebugToolbarMiddleware' in MIDDLEWARE:
    MIDDLEWARE.remove('debug_toolbar.middleware.DebugToolbarMiddleware')

# It is crucial to set this to the actual domain name in production
ALLOWED_HOSTS = os.getenv('DJANGO_ALLOWED_HOSTS', 'pot.by,www.pot.by').split(',')
CSRF_TRUSTED_ORIGINS = os.getenv('CSRF_TRUSTED_ORIGINS', 'https://pot.by,https://www.pot.by').split(',')

# Security settings
# Django работает за CWP reverse proxy, который обрабатывает HTTPS
# Между CWP и Django идёт HTTP трафик внутри локальной сети
SECURE_SSL_REDIRECT = False  # Редирект делает CWP
SESSION_COOKIE_SECURE = True  # Cookies только через HTTPS
CSRF_COOKIE_SECURE = True  # CSRF cookies только через HTTPS
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')  # Доверяем CWP proxy
# HSTS заголовок добавляет CWP сервер

# Static / media in production (CWP expects collected files in webapps path)
# Keep project-level static assets (e.g. logo.png) alongside app static files.
STATICFILES_DIRS = [
    BASE_DIR / 'static',
]
# CWP layout mirrors proverka.by, collectstatic must land inside /home/django/webapps/potby
STATIC_ROOT = Path(os.getenv('STATIC_ROOT', '/home/django/webapps/potby/staticfiles'))
MEDIA_ROOT = Path(os.getenv('MEDIA_ROOT', '/home/django/webapps/potby/media'))

STORAGES = {
    'default': {
        'BACKEND': 'django.core.files.storage.FileSystemStorage',
    },
    'staticfiles': {
        'BACKEND': 'whitenoise.storage.CompressedManifestStaticFilesStorage',
    },
}

# CORS settings
CORS_ORIGIN_ALLOW_ALL = False
CORS_ALLOWED_ORIGINS = os.getenv('CORS_ALLOWED_ORIGINS', '').split(',')

# Caching
CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.redis.RedisCache',
        'LOCATION': os.getenv('REDIS_URL', 'redis://127.0.0.1:6379/1'),
        'OPTIONS': {
            'CLIENT_CLASS': 'django_redis.client.DefaultClient',
        }
    }
}

# Email settings for production
EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'

# Allow large query/post field counts (большие деревья в админке)
DATA_UPLOAD_MAX_NUMBER_FIELDS = 100000
