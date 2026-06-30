# deadline_control/management/commands/send_medical_notifications.py
from django.core.management.base import BaseCommand
from django.core.mail import send_mail
from django.conf import settings
from django.utils import timezone
from django.contrib.auth import get_user_model

from directory.models import Employee, Organization
from directory.utils.email_recipients import collect_recipients_for_subdivision
from deadline_control.models import (
    EmailSettings,
    MedicalNotificationSendLog,
    MedicalNotificationSendDetail
)
from datetime import datetime
import json

User = get_user_model()


class Command(BaseCommand):
    help = 'Отправляет email уведомления о плане прохождения медицинских осмотров (2 раза в месяц)'

    def add_arguments(self, parser):
        parser.add_argument(
            '--emails',
            type=str,
            help='Список email адресов через запятую (по умолчанию - администраторы)',
        )
        parser.add_argument(
            '--organization',
            type=int,
            help='ID организации для фильтрации (по умолчанию - все)',
        )

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS('Начинаем формирование отчета о медосмотрах...'))

        # Определяем организации для обработки
        if options['organization']:
            organizations = Organization.objects.filter(id=options['organization'])
        else:
            organizations = Organization.objects.all()

        total_sent = 0
        total_failed = 0

        # Обрабатываем каждую организацию отдельно
        for organization in organizations:
            self.stdout.write(f'\n--- Обработка организации: {organization.short_name_ru} ---')

            # Создаём лог рассылки
            send_log = MedicalNotificationSendLog.objects.create(
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
                # Логируем пропуск
                send_log.status = 'failed'
                send_log.skipped_count = 1
                send_log.save()
                MedicalNotificationSendDetail.objects.create(
                    send_log=send_log,
                    status='skipped',
                    skip_reason='template_not_found',
                    error_message=f'Не удалось получить настройки email: {str(e)}'
                )
                continue

            # Проверяем, активны ли настройки
            if not email_settings.is_active:
                self.stdout.write(self.style.WARNING(
                    f'Email уведомления отключены для {organization.short_name_ru}'
                ))
                # Логируем пропуск
                send_log.status = 'completed'
                send_log.skipped_count = 1
                send_log.save()
                MedicalNotificationSendDetail.objects.create(
                    send_log=send_log,
                    status='skipped',
                    skip_reason='template_not_found',
                    error_message='Email уведомления отключены в настройках'
                )
                continue

            if not email_settings.email_host:
                self.stdout.write(self.style.WARNING(
                    f'SMTP сервер не настроен для {organization.short_name_ru}'
                ))
                # Логируем пропуск
                send_log.status = 'failed'
                send_log.skipped_count = 1
                send_log.save()
                MedicalNotificationSendDetail.objects.create(
                    send_log=send_log,
                    status='skipped',
                    skip_reason='template_not_found',
                    error_message='SMTP сервер не настроен'
                )
                continue

            # Определяем получателей используя новую трёхуровневую систему
            if options['emails']:
                # Если указаны email через параметр команды - используем их
                recipient_list = [email.strip() for email in options['emails'].split(',')]
                self.stdout.write(self.style.NOTICE(
                    f'Используются email из параметра --emails: {", ".join(recipient_list)}'
                ))
            else:
                # Используем новую систему сбора получателей
                # subdivision=None означает сбор только из EmailSettings организации
                # (источники 1 и 2 будут пропущены, так как они требуют subdivision)
                recipient_list = collect_recipients_for_subdivision(
                    subdivision=None,
                    organization=organization
                )

                # Fallback: если вообще никого не найдено - берём администраторов
                if not recipient_list:
                    self.stdout.write(self.style.WARNING(
                        f'Получатели не найдены через EmailSettings. '
                        f'Используем fallback на администраторов системы.'
                    ))
                    recipient_list = list(
                        User.objects.filter(is_staff=True, email__isnull=False)
                        .exclude(email='')
                        .values_list('email', flat=True)
                    )

            # Финальная проверка
            if not recipient_list:
                self.stdout.write(self.style.WARNING(
                    f'❌ Нет получателей для {organization.short_name_ru}. '
                    f'Настройте EmailSettings или укажите --emails параметр.'
                ))
                # Логируем пропуск
                send_log.status = 'completed'
                send_log.skipped_count = 1
                send_log.save()
                MedicalNotificationSendDetail.objects.create(
                    send_log=send_log,
                    status='skipped',
                    skip_reason='no_recipients',
                    error_message='Нет получателей. Настройте EmailSettings или используйте --emails'
                )
                continue

            # Получаем ВСЕХ сотрудников организации (включая тех, у кого вообще нет медосмотров)
            employees_qs = Employee.objects.active_for_operations().filter(
                organization=organization
            ).select_related(
                'organization',
                'position'
            ).prefetch_related(
                'medical_examinations__harmful_factor',
                'position__medical_factors__harmful_factor'
            )

            # Разделяем на категории
            no_date = []
            overdue = []
            upcoming = []

            for employee in employees_qs:
                medical_status = employee.get_medical_status()

                if not medical_status:
                    continue

                status = medical_status['status']
                if status == 'no_date':
                    no_date.append({
                        'employee': employee,
                        'status': medical_status
                    })
                elif status == 'expired':
                    overdue.append({
                        'employee': employee,
                        'status': medical_status
                    })
                elif status == 'upcoming':
                    upcoming.append({
                        'employee': employee,
                        'status': medical_status
                    })

            # Если нет данных для отправки - пропускаем
            if not (no_date or overdue or upcoming):
                self.stdout.write(self.style.WARNING(
                    f'Нет данных для отправки для {organization.short_name_ru}'
                ))
                # Логируем пропуск
                send_log.status = 'completed'
                send_log.skipped_count = 1
                send_log.save()
                MedicalNotificationSendDetail.objects.create(
                    send_log=send_log,
                    status='skipped',
                    skip_reason='no_data',
                    error_message='Нет сотрудников с данными о медосмотрах',
                    recipients=json.dumps(recipient_list),
                    recipients_count=len(recipient_list)
                )
                continue

            # Получаем шаблон письма
            from deadline_control.models import EmailTemplate, EmailTemplateType

            try:
                template_type = EmailTemplateType.objects.get(code='medical_examination')

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
                    f'✅ Найден шаблон: {template.name} (ID: {template.id})'
                ))
                # Используем HTML шаблон
                subject = template.get_formatted_subject({
                    'organization_name': organization.short_name_ru
                })

                # Формируем HTML секции
                overdue_section = self._format_html_section(overdue, 'overdue') if overdue else ''
                upcoming_section = self._format_html_section(upcoming, 'upcoming') if upcoming else ''
                no_date_section = self._format_html_section(no_date, 'no_date') if no_date else ''

                # Формируем контекст для шаблона
                from django.conf import settings
                site_domain = getattr(settings, 'SITE_DOMAIN', 'pot.by')
                medical_url = f'https://{site_domain}/deadline-control/medical/'

                # Кнопка после просроченных (только если есть просроченные)
                overdue_button = ''
                if overdue:
                    overdue_button = f"""
        <div style="margin: 20px 0 30px; text-align: center; padding: 20px; background-color: #ffebee; border-radius: 8px;">
            <p style="margin: 0 0 15px; color: #d32f2f; font-weight: 600; font-size: 15px;">
                ⚠️ Требуется срочное оформление направлений для {len(overdue)} сотрудников
            </p>
            <a href="{medical_url}"
               style="display: inline-block; background-color: #f44336; color: white; padding: 15px 40px;
                      text-decoration: none; border-radius: 8px; font-size: 16px; font-weight: 600;
                      box-shadow: 0 4px 6px rgba(0,0,0,0.15); transition: background-color 0.3s;">
                🚨 Срочно выдать направления
            </a>
        </div>
"""

                # Кнопка после "без даты" (только если есть сотрудники без даты)
                no_date_button = ''
                if no_date:
                    no_date_button = f"""
        <div style="margin: 20px 0 30px; text-align: center; padding: 20px; background-color: #e3f2fd; border-radius: 8px;">
            <p style="margin: 0 0 15px; color: #1976d2; font-weight: 600; font-size: 15px;">
                📋 Требуется внести даты медосмотров для {len(no_date)} сотрудников
            </p>
            <a href="{medical_url}"
               style="display: inline-block; background-color: #2196f3; color: white; padding: 15px 40px;
                      text-decoration: none; border-radius: 8px; font-size: 16px; font-weight: 600;
                      box-shadow: 0 4px 6px rgba(0,0,0,0.15); transition: background-color 0.3s;">
                📅 Внести дату медосмотра
            </a>
        </div>
"""

                # Кнопка "Выдать направления" (только если есть предстоящие медосмотры)
                upcoming_button = ''
                if upcoming:
                    upcoming_button = f"""
        <div style="margin: 20px 0 30px; text-align: center; padding: 20px; background-color: #fff3e0; border-radius: 8px;">
            <p style="margin: 0 0 15px; color: #f57c00; font-weight: 600; font-size: 15px;">
                🕐 Запланируйте выдачу направлений для {len(upcoming)} сотрудников
            </p>
            <a href="{medical_url}"
               style="display: inline-block; background-color: #ff9800; color: white; padding: 15px 40px;
                      text-decoration: none; border-radius: 8px; font-size: 16px; font-weight: 600;
                      box-shadow: 0 4px 6px rgba(0,0,0,0.15); transition: background-color 0.3s;">
                📋 Выдать направления
            </a>
        </div>
"""

                context = {
                    'organization_name': organization.short_name_ru,
                    'overdue_count': len(overdue),
                    'upcoming_count': len(upcoming),
                    'no_date_count': len(no_date),
                    'overdue_section': overdue_section,
                    'upcoming_section': upcoming_section,
                    'no_date_section': no_date_section,
                    'overdue_button': overdue_button,
                    'no_date_button': no_date_button,
                    'upcoming_button': upcoming_button,
                    'medical_url': medical_url
                }

                html_message = template.get_formatted_body(context)
                message = self._format_email_message(organization, no_date, overdue, upcoming)  # Текстовая версия

                self.stdout.write(self.style.SUCCESS(
                    f'✅ HTML письмо сформировано, размер: {len(html_message)} символов'
                ))
            else:
                self.stdout.write(self.style.WARNING(
                    f'⚠️ Шаблон не найден! Используется текстовый формат.'
                ))
                # Fallback: используем текстовый формат
                subject = f'📋 План прохождения медицинских осмотров - {organization.short_name_ru} - {datetime.now().strftime("%d.%m.%Y")}'
                message = self._format_email_message(organization, no_date, overdue, upcoming)
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
                    html_message=html_message,  # Добавляем HTML версию
                )
                self.stdout.write(
                    self.style.SUCCESS(
                        f'✅ Уведомление отправлено для {organization.short_name_ru}!\n'
                        f'   Получатели: {", ".join(recipient_list)}\n'
                        f'   Без даты: {len(no_date)}, Просроченные: {len(overdue)}, Предстоящие: {len(upcoming)}'
                    )
                )
                total_sent += 1

                # Логируем успешную отправку
                send_log.no_date_count = len(no_date)
                send_log.expired_count = len(overdue)
                send_log.upcoming_count = len(upcoming)
                send_log.successful_count = 1
                send_log.status = 'completed'
                send_log.save()

                MedicalNotificationSendDetail.objects.create(
                    send_log=send_log,
                    status='success',
                    recipients=json.dumps(recipient_list),
                    recipients_count=len(recipient_list),
                    employees_total=len(no_date) + len(overdue) + len(upcoming),
                    no_date_count=len(no_date),
                    expired_count=len(overdue),
                    upcoming_count=len(upcoming),
                    email_subject=subject,
                    sent_at=timezone.now()
                )

            except Exception as e:
                self.stdout.write(
                    self.style.ERROR(f'❌ Ошибка при отправке email для {organization.short_name_ru}: {str(e)}')
                )
                total_failed += 1

                # Логируем ошибку отправки
                send_log.no_date_count = len(no_date)
                send_log.expired_count = len(overdue)
                send_log.upcoming_count = len(upcoming)
                send_log.failed_count = 1
                send_log.status = 'failed'
                send_log.save()

                MedicalNotificationSendDetail.objects.create(
                    send_log=send_log,
                    status='failed',
                    recipients=json.dumps(recipient_list),
                    recipients_count=len(recipient_list),
                    employees_total=len(no_date) + len(overdue) + len(upcoming),
                    no_date_count=len(no_date),
                    expired_count=len(overdue),
                    upcoming_count=len(upcoming),
                    email_subject=subject,
                    error_message=str(e),
                    skip_reason='email_send_failed'
                )

        # Итоговая статистика
        self.stdout.write('\n' + '=' * 60)
        self.stdout.write(
            self.style.SUCCESS(f'Завершено! Отправлено: {total_sent}, Ошибок: {total_failed}')
        )

    def _format_email_message(self, organization, no_date, overdue, upcoming):
        """Форматирует текст email сообщения"""
        lines = []
        lines.append('📋 ПЛАН ПРОХОЖДЕНИЯ МЕДИЦИНСКИХ ОСМОТРОВ')
        lines.append('=' * 60)
        lines.append(f'Организация: {organization.full_name_ru}')
        lines.append(f'Дата отчета: {datetime.now().strftime("%d.%m.%Y %H:%M")}')
        lines.append('')

        # Без даты
        if no_date:
            lines.append(f'📋 ТРЕБУЕТСЯ ВНЕСТИ ДАТУ МЕДОСМОТРА ({len(no_date)} сотрудников):')
            lines.append('-' * 60)
            for item in no_date:
                emp = item['employee']
                status = item['status']
                factors = ', '.join([f['short_name'] for f in status['factors']])
                lines.append(
                    f'  • {emp.full_name_nominative}\n'
                    f'    Должность: {emp.position.position_name}\n'
                    f'    Организация: {emp.organization.short_name_ru}\n'
                    f'    Факторы: {factors}\n'
                    f'    Мин. периодичность: {status["min_periodicity"]} мес.\n'
                )
            lines.append('')

        # Просроченные
        if overdue:
            lines.append(f'🚨 ПРОСРОЧЕННЫЕ МЕДОСМОТРЫ ({len(overdue)} сотрудников):')
            lines.append('-' * 60)
            for item in overdue:
                emp = item['employee']
                status = item['status']
                factors = ', '.join([f['short_name'] for f in status['factors']])
                days_overdue = abs(status['days_until'])
                lines.append(
                    f'  • {emp.full_name_nominative}\n'
                    f'    Должность: {emp.position.position_name}\n'
                    f'    Организация: {emp.organization.short_name_ru}\n'
                    f'    Факторы: {factors}\n'
                    f'    Дата МО: {status["date_completed"].strftime("%d.%m.%Y")}\n'
                    f'    Просрочено: {days_overdue} дней\n'
                )
            lines.append('')

        # Предстоящие
        if upcoming:
            lines.append(f'⚠️ ПРЕДСТОЯЩИЕ МЕДОСМОТРЫ ({len(upcoming)} сотрудников):')
            lines.append('-' * 60)
            for item in upcoming:
                emp = item['employee']
                status = item['status']
                factors = ', '.join([f['short_name'] for f in status['factors']])
                lines.append(
                    f'  • {emp.full_name_nominative}\n'
                    f'    Должность: {emp.position.position_name}\n'
                    f'    Организация: {emp.organization.short_name_ru}\n'
                    f'    Факторы: {factors}\n'
                    f'    Следующий МО: {status["next_date"].strftime("%d.%m.%Y")}\n'
                    f'    Осталось: {status["days_until"]} дней\n'
                )
            lines.append('')

        # Итого
        lines.append('=' * 60)
        lines.append(f'ИТОГО: Без даты: {len(no_date)}, Просроченные: {len(overdue)}, Предстоящие: {len(upcoming)}')
        lines.append('')
        lines.append('---')
        lines.append('Это автоматическое уведомление из системы управления охраной труда OT_online')

        return '\n'.join(lines)

    def _format_html_section(self, employees_data, section_type):
        """
        Формирует HTML секцию для списка сотрудников.

        Args:
            employees_data: список словарей с данными сотрудников
            section_type: тип секции ('overdue', 'upcoming', 'no_date')

        Returns:
            str: HTML код секции
        """
        if not employees_data:
            return ''

        # Определяем стили и заголовок в зависимости от типа
        if section_type == 'overdue':
            bg_color = '#ffebee'
            border_color = '#f44336'
            title_color = '#d32f2f'
            emoji = '🚨'
            title = f'ТРЕБУЕТСЯ СРОЧНОЕ ВНИМАНИЕ: Просроченные медосмотры ({len(employees_data)})'
        elif section_type == 'upcoming':
            bg_color = '#fff3e0'
            border_color = '#ff9800'
            title_color = '#f57c00'
            emoji = '🕐'
            title = f'Предстоящие медосмотры в течение 30 дней ({len(employees_data)})'
        else:  # no_date
            bg_color = '#e3f2fd'
            border_color = '#2196f3'
            title_color = '#1976d2'
            emoji = '📋'
            title = f'Требуется внести дату медосмотра ({len(employees_data)})'

        # Формируем список сотрудников
        employees_html = []
        for item in employees_data:
            emp = item['employee']
            status = item['status']
            factors = ', '.join([f['short_name'] for f in status['factors']])

            # Базовая информация
            emp_html = f"""
            <div style="background-color: white; padding: 15px; margin: 10px 0; border-radius: 5px; border-left: 3px solid {border_color};">
                <div style="font-weight: 600; font-size: 16px; color: #333; margin-bottom: 8px;">
                    {emp.full_name_nominative}
                </div>
                <div style="color: #666; font-size: 14px; line-height: 1.6;">
                    <strong>Должность:</strong> {emp.position.position_name}<br>
                    <strong>Факторы:</strong> {factors}
"""

            # Дополнительная информация в зависимости от типа
            if section_type == 'overdue' and status.get('date_completed'):
                days_overdue = abs(status['days_until'])
                emp_html += f"""
                    <br><strong>Дата медосмотра:</strong> {status['date_completed'].strftime('%d.%m.%Y')}
                    <br><strong style="color: #d32f2f;">⚠️ Просрочено:</strong> <span style="color: #d32f2f; font-weight: 600;">{days_overdue} дней</span>
"""
            elif section_type == 'upcoming' and status.get('next_date'):
                emp_html += f"""
                    <br><strong>Следующий медосмотр:</strong> {status['next_date'].strftime('%d.%m.%Y')}
                    <br><strong>Осталось:</strong> <span style="color: #f57c00; font-weight: 600;">{status['days_until']} дней</span>
"""
            elif section_type == 'no_date' and status.get('min_periodicity'):
                emp_html += f"""
                    <br><strong>Минимальная периодичность:</strong> {status['min_periodicity']} мес.
"""

            emp_html += """
                </div>
            </div>
"""
            employees_html.append(emp_html)

        # Собираем секцию
        section_html = f"""
        <div style="background-color: {bg_color}; border-left: 4px solid {border_color}; padding: 20px; margin: 20px 0; border-radius: 5px;">
            <h3 style="color: {title_color}; margin-top: 0;">
                {emoji} {title}
            </h3>
            {''.join(employees_html)}
        </div>
"""

        return section_html
