"""
Development settings
Используйте этот файл ТОЛЬКО для локальной разработки!

Установка: export DJANGO_SETTINGS_MODULE=settings_dev
"""
from settings import *
import os

# ⚠️ DEBUG включён ТОЛЬКО для development!
DEBUG = True

# Разрешаем все хосты в development
ALLOWED_HOSTS = ['*']

# Development база данных (SQLite)
if os.getenv('USE_SQLITE_DEV', 'False') == 'True':
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': BASE_DIR / 'db_dev.sqlite3',
        }
    }

# Django Debug Toolbar
if 'debug_toolbar' not in INSTALLED_APPS:
    INSTALLED_APPS.append('debug_toolbar')

if 'debug_toolbar.middleware.DebugToolbarMiddleware' not in MIDDLEWARE:
    MIDDLEWARE.insert(0, 'debug_toolbar.middleware.DebugToolbarMiddleware')

INTERNAL_IPS = ['127.0.0.1', 'localhost']

# Email в консоль
EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'

# Простой кеш в памяти
CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
    }
}

print("🔧 DEVELOPMENT MODE: DEBUG=True")
print("⚠️  НЕ ИСПОЛЬЗУЙТЕ В PRODUCTION!")
