# -*- coding: utf-8 -*-
"""
Создаёт суперпользователя dogovor если его ещё нет.
Использование: python manage.py create_admin
"""
from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model


class Command(BaseCommand):
    help = 'Создать суперпользователя dogovor (если не существует)'

    def handle(self, *args, **options):
        User = get_user_model()
        if not User.objects.filter(username='dogovor').exists():
            User.objects.create_superuser('dogovor', '', 'dog7035911')
            self.stdout.write(self.style.SUCCESS(
                'Суперпользователь создан: login=dogovor'
            ))
        else:
            self.stdout.write('Пользователь dogovor уже существует.')
