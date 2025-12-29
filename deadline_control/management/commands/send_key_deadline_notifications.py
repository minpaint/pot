# deadline_control/management/commands/send_key_deadline_notifications.py
from django.core.management.base import BaseCommand
from django.core.mail import send_mail
from django.conf import settings
from django.utils import timezone
from django.contrib.auth import get_user_model

from directory.models import Organization
from directory.utils.email_recipients import collect_recipients_for_subdivision
from deadline_control.models import (
    EmailSettings,
    EmailTemplate,
    EmailTemplateType,
    KeyDeadlineItem,
    KeyDeadlineSendLog,
)
from datetime import datetime
import json

User = get_user_model()


class Command(BaseCommand):
    help = 'Отправляет email уведомления о ключевых мероприятиях (просроченных и предстоящих)'

    def add_arguments(self, parser):
        parser.add_argument(
            '--emails',
            type=str,
            help='Список email адресов через запятую (для тестирования)',
        )
        parser.add_argument(
            '--organization',
            type=int,
            help='ID организации для фильтрации (по умолчанию - все)',
        )
        parser.add_argument(
            '--warning-days',
            type=int,
            default=30,
            help='За сколько дней предупреждать о предстоящих мероприятиях (по умолчанию 30)',
        )

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS('Начинаем формирование уведомлений о ключевых мероприятиях...'))

        warning_days = options['warning_days']

        # Определяем организации для обработки
        if options['organization']:
            organizations = Organization.objects.filter(id=options['organization'])
        else:
            organizations = Organization.objects.all()

        total_sent = 0
        total_failed = 0
        total_skipped = 0

        # Обрабатываем каждую организацию отдельно
        for organization in organizations:
            self.stdout.write(f'\n--- Обработка организации: {organization.short_name_ru} ---')

            # Создаём лог рассылки
            send_log = KeyDeadlineSendLog.objects.create(
                organization=organization,
                initiated_by=None,  # Автоматическая рассылка по расписанию
                notification_type='scheduled'
            )

            # Получаем настройки email для организации
            try:
                email_settings = EmailSettings.get_settings(organization)
            except Exception as e:
                self.stdout.write(self.style.WARNING(
                    f'Не удалось получить настройки email для {organization.short_name_ru}: {e}'
                ))
                send_log.status = 'failed'
                send_log.save()
                total_skipped += 1
                continue

            # Проверяем, активны ли настройки
            if not email_settings.is_active:
                self.stdout.write(self.style.WARNING(
                    f'Email уведомления отключены для {organization.short_name_ru}'
                ))
                send_log.status = 'completed'
                send_log.save()
                total_skipped += 1
                continue

            if not email_settings.email_host:
                self.stdout.write(self.style.WARNING(
                    f'SMTP сервер не настроен для {organization.short_name_ru}'
                ))
                send_log.status = 'failed'
                send_log.save()
                total_skipped += 1
                continue

            # Получаем активные мероприятия организации
            items = KeyDeadlineItem.objects.filter(
                organization=organization,
                is_active=True
            ).select_related('category', 'organization').order_by('category__name', 'next_date')

            if not items.exists():
                self.stdout.write(self.style.WARNING(
                    f'Нет активных мероприятий для {organization.short_name_ru}'
                ))
                send_log.status = 'completed'
                send_log.save()
                total_skipped += 1
                continue

            # Фильтруем просроченные и предстоящие
            overdue_items = []
            upcoming_items = []

            for item in items:
                if item.is_overdue():
                    overdue_items.append(item)
                elif item.is_upcoming(warning_days=warning_days):
                    upcoming_items.append(item)

            # Если нет просроченных и предстоящих - пропускаем
            if not overdue_items and not upcoming_items:
                self.stdout.write(self.style.WARNING(
                    f'Нет просроченных или предстоящих мероприятий для {organization.short_name_ru}'
                ))
                send_log.status = 'completed'
                send_log.save()
                total_skipped += 1
                continue

            # Определяем получателей
            if options['emails']:
                recipient_list = [email.strip() for email in options['emails'].split(',')]
                self.stdout.write(f'   Используются email из параметра: {", ".join(recipient_list)}')
            else:
                recipient_list = collect_recipients_for_subdivision(
                    subdivision=None,
                    organization=organization
                )

                if not recipient_list:
                    self.stdout.write(self.style.WARNING(
                        f'Получатели не найдены через EmailSettings. Используем администраторов.'
                    ))
                    recipient_list = list(
                        User.objects.filter(is_staff=True, email__isnull=False)
                        .exclude(email='')
                        .values_list('email', flat=True)
                    )

            # Добавляем ответственных лиц из мероприятий (если указан email)
            responsible_emails = set()
            for item in overdue_items + upcoming_items:
                if item.responsible_person and '@' in item.responsible_person:
                    # Проверяем что это похоже на email
                    email = item.responsible_person.strip()
                    if email and '.' in email:  # Простая проверка на валидность
                        responsible_emails.add(email)

            if responsible_emails:
                original_count = len(recipient_list)
                recipient_list = list(set(recipient_list) | responsible_emails)  # Объединение без дублей
                added_count = len(recipient_list) - original_count
                if added_count > 0:
                    self.stdout.write(f'   Добавлено ответственных лиц: {added_count}')

            if not recipient_list:
                self.stdout.write(self.style.WARNING(
                    f'Нет получателей для {organization.short_name_ru}'
                ))
                send_log.status = 'completed'
                send_log.save()
                total_skipped += 1
                continue

            # Получаем шаблон письма
            try:
                template_type = EmailTemplateType.objects.get(code='key_deadline')

                # Сначала ищем шаблон для конкретной организации
                template = EmailTemplate.objects.filter(
                    organization=organization,
                    template_type=template_type,
                    is_active=True,
                    is_default=True
                ).first()

                # Если не найден - берём эталонный шаблон (organization=None)
                if not template:
                    template = EmailTemplate.objects.filter(
                        organization__isnull=True,
                        template_type=template_type,
                        is_active=True,
                        is_default=True
                    ).first()
            except EmailTemplateType.DoesNotExist:
                template = None

            # Формируем текст письма
            if template:
                self.stdout.write(self.style.SUCCESS(
                    f'   Найден шаблон: {template.name} (ID: {template.id})'
                ))

                # Формируем HTML секции по категориям
                overdue_section = self._format_html_sections_by_category(overdue_items, 'overdue')
                upcoming_section = self._format_html_sections_by_category(upcoming_items, 'upcoming')

                # URL для перехода
                site_domain = getattr(settings, 'SITE_DOMAIN', 'pot.by')
                key_deadline_url = f'https://{site_domain}/admin/deadline_control/keydeadlineitem/'

                context = {
                    'organization_name': organization.short_name_ru,
                    'total_count': len(overdue_items) + len(upcoming_items),
                    'overdue_count': len(overdue_items),
                    'upcoming_count': len(upcoming_items),
                    'overdue_section': overdue_section,
                    'upcoming_section': upcoming_section,
                    'key_deadline_url': key_deadline_url,
                }

                subject = template.get_formatted_subject(context)
                html_message = template.get_formatted_body(context)
                message = self._format_text_message(organization, overdue_items, upcoming_items, warning_days)

            else:
                self.stdout.write(self.style.WARNING(
                    '   Шаблон не найден! Используется текстовый формат.'
                ))
                subject = f'⚙️ Уведомление о ключевых мероприятиях - {organization.short_name_ru} - {datetime.now().strftime("%d.%m.%Y")}'
                message = self._format_text_message(organization, overdue_items, upcoming_items, warning_days)
                html_message = None

            # Получаем подключение с настройками организации
            connection = email_settings.get_connection()
            from_email = email_settings.default_from_email or email_settings.email_host_user

            # Отправляем письмо
            try:
                send_mail(
                    subject=subject,
                    message=message,
                    from_email=from_email,
                    recipient_list=recipient_list,
                    connection=connection,
                    fail_silently=False,
                    html_message=html_message,
                )
                self.stdout.write(
                    self.style.SUCCESS(
                        f'   [OK] Уведомление отправлено!\n'
                        f'      Получатели: {", ".join(recipient_list)}\n'
                        f'      Просроченные: {len(overdue_items)}, Предстоящие: {len(upcoming_items)}'
                    )
                )
                total_sent += 1

                # Обновляем лог
                send_log.overdue_items_count = len(overdue_items)
                send_log.upcoming_items_count = len(upcoming_items)
                send_log.successful_count = 1
                send_log.status = 'completed'
                send_log.recipients = json.dumps(recipient_list)
                send_log.recipients_count = len(recipient_list)
                send_log.email_subject = subject
                send_log.email_template = template
                send_log.sent_at = timezone.now()
                send_log.save()

            except Exception as e:
                self.stdout.write(
                    self.style.ERROR(f'   [ERROR] Ошибка при отправке email: {str(e)}')
                )
                total_failed += 1

                send_log.overdue_items_count = len(overdue_items)
                send_log.upcoming_items_count = len(upcoming_items)
                send_log.failed_count = 1
                send_log.status = 'failed'
                send_log.error_message = str(e)
                send_log.recipients = json.dumps(recipient_list)
                send_log.recipients_count = len(recipient_list)
                send_log.email_subject = subject
                send_log.save()

        # Итоговая статистика
        self.stdout.write('\n' + '=' * 60)
        self.stdout.write(
            self.style.SUCCESS(
                f'Завершено!\n'
                f'Отправлено: {total_sent}\n'
                f'Ошибок: {total_failed}\n'
                f'Пропущено: {total_skipped}'
            )
        )

    def _format_html_sections_by_category(self, items, section_type):
        """
        Формирует HTML секции с группировкой по категориям
        """
        if not items:
            return ''

        # Группируем по категориям
        items_by_category = {}
        for item in items:
            cat_name = item.category.name
            if cat_name not in items_by_category:
                items_by_category[cat_name] = {
                    'icon': item.category.icon,
                    'items': []
                }
            items_by_category[cat_name]['items'].append(item)

        # Формируем HTML
        sections_html = []

        for cat_name, cat_data in items_by_category.items():
            cat_items = cat_data['items']
            icon = cat_data['icon']

            # Стили в зависимости от типа
            if section_type == 'overdue':
                bg_color = '#ffebee'
                border_color = '#f44336'
                title_color = '#d32f2f'
            else:  # upcoming
                bg_color = '#fff3e0'
                border_color = '#ff9800'
                title_color = '#f57c00'

            # Формируем список мероприятий
            items_html = []
            for item in cat_items:
                days = item.days_until_next()

                item_html = f"""
                <div style="background-color: white; padding: 12px; margin: 8px 0; border-radius: 4px; border-left: 3px solid {border_color};">
                    <div style="font-weight: 600; font-size: 14px; color: #333; margin-bottom: 6px;">
                        {item.name}
                    </div>
                    <div style="color: #666; font-size: 13px; line-height: 1.5;">
                        <strong>Периодичность:</strong> {item.periodicity_months or item.category.periodicity_months} мес.<br>
                        <strong>Дата проведения:</strong> {item.current_date.strftime('%d.%m.%Y')}<br>
                        <strong>Следующая дата:</strong> {item.next_date.strftime('%d.%m.%Y')}<br>
"""

                if section_type == 'overdue':
                    days_overdue = abs(days) if days else 0
                    item_html += f'                        <strong style="color: #d32f2f;">⚠️ Просрочено:</strong> <span style="color: #d32f2f; font-weight: 600;">{days_overdue} дней</span><br>\n'
                else:
                    item_html += f'                        <strong>Осталось:</strong> <span style="color: #f57c00; font-weight: 600;">{days} дней</span><br>\n'

                if item.responsible_person:
                    item_html += f'                        <strong>Ответственный:</strong> {item.responsible_person}<br>\n'

                item_html += """
                    </div>
                </div>
"""
                items_html.append(item_html)

            # Собираем секцию категории
            section_html = f"""
            <div style="margin: 15px 0;">
                <h4 style="color: {title_color}; margin: 10px 0; font-size: 15px;">
                    {icon} {cat_name} ({len(cat_items)})
                </h4>
                {''.join(items_html)}
            </div>
"""
            sections_html.append(section_html)

        return ''.join(sections_html)

    def _format_text_message(self, organization, overdue_items, upcoming_items, warning_days):
        """Форматирует текстовую версию письма"""
        lines = []
        lines.append('⚙️ УВЕДОМЛЕНИЕ О КЛЮЧЕВЫХ МЕРОПРИЯТИЯХ')
        lines.append('=' * 60)
        lines.append(f'Организация: {organization.full_name_ru}')
        lines.append(f'Дата отчета: {datetime.now().strftime("%d.%m.%Y %H:%M")}')
        lines.append('')

        # Просроченные
        if overdue_items:
            lines.append(f'🚨 ПРОСРОЧЕННЫЕ МЕРОПРИЯТИЯ ({len(overdue_items)}):')
            lines.append('-' * 60)

            # Группируем по категориям
            items_by_cat = {}
            for item in overdue_items:
                cat = item.category.name
                if cat not in items_by_cat:
                    items_by_cat[cat] = []
                items_by_cat[cat].append(item)

            for cat_name, items in items_by_cat.items():
                lines.append(f'\n{cat_name}:')
                for item in items:
                    days_overdue = item.days_overdue()
                    lines.append(
                        f'  • {item.name}\n'
                        f'    Периодичность: {item.periodicity_months or item.category.periodicity_months} мес.\n'
                        f'    Дата проведения: {item.current_date.strftime("%d.%m.%Y")}\n'
                        f'    Следующая дата: {item.next_date.strftime("%d.%m.%Y")}\n'
                        f'    Просрочено: {days_overdue} дней\n'
                        f'    Ответственный: {item.responsible_person or "Не указан"}\n'
                    )
            lines.append('')

        # Предстоящие
        if upcoming_items:
            lines.append(f'⏰ ПРЕДСТОЯЩИЕ МЕРОПРИЯТИЯ (в течение {warning_days} дней, {len(upcoming_items)}):')
            lines.append('-' * 60)

            items_by_cat = {}
            for item in upcoming_items:
                cat = item.category.name
                if cat not in items_by_cat:
                    items_by_cat[cat] = []
                items_by_cat[cat].append(item)

            for cat_name, items in items_by_cat.items():
                lines.append(f'\n{cat_name}:')
                for item in items:
                    days_until = item.days_until_next()
                    lines.append(
                        f'  • {item.name}\n'
                        f'    Периодичность: {item.periodicity_months or item.category.periodicity_months} мес.\n'
                        f'    Дата проведения: {item.current_date.strftime("%d.%m.%Y")}\n'
                        f'    Следующая дата: {item.next_date.strftime("%d.%m.%Y")}\n'
                        f'    Осталось: {days_until} дней\n'
                        f'    Ответственный: {item.responsible_person or "Не указан"}\n'
                    )
            lines.append('')

        # Итого
        lines.append('=' * 60)
        lines.append(f'ИТОГО: Просроченных: {len(overdue_items)}, Предстоящих: {len(upcoming_items)}')
        lines.append('')
        lines.append('---')
        lines.append('Это автоматическое уведомление из системы управления охраной труда OT_online')

        return '\n'.join(lines)
