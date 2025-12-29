# Деплой OT_online (pot.by) через CWP (Apache + Nginx)

`proverka.by` уже работает через CWP exactly: Gunicorn слушает на локальном порту, а Apache/Nginx из панели проксируют запросы и раздают `/static`/`/media`. Ниже — те же шаги, адаптированные для проекта `pot.by`.

## 1. Требования

1. Сервер с установленным **CWP** (Apache + Nginx reverse-proxy), доступом по SSH и правами `root`.
2. Домен `pot.by` (и `www.pot.by`), указывающий на этот сервер.
3. Django-проект уже лежит в `/home/django/webapps/potby`, как и у `proverka.by`.

> ⚠️ Фаервол (включая роутер) обязательно должен пропускать входящие 80/443.

## 2. Настраиваем окружение Django

```bash
cd /home/django/webapps/potby
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

# Production-режим
export DJANGO_ENV=production
python manage.py migrate --settings=settings_prod
python manage.py collectstatic --noinput --settings=settings_prod
```

- `.env` должен содержать прод-настройки (`DJANGO_SETTINGS_MODULE=settings_prod`, `DJANGO_ALLOWED_HOSTS=pot.by,www.pot.by` и т.д.).
- Файлы статики и медиа размещаются внутри `/home/django/webapps/potby/static` и `/home/django/webapps/potby/media` — CWP будет отдавать их напрямую, как уже сделано для `proverka.by`.

## 3. Gunicorn как системная служба

В каталоге `deploy/cwp/` лежат готовые шаблоны:

- `gunicorn_start.sh` — ручной запуск (аналогично тому, как мы стартуем `proverka.by` при отладке).
- `gunicorn-potby.service` — юнит для systemd.

### 3.1 Установка systemd-юнита

```bash
sudo cp deploy/cwp/gunicorn-potby.service /etc/systemd/system/potby.service
sudo systemctl daemon-reload
sudo systemctl enable --now potby.service
sudo systemctl status potby.service
```

Gunicorn слушает `127.0.0.1:8020` (как `proverka.by` на `8010`). Логи пишутся в `/home/django/webapps/potby/logs/`.

## 4. Настройка CWP

По аналогии с рабочим доменом `proverka.by` нужно (готовые сниппеты лежат в `deploy/cwp/apache-potby.conf` и `deploy/cwp/nginx-potby.conf`):

1. В панели CWP → **WebServer Settings → WebServers Domain Conf** выбрать домен `pot.by` и включить кастомный шаблон.
2. В **Apache**-части шаблона вставляем содержимое `deploy/cwp/apache-potby.conf`:
   ```apache
   ServerName pot.by
   ServerAlias www.pot.by

   Alias /static/ /home/django/webapps/potby/static/
   Alias /media/ /home/django/webapps/potby/media/

   <Directory /home/django/webapps/potby/static>
       Require all granted
   </Directory>
   <Directory /home/django/webapps/potby/media>
       Require all granted
   </Directory>

   ProxyPreserveHost On
   ProxyPass /static/ !
   ProxyPass /media/ !
   ProxyPass / http://127.0.0.1:8020/
   ProxyPassReverse / http://127.0.0.1:8020/
   ```
3. В **Nginx**-шаблоне вставляем `deploy/cwp/nginx-potby.conf`, чтобы Nginx сразу раздавал статику (иначе запрос пойдёт до Apache):
   ```nginx
   location /static/ {
       alias /home/django/webapps/potby/static/;
       access_log off;
       expires 30d;
   }

   location /media/ {
       alias /home/django/webapps/potby/media/;
       access_log off;
       expires 30d;
   }
   ```
4. Сохраняем шаблон, применяем его к домену и перезапускаем веб‑серверы:
   ```bash
   sudo systemctl reload httpd
   sudo systemctl reload nginx
   ```

> Для апстрима Apache→Gunicorn оставляем стандартный 127.0.0.1:8181, как это already done for `proverka.by`. Важная часть — только alias/proxy на статические файлы и новый порт 8020.

## 5. SSL через Let’s Encrypt

1. В панели CWP → **SSL Certificates** запрашиваем сертификат для `pot.by` + `www.pot.by`.
2. После выпуска проверяем, что Apache и Nginx используют актуальные `.crt/.key`.
3. Обновляем `.env` и `CSRF_TRUSTED_ORIGINS` до HTTPS (пример уже в `.env.example`).

## 6. Проверка

1. `curl -I http://127.0.0.1:8020/` — убеждаемся, что Gunicorn отвечает (как и в `proverka.by`).
2. `curl -I https://pot.by/health/` (или главную страницу) — должна прийти 200/301.
3. Проверяем логи: `journalctl -u potby -f`, `/home/django/webapps/potby/logs/gunicorn.error.log`, `/usr/local/apache/logs/` и `/usr/local/nginx/logs/`.

После этих шагов проект пот.by доступен из интернета точно так же, как `proverka.by`.
