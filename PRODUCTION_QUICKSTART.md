# Production Quick Start - pot.by

## 🚀 Управление сервером

### Запуск
```bash
cd /home/django/webapps/potby
./start_gunicorn.sh
```

### Перезагрузка (graceful, без даунтайма)
```bash
./reload_gunicorn.sh
```

### Остановка
```bash
./stop_gunicorn.sh
```

## 🔍 Проверки

### Проверка безопасности
```bash
DJANGO_SETTINGS_MODULE=settings_prod venv/bin/python \
    utility_scripts/check_debug_status.py
```

### Проверка процессов
```bash
ps aux | grep gunicorn | grep potby
```

### Проверка логов
```bash
# Access log
tail -f logs/gunicorn.access.log

# Error log
tail -f logs/gunicorn.error.log
```

## 📦 Деплой изменений

```bash
cd /home/django/webapps/potby

# 1. Получить изменения
git pull

# 2. Обновить зависимости (если изменились)
source venv/bin/activate
pip install -r requirements.txt

# 3. Применить миграции
python manage.py migrate --settings=settings_prod

# 4. Собрать статику
python manage.py collectstatic --noinput --settings=settings_prod

# 5. Перезапустить сервер (graceful reload)
./reload_gunicorn.sh
```

## ⚠️ Критические правила

1. **НИКОГДА не включайте DEBUG в production!**
   - DEBUG = False гарантирован в настройках
   - start_gunicorn.sh проверяет перед запуском

2. **Всегда используйте settings_prod**
   - По умолчанию в wsgi.py
   - Явно установлено в start_gunicorn.sh

3. **Проверяйте безопасность после изменений**
   ```bash
   ./utility_scripts/check_debug_status.py
   ```

## 🔒 Безопасность

- ✅ DEBUG = False (жёстко установлено)
- ✅ HTTPS через CWP сервер
- ✅ HSTS заголовки
- ✅ CSRF защита
- ✅ Secure cookies
- ✅ Кастомные страницы ошибок
- ✅ PostgreSQL
- ✅ Redis кеширование

## 📚 Документация

- [DEBUG_MODE_FIX.md](docs/DEBUG_MODE_FIX.md) - Исправление DEBUG режима
- [CWP_ARCHITECTURE.md](docs/CWP_ARCHITECTURE.md) - Архитектура развёртывания
- [SECURITY_GUIDE.md](docs/SECURITY_GUIDE.md) - Безопасность
- [DEPLOYMENT.md](docs/DEPLOYMENT.md) - Развёртывание

## 🆘 Помощь

### Сервер не запускается
```bash
# Проверить логи ошибок
tail -50 logs/gunicorn.error.log

# Проверить настройки
DJANGO_SETTINGS_MODULE=settings_prod venv/bin/python manage.py check
```

### 500 ошибка на сайте
```bash
# Смотреть логи в реальном времени
tail -f logs/gunicorn.error.log
```

### Изменения не применяются
```bash
# Полный перезапуск
./stop_gunicorn.sh
./start_gunicorn.sh
```
