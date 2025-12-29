# deadline_control/management/commands/create_instruction_journal_template_type.py

from django.core.management.base import BaseCommand
from deadline_control.models import EmailTemplateType


class Command(BaseCommand):
    help = 'Создает начальный тип шаблона для образца журнала инструктажей'

    def handle(self, *args, **options):
        """Создание типа шаблона"""

        # Проверяем, существует ли уже
        template_type, created = EmailTemplateType.objects.get_or_create(
            code='instruction_journal',
            defaults={
                'name': 'Образец журнала инструктажей',
                'description': 'Шаблон для отправки образца заполнения журнала повторных инструктажей',
                'available_variables': {
                    'organization_name': 'Полное название организации (например: "Общество с ограниченной ответственностью \'БиоМилкГрин\'")',
                    'subdivision_name': 'Название структурного подразделения (например: "Производственный цех №1")',
                    'department_name': 'Название отдела. Если несколько отделов - "Все отделы", если один - его название, если нет - "Без отдела"',
                    'date': 'Дата проведения инструктажа в формате ДД.ММ.ГГГГ (например: "05.12.2025")',
                    'instruction_type': 'Вид инструктажа: "Повторный", "Внеплановый", "Целевой"',
                    'instruction_reason': 'Причина проведения внепланового/целевого инструктажа (опционально)',
                    'employee_count': 'Количество сотрудников с инструкциями в подразделении (например: "15")',
                },
                'is_active': True,
            }
        )

        if created:
            self.stdout.write(
                self.style.SUCCESS(
                    f'Создан тип шаблона: {template_type.name} (код: {template_type.code})'
                )
            )
        else:
            self.stdout.write(
                self.style.WARNING(
                    f'Тип шаблона уже существует: {template_type.name} (код: {template_type.code})'
                )
            )
