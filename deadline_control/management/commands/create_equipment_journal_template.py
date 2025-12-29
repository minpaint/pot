# deadline_control/management/commands/create_equipment_journal_template.py

from django.core.management.base import BaseCommand
from deadline_control.models import EmailTemplateType, EmailTemplate


class Command(BaseCommand):
    help = 'Создает тип шаблона и эталонный шаблон для журналов осмотра оборудования'

    def handle(self, *args, **options):
        template_type, created = EmailTemplateType.objects.get_or_create(
            code='equipment_journal',
            defaults={
                'name': 'Журнал осмотра оборудования',
                'description': 'Шаблон для отправки журналов осмотра оборудования по подразделениям',
                'available_variables': {
                    'organization_name': 'Полное название организации',
                    'subdivision_name': 'Название подразделения',
                    'department_name': 'Название отдела или "Все отделы"',
                    'inspection_date': 'Дата осмотра (ДД.ММ.ГГГГ)',
                    'equipment_type': 'Тип оборудования',
                    'equipment_count': 'Количество оборудования',
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

        existing_reference = EmailTemplate.objects.filter(
            template_type=template_type,
            organization__isnull=True,
            is_default=True
        ).first()

        if existing_reference:
            self.stdout.write(
                self.style.WARNING(
                    f'Эталонный шаблон уже существует: {existing_reference.name}'
                )
            )
            return

        html_body = """
<div style="font-family: Arial, sans-serif; max-width: 800px; margin: 0 auto; padding: 20px; background-color: #f5f5f5;">
    <div style="background-color: white; padding: 30px; border-radius: 10px; box-shadow: 0 2px 10px rgba(0,0,0,0.1);">
        <h2 style="color: #0d6efd; margin-top: 0; border-bottom: 3px solid #0d6efd; padding-bottom: 10px;">
            Журнал осмотра оборудования
        </h2>
        <p style="font-size: 16px; color: #333;">
            Организация: <strong>{organization_name}</strong><br>
            Подразделение: <strong>{subdivision_name}</strong><br>
            Отдел: <strong>{department_name}</strong><br>
            Тип оборудования: <strong>{equipment_type}</strong><br>
            Дата осмотра: <strong>{inspection_date}</strong><br>
            Количество оборудования: <strong>{equipment_count}</strong>
        </p>
        <p style="font-size: 14px; color: #666; margin-top: 20px;">
            В приложении находится файл с журналом осмотра оборудования для заполнения.
        </p>
        <div style="margin-top: 30px; padding-top: 20px; border-top: 2px solid #eee; text-align: center; color: #999; font-size: 12px;">
            Письмо создано автоматически системой OT-online
        </div>
    </div>
</div>
"""

        reference_template = EmailTemplate.objects.create(
            organization=None,
            template_type=template_type,
            name='Эталонный шаблон журнала оборудования',
            subject='Журнал осмотра {equipment_type} - {subdivision_name}',
            body=html_body,
            is_active=True,
            is_default=True
        )

        self.stdout.write(
            self.style.SUCCESS(
                f'Создан эталонный шаблон: {reference_template.name} (ID: {reference_template.id})'
            )
        )
