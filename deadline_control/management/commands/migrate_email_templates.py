# deadline_control/management/commands/migrate_email_templates.py

from django.core.management.base import BaseCommand
from deadline_control.models import EmailSettings, EmailTemplate, EmailTemplateType
from django.db import transaction


class Command(BaseCommand):
    help = 'Переносит существующие шаблоны из EmailSettings в EmailTemplate'

    def handle(self, *args, **options):
        """Миграция шаблонов писем"""

        # Получаем тип шаблона для журнала инструктажей
        try:
            template_type = EmailTemplateType.objects.get(code='instruction_journal')
        except EmailTemplateType.DoesNotExist:
            self.stdout.write(
                self.style.ERROR(
                    'Тип шаблона "instruction_journal" не найден. '
                    'Сначала выполните: py manage.py create_instruction_journal_template_type'
                )
            )
            return

        migrated_count = 0
        skipped_count = 0

        # Получаем все настройки email с непустыми шаблонами
        email_settings = EmailSettings.objects.filter(
            organization__isnull=False
        ).select_related('organization')

        with transaction.atomic():
            for settings in email_settings:
                # Проверяем, есть ли уже шаблон для этой организации
                existing_template = EmailTemplate.objects.filter(
                    organization=settings.organization,
                    template_type=template_type
                ).first()

                if existing_template:
                    self.stdout.write(
                        self.style.WARNING(
                            f'Шаблон для {settings.organization.short_name_ru} уже существует, пропускаем'
                        )
                    )
                    skipped_count += 1
                    continue

                # Проверяем, есть ли данные для миграции
                has_subject = bool(settings.instruction_journal_subject)
                has_body = bool(settings.instruction_journal_body)

                if not has_subject and not has_body:
                    self.stdout.write(
                        self.style.WARNING(
                            f'Нет данных для миграции для {settings.organization.short_name_ru}, пропускаем'
                        )
                    )
                    skipped_count += 1
                    continue

                # Создаем новый шаблон
                template = EmailTemplate.objects.create(
                    organization=settings.organization,
                    template_type=template_type,
                    name='Образец журнала инструктажей',
                    subject=settings.instruction_journal_subject or 'Образец журнала инструктажей - {subdivision_name}',
                    body=settings.instruction_journal_body or self._get_default_body(),
                    is_active=True,
                    is_default=True
                )

                self.stdout.write(
                    self.style.SUCCESS(
                        f'Создан шаблон для {settings.organization.short_name_ru}'
                    )
                )
                migrated_count += 1

        # Итоговая статистика
        self.stdout.write('\n' + '=' * 60)
        self.stdout.write(
            self.style.SUCCESS(
                f'Миграция завершена:\n'
                f'  - Создано шаблонов: {migrated_count}\n'
                f'  - Пропущено: {skipped_count}'
            )
        )

    def _get_default_body(self):
        """Возвращает дефолтный текст письма"""
        return """<p>Здравствуйте!</p>

<p>Направляем образец заполнения журнала инструктажей.</p>

<p><strong>Информация об инструктаже:</strong><br>
<strong>Вид инструктажа:</strong> {instruction_type}<br>
<strong>Дата проведения:</strong> {date}<br>
<strong>Организация:</strong> {organization_name}<br>
<strong>Подразделение:</strong> {subdivision_name}<br>
<strong>Отдел:</strong> {department_name}<br>
<strong>Количество сотрудников:</strong> {employee_count}</p>

<p>Пожалуйста, проверьте образец и заполните журнал.</p>

<p>---<br>
Это автоматическое уведомление из системы управления охраной труда OT_online</p>"""
