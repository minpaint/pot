#!/bin/bash
# Запуск django-tasks worker вручную (для тестов / до установки systemd-юнита)
# Для production установите potby-worker.service в /etc/systemd/system/
set -e
cd /home/django/webapps/potby
export DJANGO_SETTINGS_MODULE=settings_prod
mkdir -p logs
exec venv/bin/python manage.py db_worker --queue-name default --interval 1 --no-reload
