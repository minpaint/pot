# -*- coding: utf-8 -*-
"""
Импорт клиентов из clients.json в базу данных Django.
Использование: python manage.py import_clients
"""
import json
import os
from django.core.management.base import BaseCommand
from contracts.models import Client

CLIENTS_FILE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))))),
    'clients.json'
)


class Command(BaseCommand):
    help = 'Импорт клиентов из clients.json'

    def handle(self, *args, **options):
        if not os.path.exists(CLIENTS_FILE):
            self.stderr.write(f'Файл не найден: {CLIENTS_FILE}')
            return

        with open(CLIENTS_FILE, encoding='utf-8') as f:
            data = json.load(f)

        created = 0
        skipped = 0
        for c in data.get('clients', []):
            if Client.objects.filter(unp=c['unp']).exists():
                self.stdout.write(f'  Пропущен (уже есть): {c["org_name_short"]}')
                skipped += 1
                continue
            Client.objects.create(
                org_name=c.get('org_name', ''),
                org_name_short=c.get('org_name_short', ''),
                director_name=c.get('director_name', ''),
                director_initials=c.get('director_initials', ''),
                director_basis=c.get('director_basis', 'Устава'),
                unp=c.get('unp', ''),
                okpo=c.get('okpo', ''),
                address=c.get('address', ''),
                account=c.get('account', ''),
                bank=c.get('bank', ''),
                bank_branch=c.get('bank_branch', ''),
                bic=c.get('bic', ''),
                bank_city=c.get('bank_city', 'г. Минск'),
                phone=c.get('phone', ''),
                email=c.get('email', ''),
            )
            self.stdout.write(f'  Добавлен: {c["org_name_short"]}')
            created += 1

        self.stdout.write(self.style.SUCCESS(
            f'Готово. Добавлено: {created}, пропущено: {skipped}.'
        ))
