# Архитектура развёртывания через CWP

## Обзор инфраструктуры

Проект **OT_online (pot.by)** развёрнут в двухуровневой архитектуре с использованием CentOS Web Panel (CWP) в качестве фронтального прокси-сервера.

```
┌─────────────────────────────────────────────────┐
│ Интернет                                        │
│ Внешние запросы: https://pot.by                 │
└────────────────┬────────────────────────────────┘
                 │ HTTPS (порт 443)
                 ↓
┌─────────────────────────────────────────────────┐
│ CWP Server (192.168.37.55)                      │
│ ┌─────────────────────────────────────────────┐ │
│ │ Nginx/Apache (фронтальный веб-сервер)       │ │
│ │ - SSL терминация (Let's Encrypt)            │ │
│ │ - HTTPS редиректы (HTTP → HTTPS)            │ │
│ │ - Domain redirects (www → pot.by)           │ │
│ │ - Security headers (HSTS, CSP, X-Frame)     │ │
│ │ - Rate limiting                             │ │
│ └─────────────────────────────────────────────┘ │
└────────────────┬────────────────────────────────┘
                 │ HTTP (внутренняя сеть)
                 │ X-Forwarded-For, X-Forwarded-Proto
                 ↓
┌─────────────────────────────────────────────────┐
│ Django Server (192.168.37.10)                   │
│ ┌─────────────────────────────────────────────┐ │
│ │ Nginx (локальный reverse proxy) :80         │ │
│ │   ↓                                         │ │
│ │ Gunicorn (WSGI server) :8020                │ │
│ │   ↓                                         │ │
│ │ Django Application (OT_online)              │ │
│ └─────────────────────────────────────────────┘ │
│ PostgreSQL :5432 (локально)                     │
│ Redis :6379 (кеширование)                       │
└─────────────────────────────────────────────────┘
```

## Сетевая конфигурация

### IP адреса

| Сервер | IP адрес | Назначение |
|--------|----------|------------|
| CWP Server | 192.168.37.55 | Фронтальный прокси, SSL терминация |
| Django Server | 192.168.37.10 | Backend приложение |

### Порты

| Сервер | Порт | Протокол | Доступ |
|--------|------|----------|--------|
| CWP | 443 | HTTPS | Внешний (интернет) |
| CWP | 80 | HTTP | Внешний (редирект на HTTPS) |
| CWP | 2087 | HTTPS | Панель управления CWP |
| Django | 8020 | HTTP | Внутренний (только от CWP) |
| Django | 5432 | PostgreSQL | Локально |
| Django | 6379 | Redis | Локально |

### Firewall правила

**На CWP сервере:**
- ✅ Открыт порт 443 (HTTPS)
- ✅ Открыт порт 80 (HTTP, с редиректом)
- ✅ Открыт порт 2087 (CWP панель)

**На Django сервере:**
- ❌ Порт 8020 закрыт для внешнего доступа
- ✅ Порт 8020 доступен только из внутренней сети (192.168.37.0/24)
- ❌ PostgreSQL 5432 доступен только локально (127.0.0.1)
- ❌ Redis 6379 доступен только локально (127.0.0.1)

## Настройки безопасности

### На уровне CWP (192.168.37.55)

CWP обеспечивает первый уровень безопасности:

1. **SSL/TLS**
   - Let's Encrypt сертификаты для pot.by, www.pot.by, exam.pot.by
   - Автоматическое обновление сертификатов
   - TLS 1.2+ only

2. **HTTP Security Headers**
   ```nginx
   Strict-Transport-Security: max-age=31536000
   X-Frame-Options: DENY
   X-Content-Type-Options: nosniff
   X-XSS-Protection: 1; mode=block
   Referrer-Policy: same-origin
   ```

3. **Редиректы**
   - HTTP → HTTPS (301)
   - www.pot.by → pot.by (301)

4. **Rate Limiting** (если настроено в CWP)

5. **Блокировка по IP** (если требуется)

### На уровне Django (192.168.37.10)

Django работает за прокси и обеспечивает второй уровень безопасности:

1. **Django Security Settings** (`settings_prod.py`)
   ```python
   # SSL обрабатывается CWP, между CWP и Django - HTTP
   SECURE_SSL_REDIRECT = False  # Редирект делает CWP
   SESSION_COOKIE_SECURE = True  # Cookies только через HTTPS
   CSRF_COOKIE_SECURE = True
   SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
   ```

2. **ALLOWED_HOSTS**
   ```python
   ALLOWED_HOSTS = ['pot.by', 'www.pot.by', 'exam.pot.by',
                    '192.168.37.10', '192.168.37.55']
   ```
   - Домены для публичного доступа
   - IP адреса для внутренней маршрутизации

3. **CSRF Protection**
   ```python
   CSRF_TRUSTED_ORIGINS = ['https://pot.by', 'https://www.pot.by',
                           'https://exam.pot.by']
   ```

4. **Application-level security**
   - Аутентификация пользователей
   - Авторизация на уровне модели
   - Валидация данных
   - Anti-CSRF токены
   - Защита от SQL injection (Django ORM)
   - Защита от XSS (Django templates)

## Конфигурация Nginx на Django сервере

Nginx на Django сервере работает как локальный reverse proxy.

**Файл:** `/etc/nginx/sites-enabled/pot.by`

```nginx
# Основной домен
server {
    listen 80;
    server_name pot.by www.pot.by 192.168.37.10;

    client_max_body_size 50M;

    location /static/ {
        alias /home/django/webapps/potby/staticfiles/;
        expires 30d;
        add_header Cache-Control "public, immutable";
    }

    location /media/ {
        alias /home/django/webapps/potby/media/;
        expires 7d;
    }

    location / {
        proxy_pass http://192.168.37.10:8020;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}

# Exam поддомен
server {
    listen 80;
    server_name exam.pot.by;

    # ... аналогичная конфигурация ...

    add_header X-Robots-Tag "noindex, nofollow, noarchive" always;
}
```

**Важно:** Nginx слушает порт 80, а не 443, так как HTTPS терминация происходит на CWP.

## Конфигурация Gunicorn

**Команда запуска:**
```bash
/home/django/webapps/potby/venv/bin/gunicorn \
    --workers 3 \
    --bind 192.168.37.10:8020 \
    --timeout 120 \
    --access-logfile /home/django/webapps/potby/logs/gunicorn.access.log \
    --error-logfile /home/django/webapps/potby/logs/gunicorn.error.log \
    wsgi:application
```

**Параметры:**
- `--workers 3` - количество worker процессов (рекомендуется: 2-4 × CPU cores)
- `--bind 192.168.37.10:8020` - слушаем на внутреннем IP
- `--timeout 120` - таймаут для длительных операций (генерация документов)

## Логи

### Gunicorn
- **Access log:** `/home/django/webapps/potby/logs/gunicorn.access.log`
- **Error log:** `/home/django/webapps/potby/logs/gunicorn.error.log`

**Пример записи в access log:**
```
192.168.37.55 - - [29/Dec/2025:16:27:49 +0300] "GET /admin/ HTTP/1.0" 200 35985
```
Обратите внимание: все запросы приходят от IP **192.168.37.55** (CWP server).

### Django
- **Application log:** настраивается в `settings_prod.py`

### Nginx (локальный)
- **Access log:** `/var/log/nginx/access.log`
- **Error log:** `/var/log/nginx/error.log`

### CWP
- Логи на CWP сервере (192.168.37.55), доступны через панель управления

## Деплой и обновление

### Обновление кода

```bash
cd /home/django/webapps/potby
git pull origin main

# Активировать виртуальное окружение
source venv/bin/activate

# Обновить зависимости (если изменились)
pip install -r requirements.txt

# Применить миграции
python manage.py migrate --settings=settings_prod

# Собрать статику
python manage.py collectstatic --noinput --settings=settings_prod

# Перезапустить Gunicorn
kill -HUP $(ps aux | grep "[g]unicorn.*potby" | grep master | awk '{print $2}')
```

### Перезапуск сервисов

**Gunicorn:**
```bash
# Graceful reload (без даунтайма)
kill -HUP $(pgrep -f "gunicorn.*potby" | head -1)

# Полный перезапуск
pkill -f "gunicorn.*potby"
# Затем запустить заново
```

**Nginx (локальный):**
```bash
sudo systemctl reload nginx
# или
sudo nginx -s reload
```

**CWP:** Управление через панель CWP на 192.168.37.55:2087

## Мониторинг

### Проверка доступности

```bash
# Проверить основной сайт
curl -I https://pot.by

# Проверить файл верификации
curl https://pot.by/yandex_e29c8fbc01012d21.html

# Проверить заголовки безопасности
curl -I https://pot.by | grep -i "strict-transport\|x-frame"
```

### Проверка процессов

```bash
# Gunicorn процессы
ps aux | grep gunicorn | grep potby

# Nginx
systemctl status nginx

# PostgreSQL
systemctl status postgresql

# Redis
systemctl status redis
```

### Проверка портов

```bash
# Что слушает на сервере
netstat -tlnp | grep -E ":8020|:5432|:6379"
```

## Troubleshooting

### Проблема: 404 с отображением IP в пути

**Симптом:** Django показывает 404 с `'path': 'some_file.html'` и `'tried': [...]`

**Причина:** Запрос пришёл с неправильным заголовком Host или путь не обрабатывается Django.

**Решение:**
1. Проверить, что CWP правильно передаёт заголовок Host
2. Убедиться, что IP адреса CWP и Django в ALLOWED_HOSTS
3. Добавить обработчик для статических файлов в urls.py (если нужно)

### Проблема: CSRF ошибки

**Причина:** Неправильная конфигурация CSRF_TRUSTED_ORIGINS

**Решение:**
```python
CSRF_TRUSTED_ORIGINS = ['https://pot.by', 'https://www.pot.by', 'https://exam.pot.by']
```

### Проблема: Static files не загружаются

**Решение:**
```bash
python manage.py collectstatic --noinput --settings=settings_prod
sudo systemctl reload nginx
```

### Проблема: Gunicorn не перезапускается

**Решение:**
```bash
# Найти PID master процесса
ps aux | grep gunicorn | grep potby | grep master

# Отправить сигнал HUP
kill -HUP <PID>

# Если не помогло - полный перезапуск
pkill -f "gunicorn.*potby"
# Запустить заново через systemd или вручную
```

## Важные замечания

1. **Не блокировать внутренние IP:**
   - 192.168.37.10 и 192.168.37.55 должны быть в ALLOWED_HOSTS
   - Это внутренние адреса, недоступные извне

2. **Не включать SECURE_SSL_REDIRECT в Django:**
   - SSL обрабатывает CWP
   - Между CWP и Django идёт HTTP трафик
   - Редирект на HTTPS делает CWP

3. **Безопасность обеспечивается на двух уровнях:**
   - CWP: SSL, HSTS, security headers, rate limiting
   - Django: CSRF, аутентификация, авторизация, валидация

4. **Логи показывают IP CWP сервера:**
   - В логах Django все запросы от 192.168.37.55
   - Реальный IP клиента в заголовке X-Forwarded-For

5. **Конфигурация Nginx на Django сервере:**
   - Слушает порт 80 (не 443)
   - Принимает запросы от CWP
   - Проксирует на Gunicorn

## См. также

- [DEPLOYMENT.md](DEPLOYMENT.md) - Общее руководство по развёртыванию
- [SECURITY_GUIDE.md](SECURITY_GUIDE.md) - Руководство по безопасности
- [PROJECT_DESCRIPTION.md](PROJECT_DESCRIPTION.md) - Описание проекта
