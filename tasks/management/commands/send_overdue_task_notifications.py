# tasks/management/commands/send_overdue_task_notifications.py
"""
Отправка email-уведомлений о просроченных задачах.
Запуск: python manage.py send_overdue_task_notifications --settings=settings_prod
Cron:   0 9 * * 1  (понедельник в 9:00)
"""
from django.core.management.base import BaseCommand
from django.core.mail import send_mail
from django.utils import timezone

from directory.models import Organization
from deadline_control.models import EmailSettings
from tasks.models import TaskList


class Command(BaseCommand):
    help = 'Отправляет email-уведомления о просроченных задачах по организациям'

    def add_arguments(self, parser):
        parser.add_argument(
            '--organization', type=int,
            help='ID организации (по умолчанию — все)',
        )
        parser.add_argument(
            '--emails', type=str,
            help='Тестовые адреса через запятую',
        )
        parser.add_argument(
            '--dry-run', action='store_true',
            help='Только вывести отчёт, не отправлять письма',
        )

    def handle(self, *args, **options):
        today = timezone.now().date()

        # Настройки email
        email_settings = EmailSettings.objects.first()
        if not email_settings and not options['dry_run']:
            self.stdout.write(self.style.ERROR('EmailSettings не настроены. Выход.'))
            return

        # Организации
        if options['organization']:
            orgs = Organization.objects.filter(pk=options['organization'])
        else:
            orgs = Organization.objects.all()

        total_sent = 0
        total_skipped = 0

        for org in orgs:
            # Списки с просроченными задачами
            lists_with_overdue = (
                TaskList.objects
                .filter(organization=org, is_archived=False)
                .prefetch_related('items')
            )

            overdue_items = []
            for tl in lists_with_overdue:
                for item in tl.items.filter(is_done=False, due_date__lt=today):
                    overdue_items.append((tl, item))

            if not overdue_items:
                self.stdout.write(f'  {org.short_name_ru}: нет просроченных задач')
                total_skipped += 1
                continue

            # Формируем письмо
            lines = [f'Просроченные задачи для {org.short_name_ru}:', '']
            for tl, item in overdue_items:
                days = (today - item.due_date).days
                priority_label = item.get_priority_display()
                lines.append(
                    f'  [{priority_label}] {item.text}\n'
                    f'    Список: {tl.title} | Срок: {item.due_date:%d.%m.%Y} (просрочено {days} дн.)'
                )

            body = '\n'.join(lines)
            subject = f'[OT_online] Просроченные задачи: {org.short_name_ru} ({len(overdue_items)} шт.)'

            # Получатели
            if options['emails']:
                recipients = [e.strip() for e in options['emails'].split(',') if e.strip()]
            else:
                # Берём email из профиля организации (если есть) — иначе email из настроек
                recipients = []
                try:
                    from directory.models import Profile
                    for profile in Profile.objects.filter(organizations=org):
                        if profile.user.email:
                            recipients.append(profile.user.email)
                except Exception:
                    pass
                if not recipients and email_settings:
                    recipients = [email_settings.default_from_email or email_settings.email_host_user]

            if not recipients:
                self.stdout.write(self.style.WARNING(
                    f'  {org.short_name_ru}: нет получателей, пропускаем'
                ))
                total_skipped += 1
                continue

            self.stdout.write(
                f'  {org.short_name_ru}: {len(overdue_items)} просроченных задач → {recipients}'
            )

            if options['dry_run']:
                self.stdout.write(self.style.WARNING('  [dry-run] Письмо НЕ отправлено'))
                self.stdout.write(body)
                continue

            try:
                from_email = email_settings.default_from_email or email_settings.email_host_user
                send_mail(
                    subject=subject,
                    message=body,
                    from_email=from_email,
                    recipient_list=recipients,
                    fail_silently=False,
                )
                self.stdout.write(self.style.SUCCESS(f'  ✓ Отправлено'))
                total_sent += 1
            except Exception as e:
                self.stdout.write(self.style.ERROR(f'  ✗ Ошибка: {e}'))

        self.stdout.write(self.style.SUCCESS(
            f'\nГотово. Отправлено: {total_sent}, пропущено: {total_skipped}'
        ))
