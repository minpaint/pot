"""
Management команда для создания пункта меню "Импорт реестра сотрудников"
"""
from django.core.management.base import BaseCommand
from directory.models.menu_item import MenuItem


class Command(BaseCommand):
    help = 'Создает пункт меню для импорта реестра сотрудников из иерархического Excel-файла'

    def handle(self, *args, **options):
        # Проверяем, есть ли уже такой пункт меню
        existing = MenuItem.objects.filter(url_name='admin:registry_import').first()

        if existing:
            self.stdout.write(
                self.style.WARNING(f'Пункт меню "{existing.name}" уже существует (ID: {existing.id})')
            )
            return

        # Создаём новый пункт меню
        menu_item = MenuItem.objects.create(
            name='Импорт реестра сотрудников',
            icon='📋',
            url_name='admin:registry_import',
            location='sidebar',
            is_active=True,
            requires_auth=True,
            is_separator=False,
            order=11,  # После единого импорта/экспорта
            description='Импорт сотрудников из иерархического Excel-файла с автоматическим созданием структуры (подразделения, отделы, должности)'
        )

        self.stdout.write(
            self.style.SUCCESS(
                f'[OK] Пункт меню "{menu_item.name}" успешно создан (ID: {menu_item.id})'
            )
        )
        self.stdout.write(
            self.style.SUCCESS(
                f'[OK] URL: admin:registry_import'
            )
        )
        self.stdout.write(
            self.style.SUCCESS(
                f'[OK] Иконка: {menu_item.icon}'
            )
        )
        self.stdout.write('')
        self.stdout.write(
            self.style.SUCCESS(
                'Теперь пункт меню "Импорт реестра сотрудников" доступен в боковом меню системы.'
            )
        )
