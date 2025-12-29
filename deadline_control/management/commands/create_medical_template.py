# deadline_control/management/commands/create_medical_template.py

from django.core.management.base import BaseCommand
from deadline_control.models import EmailTemplateType, EmailTemplate


class Command(BaseCommand):
    help = 'Создает тип шаблона и ОДИН эталонный шаблон для уведомлений о медицинских осмотрах'

    def add_arguments(self, parser):
        parser.add_argument(
            '--recreate',
            action='store_true',
            help='Пересоздать эталонный шаблон (удалить существующий и создать новый)'
        )

    def handle(self, *args, **options):
        """Создание типа шаблона и ОДНОГО эталонного шаблона"""

        recreate = options.get('recreate', False)

        # Шаг 1: Создаем тип шаблона
        template_type, created = EmailTemplateType.objects.get_or_create(
            code='medical_examination',
            defaults={
                'name': 'Уведомление о медицинских осмотрах',
                'description': 'Шаблон для отправки уведомлений о медосмотрах (просроченные, предстоящие, без даты)',
                'available_variables': {
                    'organization_name': 'Краткое название организации (например: "ООО БиоМилкГрин")',
                    'no_date_count': 'Количество сотрудников без даты медосмотра (например: "5")',
                    'overdue_count': 'Количество сотрудников с просроченным медосмотром (например: "3")',
                    'upcoming_count': 'Количество сотрудников с предстоящим медосмотром (например: "12")',
                    'overdue_section': 'HTML секция просроченных медосмотров',
                    'upcoming_section': 'HTML секция предстоящих медосмотров',
                    'no_date_section': 'HTML секция сотрудников без даты медосмотра',
                    'overdue_button': 'Кнопка "Срочно выдать направления" (красная)',
                    'no_date_button': 'Кнопка "Внести дату медосмотра" (синяя)',
                    'upcoming_button': 'Кнопка "Выдать направления" (оранжевая)',
                    'medical_url': 'Ссылка на страницу управления медосмотрами',
                },
                'is_active': True,
            }
        )

        if created:
            self.stdout.write(
                self.style.SUCCESS(
                    f'[OK] Sozdan tip shablona: {template_type.name} (kod: {template_type.code})'
                )
            )
        else:
            self.stdout.write(
                self.style.WARNING(
                    f'! Тип шаблона уже существует: {template_type.name} (код: {template_type.code})'
                )
            )

        # Шаг 2: Проверяем наличие эталонного шаблона
        existing_reference = EmailTemplate.objects.filter(
            template_type=template_type,
            organization__isnull=True,
            is_default=True
        ).first()

        if existing_reference:
            if not recreate:
                self.stdout.write(
                    self.style.WARNING(
                        f'! Эталонный шаблон уже существует: {existing_reference.name}\n'
                        f'  Используйте --recreate для пересоздания'
                    )
                )
                return
            else:
                # Удаляем существующий эталон
                existing_reference.delete()
                self.stdout.write(
                    self.style.WARNING(
                        f'! Удалён существующий эталонный шаблон'
                    )
                )

        # Шаг 3: Создаем HTML шаблон
        html_body = """
<div style="font-family: Arial, sans-serif; max-width: 800px; margin: 0 auto; padding: 20px; background-color: #f5f5f5;">
    <div style="background-color: white; padding: 30px; border-radius: 10px; box-shadow: 0 2px 10px rgba(0,0,0,0.1);">

        <!-- Заголовок -->
        <h2 style="color: #2196f3; margin-top: 0; border-bottom: 3px solid #2196f3; padding-bottom: 10px;">
            🏥 Уведомление о медицинских осмотрах
        </h2>

        <p style="font-size: 16px; color: #333;">
            Здравствуйте!<br><br>
            Направляем информацию о медицинских осмотрах сотрудников организации <strong>{organization_name}</strong>.
        </p>

        <!-- ПРОСРОЧЕННЫЕ МЕДОСМОТРЫ -->
        {overdue_section}

        <!-- Кнопка срочных действий (только если есть просроченные) -->
        {overdue_button}

        <!-- ПРЕДСТОЯЩИЕ МЕДОСМОТРЫ -->
        {upcoming_section}

        <!-- БЕЗ ДАТЫ МЕДОСМОТРА -->
        {no_date_section}

        <!-- Кнопка внесения даты (только если есть сотрудники без даты) -->
        {no_date_button}

        <!-- Кнопка выдать направления (только если есть предстоящие медосмотры) -->
        {upcoming_button}

        <p style="font-size: 14px; color: #666; margin-top: 30px; padding-top: 20px; border-top: 1px solid #ddd;">
            <strong>💡 Справка:</strong> Для работы с медосмотрами войдите в систему под своей учётной записью.
            После входа вы будете автоматически перенаправлены на страницу управления медосмотрами.
        </p>

        <!-- Футер -->
        <div style="margin-top: 30px; padding-top: 20px; border-top: 2px solid #eee; text-align: center; color: #999; font-size: 12px;">
            <p>
                📧 Письмо создано автоматически системой OT-online<br>
                🔒 Система управления охраной труда
            </p>
        </div>
    </div>
</div>
"""

        # Шаг 4: Создаем ОДИН эталонный шаблон (organization=NULL)
        reference_template = EmailTemplate.objects.create(
            organization=None,  # ЭТАЛОННЫЙ ШАБЛОН
            template_type=template_type,
            name='Эталонный шаблон медосмотров',
            subject='🏥 Уведомление о медицинских осмотрах - {organization_name}',
            body=html_body,
            is_active=True,
            is_default=True
        )

        self.stdout.write(
            self.style.SUCCESS(
                f'\n[OK] Sozdan etalonnyy shablon medosmotrov!\n'
                f'  ID: {reference_template.id}\n'
                f'  Nazvanie: {reference_template.name}\n'
                f'  Tip: {reference_template.template_type.name}\n'
                f'  Organizatsiya: Etalon (primenyaetsya dlya vsekh organizatsiy)\n'
            )
        )

        self.stdout.write(
            self.style.SUCCESS(
                f'\n[OK] Sozdanie shablona zaversheno!\n'
                f'   Etot shablon budet ispolzovatsya dlya vsekh organizatsiy,\n'
                f'   esli u nikh net sobstvennogo nastroennogo shablona.'
            )
        )
