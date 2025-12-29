#!/usr/bin/env python3
"""
Скрипт проверки статуса DEBUG в production
"""
import os
import sys
import django

# Настройка Django
sys.path.insert(0, '/home/django/webapps/potby')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'settings_prod')
django.setup()

from django.conf import settings

print("=" * 60)
print("🔍 ПРОВЕРКА НАСТРОЕК БЕЗОПАСНОСТИ DJANGO")
print("=" * 60)
print()

# 1. DEBUG
print("1. DEBUG режим:")
if settings.DEBUG:
    print("   ❌ ОПАСНО! DEBUG = True")
    print("   ⚠️  Техническая информация видна всем!")
    print("   🔧 Исправьте: DJANGO_DEBUG=False в .env")
else:
    print("   ✅ DEBUG = False (правильно)")
print()

# 2. ALLOWED_HOSTS
print("2. ALLOWED_HOSTS:")
if settings.ALLOWED_HOSTS == ['*']:
    print("   ❌ ОПАСНО! Разрешены все хосты")
    print("   🔧 Укажите конкретные домены")
else:
    print(f"   ✅ Настроено: {', '.join(settings.ALLOWED_HOSTS)}")
print()

# 3. SECRET_KEY
print("3. SECRET_KEY:")
if settings.SECRET_KEY == 'django-insecure-' or len(settings.SECRET_KEY) < 50:
    print("   ❌ ОПАСНО! Слабый SECRET_KEY")
else:
    print("   ✅ SECRET_KEY настроен (50+ символов)")
print()

# 4. CSRF
print("4. CSRF защита:")
if hasattr(settings, 'CSRF_TRUSTED_ORIGINS'):
    print(f"   ✅ CSRF_TRUSTED_ORIGINS: {', '.join(settings.CSRF_TRUSTED_ORIGINS)}")
else:
    print("   ⚠️  CSRF_TRUSTED_ORIGINS не настроено")
print()

# 5. Cookies безопасность
print("5. Cookies безопасность:")
print(f"   SESSION_COOKIE_SECURE: {'✅' if settings.SESSION_COOKIE_SECURE else '❌'} {settings.SESSION_COOKIE_SECURE}")
print(f"   CSRF_COOKIE_SECURE: {'✅' if settings.CSRF_COOKIE_SECURE else '❌'} {settings.CSRF_COOKIE_SECURE}")
print(f"   SESSION_COOKIE_HTTPONLY: {'✅' if settings.SESSION_COOKIE_HTTPONLY else '❌'} {settings.SESSION_COOKIE_HTTPONLY}")
print()

# 6. SSL
print("6. SSL настройки:")
print(f"   SECURE_SSL_REDIRECT: {settings.SECURE_SSL_REDIRECT}")
if hasattr(settings, 'SECURE_PROXY_SSL_HEADER'):
    print(f"   ✅ SECURE_PROXY_SSL_HEADER настроено (работа за прокси)")
print()

# 7. Database
print("7. База данных:")
db_engine = settings.DATABASES['default']['ENGINE']
if 'sqlite3' in db_engine:
    print("   ⚠️  SQLite (подходит для разработки)")
elif 'postgresql' in db_engine:
    print("   ✅ PostgreSQL (production)")
else:
    print(f"   ℹ️  {db_engine}")
print()

# 8. Static files
print("8. Static files:")
if settings.DEBUG:
    print("   ⚠️  DEBUG=True, статика раздаётся Django")
else:
    print(f"   ✅ STATIC_ROOT: {settings.STATIC_ROOT}")
print()

# 9. Error handlers
print("9. Обработчики ошибок:")
from django.conf.urls import handler404, handler500
if handler404:
    print(f"   ✅ handler404 настроен")
if handler500:
    print(f"   ✅ handler500 настроен")
print()

# Итог
print("=" * 60)
if settings.DEBUG:
    print("❌ КРИТИЧНО: DEBUG включён! Отключите немедленно!")
    sys.exit(1)
elif settings.ALLOWED_HOSTS == ['*']:
    print("⚠️  ВНИМАНИЕ: Есть проблемы безопасности")
    sys.exit(1)
else:
    print("✅ Основные настройки безопасности в порядке")
    sys.exit(0)
