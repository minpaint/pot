# 🚀 Быстрое развёртывание OT_online на домашнем сервере (SQLite)

## 📌 Краткое описание

Пошаговая инструкция для развёртывания Django-проекта OT_online на домашнем Linux сервере с использованием:
- SQLite (перенос БД с локалки)
- Nginx (уже настроен)
- Gunicorn (WSGI сервер)
- systemd (автозапуск)

**Время выполнения:** 30-40 минут

---

## 🔧 Шаг 1: Подготовка сервера (выполнить на сервере)

### 1.1. Подключитесь к серверу по SSH

```bash
# С вашего локального компьютера
ssh ваш_пользователь@IP_адрес_сервера
# Например: ssh alex@192.168.1.100
```

### 1.2. Установите Git (если ещё не установлен)

```bash
# Обновляем список пакетов
sudo apt update

# Устанавливаем Git
sudo apt install -y git

# Проверяем установку
git --version
```

### 1.3. Создайте пользователя для приложения (опционально, для безопасности)

```bash
# Создаём системного пользователя
sudo useradd -m -s /bin/bash ot_user

# Добавляем в группу www-data для работы с Nginx
sudo usermod -aG www-data ot_user

# Переключаемся на этого пользователя
sudo su - ot_user
```

**Альтернатива:** Можете работать от своего пользователя, пропустив этот пункт.

---

## 📥 Шаг 2: Клонирование репозитория

### 2.1. Создайте директорию проекта

```bash
# Создаём директорию (от root или с sudo)
sudo mkdir -p /var/www/ot_online

# Даём права вашему пользователю (замените YOUR_USER на ваш логин)
sudo chown -R $USER:www-data /var/www/ot_online
sudo chmod 755 /var/www/ot_online

# Переходим в директорию
cd /var/www/ot_online
```

### 2.2. Клонируйте репозиторий из GitHub

```bash
# Клонируем репозиторий
git clone https://github.com/minpaint/OT_online.git .

# Проверяем, что файлы на месте
ls -la
```

**Должны увидеть:** manage.py, settings.py, directory/, deadline_control/, и т.д.

---

## 🐍 Шаг 3: Настройка Python окружения

### 3.1. Создайте виртуальное окружение

```bash
# Проверяем версию Python (должна быть 3.10+)
python3 --version

# Устанавливаем python3-venv, если нужно
sudo apt install -y python3-venv python3-pip

# Создаём виртуальное окружение
python3 -m venv venv

# Активируем
source venv/bin/activate

# Обновляем pip
pip install --upgrade pip
```

**Проверка:** В терминале должно появиться `(venv)` перед командной строкой.

### 3.2. Установите зависимости

```bash
# Устанавливаем все зависимости из requirements.txt
pip install -r requirements.txt

# Это займёт 5-10 минут, ждём...
```

**Важно:** Если увидите ошибки с `pywin32` - это нормально (Windows-библиотека, не нужна на Linux).

---

## ⚙️ Шаг 4: Настройка переменных окружения

### 4.1. Создайте production .env файл

```bash
# Копируем пример
cp .env.example .env

# Редактируем (используйте nano или vim)
nano .env
```

### 4.2. Заполните .env следующими значениями:

```bash
# Django Settings
DJANGO_SECRET_KEY=ЗАМЕНИТЕ_НА_СЛУЧАЙНУЮ_СТРОКУ_50_СИМВОЛОВ
DJANGO_DEBUG=False
DJANGO_ALLOWED_HOSTS=pot.by,www.pot.by,ваш_IP_адрес,localhost
DJANGO_SETTINGS_MODULE=settings

# Database (SQLite)
# Оставляем пустым, будет использоваться SQLite по умолчанию
DATABASE_URL=

# Exam Subdomain
EXAM_SUBDOMAIN=exam.pot.by
EXAM_PROTOCOL=http

# Security
CSRF_TRUSTED_ORIGINS=http://pot.by,http://www.pot.by,http://exam.pot.by

# Static/Media
STATIC_ROOT=/var/www/ot_online/staticfiles
MEDIA_ROOT=/var/www/ot_online/media

# Logging
LOG_LEVEL=INFO
```

**Генерация SECRET_KEY:**
```bash
python3 -c 'from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())'
```
Скопируйте вывод и вставьте в `DJANGO_SECRET_KEY=`

**Сохраните файл:**
- В nano: `Ctrl+O`, `Enter`, `Ctrl+X`
- В vim: `:wq`

---

## 📦 Шаг 5: Перенос базы данных и медиа-файлов

**Этот шаг выполняется с ВАШЕГО локального компьютера!**

### 5.1. Подготовьте файлы на локалке

На вашем Windows компьютере откройте PowerShell/CMD в папке проекта:

```powershell
# Переходим в папку проекта
cd "G:\Мой диск\OT_online"

# Создаём архив с БД и медиа
# Вариант 1: Используем tar (если доступен в Windows)
tar -czf transfer.tar.gz db.sqlite3 media/

# Вариант 2: Создайте ZIP архив вручную в проводнике
# Добавьте в архив: db.sqlite3 и папку media/
```

### 5.2. Загрузите на сервер

```powershell
# Загружаем архив на сервер по SCP (замените данные на свои)
scp transfer.tar.gz ваш_пользователь@IP_сервера:/var/www/ot_online/

# Например:
# scp transfer.tar.gz alex@192.168.1.100:/var/www/ot_online/
```

**Альтернатива:** Используйте WinSCP или FileZilla для загрузки файлов графически.

### 5.3. Распакуйте на сервере

Вернитесь в SSH сессию на сервере:

```bash
# Переходим в директорию проекта
cd /var/www/ot_online

# Распаковываем
tar -xzf transfer.tar.gz

# Проверяем, что файлы на месте
ls -lh db.sqlite3
ls -lh media/

# Удаляем архив
rm transfer.tar.gz

# Выставляем права
chmod 644 db.sqlite3
chmod -R 755 media/
```

---

## 🗄️ Шаг 6: Применение миграций

```bash
# Активируем venv (если не активировано)
source venv/bin/activate

# Применяем миграции (БД уже перенесена, но на всякий случай)
python manage.py migrate --noinput

# Создаём суперпользователя (если ещё нет)
# python manage.py createsuperuser

# Собираем статику
python manage.py collectstatic --noinput
```

**Проверка:** Должна появиться папка `staticfiles/` с CSS, JS, и т.д.

---

## 🚀 Шаг 7: Настройка Gunicorn как системной службы

### 7.1. Создайте файл службы

```bash
# Выходим из venv
deactivate

# Создаём systemd service файл
sudo nano /etc/systemd/system/ot_online.service
```

### 7.2. Вставьте следующее содержимое:

```ini
[Unit]
Description=OT_online Gunicorn daemon
After=network.target

[Service]
Type=notify
User=ваш_пользователь
Group=www-data
WorkingDirectory=/var/www/ot_online
Environment="PATH=/var/www/ot_online/venv/bin"
EnvironmentFile=/var/www/ot_online/.env
ExecStart=/var/www/ot_online/venv/bin/gunicorn \
    --workers 3 \
    --bind unix:/run/gunicorn/ot_online.sock \
    --timeout 60 \
    --log-level info \
    --access-logfile /var/log/ot_online/access.log \
    --error-logfile /var/log/ot_online/error.log \
    wsgi:application
ExecReload=/bin/kill -s HUP $MAINPID
KillMode=mixed
TimeoutStopSec=5
PrivateTmp=true
Restart=always

[Install]
WantedBy=multi-user.target
```

**⚠️ ВАЖНО:** Замените `ваш_пользователь` на ваш реальный логин (или `ot_user`, если создавали).

**Сохраните:** `Ctrl+O`, `Enter`, `Ctrl+X`

### 7.3. Создайте необходимые директории

```bash
# Директория для сокета gunicorn
sudo mkdir -p /run/gunicorn
sudo chown -R $USER:www-data /run/gunicorn

# Директория для логов
sudo mkdir -p /var/log/ot_online
sudo chown -R $USER:www-data /var/log/ot_online
```

### 7.4. Запустите службу

```bash
# Перезагружаем systemd
sudo systemctl daemon-reload

# Запускаем службу
sudo systemctl start ot_online

# Проверяем статус
sudo systemctl status ot_online

# Включаем автозапуск при старте системы
sudo systemctl enable ot_online
```

**Ожидаемый результат:**
```
● ot_online.service - OT_online Gunicorn daemon
   Loaded: loaded (/etc/systemd/system/ot_online.service; enabled)
   Active: active (running) since ...
```

**Если ошибка:**
```bash
# Смотрим логи
sudo journalctl -u ot_online -n 50

# Проверяем gunicorn вручную
cd /var/www/ot_online
source venv/bin/activate
gunicorn --bind 0.0.0.0:8000 wsgi:application
```

---

## 🌐 Шаг 8: Настройка Nginx

### 8.1. Создайте конфигурацию сайта

```bash
sudo nano /etc/nginx/sites-available/ot_online
```

### 8.2. Вставьте конфигурацию:

```nginx
# Основной домен
server {
    listen 80;
    server_name pot.by www.pot.by ваш_IP_адрес;

    client_max_body_size 50M;

    # Статика
    location /static/ {
        alias /var/www/ot_online/staticfiles/;
        expires 30d;
        add_header Cache-Control "public, immutable";
    }

    # Медиа файлы
    location /media/ {
        alias /var/www/ot_online/media/;
        expires 7d;
    }

    # Прокси на Gunicorn
    location / {
        include proxy_params;
        proxy_pass http://unix:/run/gunicorn/ot_online.sock;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header Host $http_host;
        proxy_redirect off;
    }
}

# Exam поддомен
server {
    listen 80;
    server_name exam.pot.by;

    client_max_body_size 50M;

    location /static/ {
        alias /var/www/ot_online/staticfiles/;
        expires 30d;
    }

    location /media/ {
        alias /var/www/ot_online/media/;
        expires 7d;
    }

    location / {
        include proxy_params;
        proxy_pass http://unix:/run/gunicorn/ot_online.sock;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header Host $http_host;
        proxy_redirect off;
    }

    # Защита от индексации
    add_header X-Robots-Tag "noindex, nofollow" always;
}
```

**Замените:** `ваш_IP_адрес` на реальный IP сервера.

**Сохраните:** `Ctrl+O`, `Enter`, `Ctrl+X`

### 8.3. Активируйте конфигурацию

```bash
# Создаём символическую ссылку
sudo ln -s /etc/nginx/sites-available/ot_online /etc/nginx/sites-enabled/

# Удаляем дефолтную конфигурацию (если есть)
sudo rm /etc/nginx/sites-enabled/default

# Проверяем конфигурацию
sudo nginx -t

# Перезагружаем Nginx
sudo systemctl reload nginx
```

**Ожидаемый результат:**
```
nginx: configuration file /etc/nginx/nginx.conf test is successful
```

---

## ✅ Шаг 9: Проверка работоспособности

### 9.1. Проверьте статус служб

```bash
# Gunicorn
sudo systemctl status ot_online

# Nginx
sudo systemctl status nginx
```

### 9.2. Откройте сайт в браузере

```
http://pot.by
# или
http://ваш_IP_адрес
```

**Должны увидеть:** Главную страницу OT_online

### 9.3. Проверьте админку

```
http://pot.by/admin/
```

Войдите под суперпользователем.

---

## 🔍 Устранение неполадок

### Ошибка 502 Bad Gateway

**Причина:** Gunicorn не запущен или сокет недоступен.

**Решение:**
```bash
sudo systemctl status ot_online
sudo journalctl -u ot_online -n 50
sudo systemctl restart ot_online
```

### Ошибка 403 Forbidden

**Причина:** Неверные права доступа к файлам.

**Решение:**
```bash
sudo chown -R $USER:www-data /var/www/ot_online
sudo chmod -R 755 /var/www/ot_online
sudo chmod 644 /var/www/ot_online/db.sqlite3
```

### Статика не загружается (404 на CSS/JS)

**Причина:** Не собрана статика или неверный путь в Nginx.

**Решение:**
```bash
cd /var/www/ot_online
source venv/bin/activate
python manage.py collectstatic --noinput
sudo nginx -t && sudo systemctl reload nginx
```

### Ошибки в логах Django

```bash
# Логи приложения
sudo tail -f /var/log/ot_online/error.log
sudo tail -f /var/log/ot_online/access.log

# Логи systemd
sudo journalctl -u ot_online -f
```

---

## 🔄 Обновление проекта после изменений

Когда вы сделали изменения и запушили в GitHub:

```bash
cd /var/www/ot_online

# Получаем последние изменения
git pull origin main

# Активируем venv
source venv/bin/activate

# Обновляем зависимости (если менялись)
pip install -r requirements.txt

# Применяем миграции
python manage.py migrate --noinput

# Собираем статику
python manage.py collectstatic --noinput

# Перезапускаем Gunicorn
sudo systemctl restart ot_online

# Проверяем статус
sudo systemctl status ot_online
```

---

## 📊 Полезные команды

### Просмотр логов

```bash
# Логи Gunicorn (systemd)
sudo journalctl -u ot_online -f

# Логи приложения
sudo tail -f /var/log/ot_online/error.log

# Логи Nginx
sudo tail -f /var/log/nginx/error.log
```

### Управление службой

```bash
# Статус
sudo systemctl status ot_online

# Запуск
sudo systemctl start ot_online

# Остановка
sudo systemctl stop ot_online

# Перезапуск
sudo systemctl restart ot_online

# Автозапуск
sudo systemctl enable ot_online
```

### Работа с Git

```bash
# Проверить текущую ветку
git branch

# Посмотреть изменения
git status

# Сбросить локальные изменения
git reset --hard origin/main

# Обновить код
git pull origin main
```

---

## 📝 Чеклист развёртывания

- [ ] Git установлен на сервере
- [ ] Репозиторий склонирован в `/var/www/ot_online`
- [ ] Виртуальное окружение создано и активировано
- [ ] Зависимости установлены из `requirements.txt`
- [ ] `.env` файл создан и настроен
- [ ] `db.sqlite3` и `media/` перенесены с локалки
- [ ] Миграции применены (`python manage.py migrate`)
- [ ] Статика собрана (`python manage.py collectstatic`)
- [ ] Gunicorn служба создана и запущена
- [ ] Nginx настроен и перезагружен
- [ ] Сайт открывается в браузере
- [ ] Админка доступна и работает

---

## 🎉 Готово!

Ваш проект успешно развёрнут на production сервере!

**Что дальше:**
- Настройте SSL (Let's Encrypt) для HTTPS
- Настройте автоматические бэкапы БД
- Добавьте мониторинг (Uptime Robot, Sentry)
- Настройте email-уведомления

**Документация:**
- Полное руководство: `docs/DEPLOYMENT.md`
- Email настройка: `docs/EMAIL_NOTIFICATIONS_SETUP.md`
- Квизы с токенами: `docs/QUIZ_TOKEN_SETUP.md`
