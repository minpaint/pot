# deadline_control/management/commands/create_default_key_deadline_categories.py
from django.core.management.base import BaseCommand
from deadline_control.models import KeyDeadlineCategory
from directory.models import Organization


class Command(BaseCommand):
    help = 'Создает предустановленные категории ключевых сроков для всех организаций'

    # Предустановленные категории с периодичностью по умолчанию
    DEFAULT_CATEGORIES = [
        {'name': 'Повторный инструктаж', 'icon': '📝', 'periodicity_months': 6},
        {'name': 'Периодическая проверка знаний', 'icon': '📚', 'periodicity_months': 12},
        {'name': 'Отчет', 'icon': '📊', 'periodicity_months': 12},
        {'name': 'Аттестация рабочих мест', 'icon': '✅', 'periodicity_months': 60},  # 5 лет
        {'name': 'Замеры вредных факторов', 'icon': '🔬', 'periodicity_months': 12},
        {'name': 'Пересмотр инструкций по охране труда', 'icon': '📋', 'periodicity_months': 60},  # 5 лет
        {'name': 'Повышение квалификации', 'icon': '🎓', 'periodicity_months': 36},  # 3 года
        {'name': 'Прочие', 'icon': '📌', 'periodicity_months': 12},
    ]

    def add_arguments(self, parser):
        parser.add_argument(
            '--organization',
            type=int,
            help='ID организации (если не указан - для всех организаций)',
        )

    def handle(self, *args, **options):
        organization_id = options.get('organization')

        if organization_id:
            organizations = Organization.objects.filter(id=organization_id)
            if not organizations.exists():
                self.stdout.write(self.style.ERROR(f'Организация с ID {organization_id} не найдена'))
                return
        else:
            organizations = Organization.objects.all()

        if not organizations.exists():
            self.stdout.write(self.style.WARNING('Нет организаций в системе'))
            return

        self.stdout.write(self.style.SUCCESS(f'Создание категорий для {organizations.count()} организаций...'))
        self.stdout.write('')

        total_created = 0
        total_existing = 0

        for organization in organizations:
            self.stdout.write(f'Организация: {organization.short_name_ru}')

            for category_data in self.DEFAULT_CATEGORIES:
                category, created = KeyDeadlineCategory.objects.get_or_create(
                    organization=organization,
                    name=category_data['name'],
                    defaults={
                        'icon': category_data['icon'],
                        'periodicity_months': category_data['periodicity_months'],
                    }
                )

                if created:
                    self.stdout.write(
                        self.style.SUCCESS(
                            f'  [+] {category_data["name"]} '
                            f'(периодичность: {category_data["periodicity_months"]} мес.)'
                        )
                    )
                    total_created += 1
                else:
                    self.stdout.write(
                        self.style.WARNING(
                            f'  [=] {category_data["name"]} (уже существует)'
                        )
                    )
                    total_existing += 1

            self.stdout.write('')

        self.stdout.write('=' * 60)
        self.stdout.write(self.style.SUCCESS(f'Завершено!'))
        self.stdout.write(f'Создано новых категорий: {total_created}')
        self.stdout.write(f'Уже существовало: {total_existing}')
        self.stdout.write(f'Всего категорий: {total_created + total_existing}')
