"""
Management команда для создания пункта меню "Единый импорт/экспорт"
"""
from django.core.management.base import BaseCommand
from directory.models.menu_item import MenuItem


class Command(BaseCommand):
    help = 'Создает пункт меню для единого импорта/экспорта справочников'

    def handle(self, *args, **options):
        # Проверяем, есть ли уже такой пункт меню
        existing = MenuItem.objects.filter(url_name='admin:global_import').first()

        if existing:
            self.stdout.write(
                self.style.WARNING(f'Пункт меню "{existing.name}" уже существует (ID: {existing.id})')
            )
            return

        # Создаём новый пункт меню
        menu_item = MenuItem.objects.create(
            name='Единый импорт/экспорт',
            icon='📊',
            url_name='admin:global_import',
            location='sidebar',
            is_active=True,
            requires_auth=True,
            is_separator=False,
            order=10,  # После основных разделов
            description='Массовый импорт и экспорт организационной структуры, сотрудников и оборудования из одного Excel-файла'
        )

        self.stdout.write(
            self.style.SUCCESS(
                f'Пункт меню "{menu_item.name}" успешно создан (ID: {menu_item.id})'
            )
        )
        self.stdout.write(
            self.style.SUCCESS(
                f'URL: admin:global_import'
            )
        )
        self.stdout.write(
            self.style.SUCCESS(
                f'Иконка: {menu_item.icon}'
            )
        )
