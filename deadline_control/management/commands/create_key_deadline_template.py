# deadline_control/management/commands/create_key_deadline_template.py

from django.core.management.base import BaseCommand
from deadline_control.models import EmailTemplateType, EmailTemplate


class Command(BaseCommand):
    help = 'Создаёт тип шаблона и эталонный шаблон для уведомлений о ключевых мероприятиях'

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS('Начинаем создание типа шаблона и эталонного шаблона для ключевых мероприятий...'))

        # Шаг 1: Создаём или получаем тип шаблона
        template_type, created = EmailTemplateType.objects.get_or_create(
            code='key_deadline',
            defaults={
                'name': 'Уведомления о ключевых мероприятиях',
                'description': 'Шаблон для уведомлений о ключевых мероприятиях (просроченных и предстоящих)',
                'available_variables': {
                    'organization_name': 'Название организации',
                    'total_count': 'Общее количество мероприятий',
                    'overdue_count': 'Количество просроченных мероприятий',
                    'upcoming_count': 'Количество предстоящих мероприятий',
                    'overdue_section': 'HTML секция с просроченными мероприятиями',
                    'upcoming_section': 'HTML секция с предстоящими мероприятиями',
                    'key_deadline_url': 'URL для перехода к ключевым мероприятиям',
                },
                'is_active': True
            }
        )

        if created:
            self.stdout.write(self.style.SUCCESS(f'[OK] Создан тип шаблона: {template_type.name} (код: {template_type.code})'))
        else:
            self.stdout.write(self.style.NOTICE(f'[INFO] Тип шаблона уже существует: {template_type.name}'))

        # Шаг 2: Проверяем наличие эталонного шаблона
        existing_reference = EmailTemplate.objects.filter(
            template_type=template_type,
            organization__isnull=True,
            is_default=True
        ).first()

        if existing_reference:
            self.stdout.write(self.style.NOTICE(
                f'[INFO] Эталонный шаблон уже существует: {existing_reference.name} (ID: {existing_reference.id})'
            ))
            # Спрашиваем, перезаписать ли
            answer = input('Перезаписать эталонный шаблон? (yes/no): ')
            if answer.lower() not in ['yes', 'y', 'да', 'д']:
                self.stdout.write(self.style.WARNING('Отменено пользователем'))
                return
            else:
                existing_reference.delete()
                self.stdout.write(self.style.SUCCESS('[OK] Старый эталонный шаблон удалён'))

        # Шаг 3: Формируем HTML тело письма
        html_body = self._get_html_body()

        # Шаг 4: Создаем ОДИН эталонный шаблон (organization=NULL)
        reference_template = EmailTemplate.objects.create(
            organization=None,  # ЭТАЛОННЫЙ ШАБЛОН
            template_type=template_type,
            name='Эталонный шаблон ключевых мероприятий',
            subject='⚙️ Уведомление о ключевых мероприятиях - {organization_name}',
            body=html_body,
            is_default=True,
            is_active=True
        )

        self.stdout.write(self.style.SUCCESS(
            f'[OK] Создан эталонный шаблон: {reference_template.name} (ID: {reference_template.id})'
        ))

        self.stdout.write(self.style.SUCCESS('\n' + '=' * 60))
        self.stdout.write(self.style.SUCCESS('[OK] Готово!'))
        self.stdout.write(self.style.SUCCESS(
            f'Тип шаблона: {template_type.code}\n'
            f'Эталонный шаблон ID: {reference_template.id}\n'
            f'\nТеперь организации могут переопределить этот шаблон через админ-панель.'
        ))

    def _get_html_body(self):
        """Возвращает HTML тело эталонного шаблона"""
        return """<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Уведомление о ключевых мероприятиях</title>
</head>
<body style="margin: 0; padding: 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif; background-color: #f5f5f5;">
    <table width="100%" cellpadding="0" cellspacing="0" style="background-color: #f5f5f5; padding: 20px 0;">
        <tr>
            <td align="center">
                <table width="600" cellpadding="0" cellspacing="0" style="background-color: #ffffff; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1);">
                    <!-- Заголовок -->
                    <tr>
                        <td style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); padding: 30px; border-radius: 8px 8px 0 0; text-align: center;">
                            <h1 style="margin: 0; color: #ffffff; font-size: 24px; font-weight: 600;">
                                ⚙️ Уведомление о ключевых мероприятиях
                            </h1>
                            <p style="margin: 10px 0 0; color: #e0e7ff; font-size: 16px;">
                                {organization_name}
                            </p>
                        </td>
                    </tr>

                    <!-- Основное содержимое -->
                    <tr>
                        <td style="padding: 30px;">
                            <p style="margin: 0 0 20px; color: #374151; font-size: 15px; line-height: 1.6;">
                                Добрый день!
                            </p>
                            <p style="margin: 0 0 20px; color: #374151; font-size: 15px; line-height: 1.6;">
                                Направляем уведомление о ключевых мероприятиях, требующих вашего внимания.
                            </p>

                            <!-- Статистика -->
                            <table width="100%" cellpadding="0" cellspacing="0" style="margin: 20px 0;">
                                <tr>
                                    <td style="padding: 15px; background-color: #fef3c7; border-left: 4px solid #f59e0b; border-radius: 4px;">
                                        <div style="font-size: 14px; color: #92400e; font-weight: 600;">
                                            📊 Статистика
                                        </div>
                                        <div style="margin-top: 8px; color: #78350f; font-size: 13px;">
                                            Просроченных: <strong>{overdue_count}</strong> |
                                            Предстоящих: <strong>{upcoming_count}</strong>
                                        </div>
                                    </td>
                                </tr>
                            </table>

                            <!-- Просроченные мероприятия -->
                            {overdue_section}

                            <!-- Предстоящие мероприятия -->
                            {upcoming_section}

                            <!-- Призыв к действию -->
                            <div style="margin: 30px 0; text-align: center; padding: 20px; background-color: #f3f4f6; border-radius: 8px;">
                                <p style="margin: 0 0 15px; color: #1f2937; font-weight: 600; font-size: 15px;">
                                    📋 Перейдите в систему для просмотра полной информации
                                </p>
                                <a href="{key_deadline_url}"
                                   style="display: inline-block; background-color: #667eea; color: white; padding: 12px 30px;
                                          text-decoration: none; border-radius: 6px; font-size: 15px; font-weight: 600;
                                          box-shadow: 0 2px 4px rgba(102, 126, 234, 0.4);">
                                    🔗 Открыть ключевые мероприятия
                                </a>
                            </div>
                        </td>
                    </tr>

                    <!-- Футер -->
                    <tr>
                        <td style="padding: 20px 30px; background-color: #f9fafb; border-radius: 0 0 8px 8px; border-top: 1px solid #e5e7eb;">
                            <p style="margin: 0; color: #6b7280; font-size: 13px; text-align: center;">
                                Это автоматическое уведомление из системы управления охраной труда <strong>OT_online</strong>
                            </p>
                        </td>
                    </tr>
                </table>
            </td>
        </tr>
    </table>
</body>
</html>"""
