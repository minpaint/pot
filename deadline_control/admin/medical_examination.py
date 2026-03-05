# 📂 deadline_control/admin/medical_examination.py

import logging
from datetime import timedelta, datetime
from django.contrib import admin
from django.contrib.admin import SimpleListFilter
from django.db.models import Exists, OuterRef
from django.utils import timezone
from django.utils.html import format_html
from django.http import HttpResponseRedirect

from deadline_control.models import (
    MedicalExaminationType,
    HarmfulFactor,
    MedicalSettings,
    MedicalExaminationNorm,
    PositionMedicalFactor,
    EmployeeMedicalExamination,
)
from deadline_control.forms.medical_examination import (
    PositionNormForm,
    HarmfulFactorNormFormSet,
    HarmfulFactorNormForm,
    HarmfulFactorNormFormWithCounter,
)
from directory.models.position import Position
from directory.admin.mixins.org_filter import apply_session_org_filter

# Настройка логирования
logger = logging.getLogger(__name__)


# ------------------------------------------------------------------
# 🔧 Справочники
# ------------------------------------------------------------------

@admin.register(MedicalExaminationType)
class MedicalExaminationTypeAdmin(admin.ModelAdmin):
    """Админка для типов медосмотров"""
    list_display = ("name",)
    search_fields = ("name",)


@admin.register(HarmfulFactor)
class HarmfulFactorAdmin(admin.ModelAdmin):
    list_display = ("short_name", "full_name", "periodicity")
    search_fields = ("short_name", "full_name",)
    form = HarmfulFactorNormFormWithCounter

    change_list_template = "admin/deadline_control/harmful_factor/change_list.html"

    class Media:
        js = ('admin/js/harmful_factor_char_counter.js',)

    def get_urls(self):
        from django.urls import path
        urls = super().get_urls()
        custom_urls = [
            path('import/', self.import_view, name='deadline_control_harmfulfactor_import'),
            path('export/', self.export_view, name='deadline_control_harmfulfactor_export'),
        ]
        return custom_urls + urls

    def import_view(self, request):
        """Импорт вредных факторов"""
        from django.shortcuts import render, redirect
        from django.contrib import messages
        from tablib import Dataset
        from directory.resources.harmful_factor import HarmfulFactorResource

        context = self.admin_site.each_context(request)

        if request.method == 'POST':
            if "confirm" in request.POST:
                dataset_data = request.session.get("harmful_factor_dataset")
                if not dataset_data:
                    messages.error(request, "Сессия с набором данных не найдена. Загрузите файл снова.")
                    return redirect("admin:deadline_control_harmfulfactor_import")

                dataset = Dataset().load(dataset_data)
                resource = HarmfulFactorResource()
                result = resource.import_data(dataset, dry_run=False)

                del request.session["harmful_factor_dataset"]

                if result.has_errors():
                    messages.error(request, f"⚠ Импорт завершён с ошибками! Новых: {result.totals['new']}, ошибок: {result.totals['error']}")
                else:
                    messages.success(request, f"✔ Импорт завершён! Новых: {result.totals['new']}, обновлено: {result.totals['update']}")
                return redirect("admin:deadline_control_harmfulfactor_changelist")
            else:
                import_file = request.FILES.get("import_file")
                if not import_file:
                    messages.error(request, "Файл не выбран")
                    return redirect("admin:deadline_control_harmfulfactor_import")

                file_format = import_file.name.split('.')[-1].lower()
                if file_format not in ["xlsx", "xls"]:
                    messages.error(request, "Поддерживаются только файлы XLSX и XLS")
                    return redirect("admin:deadline_control_harmfulfactor_import")

                try:
                    dataset = Dataset().load(import_file.read(), format=file_format)
                    resource = HarmfulFactorResource()
                    result = resource.import_data(dataset, dry_run=True)

                    request.session["harmful_factor_dataset"] = dataset.export("json")

                    context.update({
                        "title": "Предпросмотр импорта вредных факторов",
                        "result": result,
                        "dataset": dataset,
                    })
                    return render(request, "admin/deadline_control/harmful_factor/import_preview.html", context)
                except Exception as e:
                    messages.error(request, f"Ошибка при обработке файла: {str(e)}")
                    return redirect("admin:deadline_control_harmfulfactor_import")

        context.update({
            "title": "Импорт вредных факторов",
            "subtitle": None,
        })
        return render(request, "admin/deadline_control/harmful_factor/import.html", context)
    def export_view(self, request):
        """📤 Экспорт вредных факторов"""
        from django.http import HttpResponse
        from directory.resources.harmful_factor import HarmfulFactorResource

        resource = HarmfulFactorResource()
        dataset = resource.export()
        response = HttpResponse(dataset.xlsx, content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
        response['Content-Disposition'] = 'attachment; filename="harmful_factors.xlsx"'
        return response


@admin.register(MedicalSettings)
class MedicalSettingsAdmin(admin.ModelAdmin):
    list_display = ("organization", "days_before_issue", "days_before_email", "has_template", "send_notification_button")
    list_filter = ("organization",)
    search_fields = ("organization__short_name_ru", "organization__full_name_ru")

    fieldsets = (
        ('Организация', {
            'fields': ('organization',)
        }),
        ('Уведомления', {
            'fields': ('days_before_issue', 'days_before_email')
        }),
        ('Шаблоны документов', {
            'fields': ('referral_template',),
            'description': '<strong>Шаблон направления на медосмотр (необязательно):</strong><br>'
                          '• Если шаблон НЕ загружен - используется <strong>эталонный шаблон</strong> системы<br>'
                          '• Если шаблон загружен - будет использоваться <strong>ваш шаблон</strong> для этой организации<br>'
                          '• Формат: DOCX с переменными docxtpl'
        }),
    )

    def has_template(self, obj):
        return bool(obj.referral_template)
    has_template.boolean = True
    has_template.short_description = "Шаблон загружен"

    def get_queryset(self, request):
        """Фильтруем по организациям пользователя"""
        qs = super().get_queryset(request)
        if not request.user.is_superuser and hasattr(request.user, 'profile'):
            allowed_orgs = request.user.profile.organizations.all()
            qs = qs.filter(organization__in=allowed_orgs)
        qs = apply_session_org_filter(request, qs)
        return qs.select_related('organization')

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        """Показываем только организации, доступные пользователю"""
        if db_field.name == "organization":
            if not request.user.is_superuser and hasattr(request.user, 'profile'):
                kwargs["queryset"] = request.user.profile.organizations.all()
        return super().formfield_for_foreignkey(db_field, request, **kwargs)

    def send_notification_button(self, obj):
        """Кнопка для отправки уведомлений о медосмотрах"""
        return format_html(
            '<a class="button" href="{}?action=send_medical_notification" style="padding:4px 12px;">📧 Отправить уведомление</a>',
            f'/admin/deadline_control/medicalsettings/{obj.pk}/change/'
        )

    send_notification_button.short_description = "Действия"

    def change_view(self, request, object_id, form_url='', extra_context=None):
        """Обработка кастомных действий перед отображением страницы редактирования"""
        if "action" in request.GET and request.GET["action"] == "send_medical_notification":
            # Получаем объект
            obj = self.get_object(request, object_id)
            if obj:
                # Выполняем отправку
                self.send_medical_notification(request, obj)
                # Редиректим обратно на список
                from django.http import HttpResponseRedirect
                from django.urls import reverse
                return HttpResponseRedirect(reverse('admin:deadline_control_medicalsettings_changelist'))

        return super().change_view(request, object_id, form_url, extra_context)

    def send_medical_notification(self, request, medical_settings):
        """Отправка уведомлений о медосмотрах для организации"""
        from django.contrib import messages
        from django.core.mail import send_mail
        from deadline_control.models import EmailSettings, MedicalNotificationSendLog, MedicalNotificationSendDetail
        from directory.models import Employee
        from directory.utils.email_recipients import collect_recipients_for_subdivision
        import json

        organization = medical_settings.organization

        # Получаем настройки email для организации
        try:
            email_settings = EmailSettings.get_settings(organization)
        except Exception as e:
            messages.error(request, f"❌ Не удалось получить настройки email: {str(e)}")
            return

        # Проверяем активность настроек
        if not email_settings.is_active:
            messages.error(request, f"❌ Email уведомления отключены для {organization.short_name_ru}")
            return

        if not email_settings.email_host:
            messages.error(request, f"❌ SMTP сервер не настроен для {organization.short_name_ru}")
            return

        # Создаём лог рассылки
        send_log = MedicalNotificationSendLog.objects.create(
            organization=organization,
            initiated_by=request.user,
            notification_type='manual'
        )

        # Собираем получателей (subdivision=None означает сбор только из EmailSettings)
        original_recipient_list = collect_recipients_for_subdivision(
            subdivision=None,
            organization=organization
        )

        # Фильтруем получателей от некорректных email (защита от IDNA ошибок)
        recipient_list = self._filter_valid_emails(original_recipient_list)

        # Если были отфильтрованы адреса - предупреждаем
        if len(recipient_list) < len(original_recipient_list):
            filtered_count = len(original_recipient_list) - len(recipient_list)
            messages.warning(
                request,
                f'⚠️ Отфильтровано {filtered_count} некорректных email адресов. '
                f'Проверьте настройки EmailSettings и исправьте адреса с двойными точками или другими ошибками.'
            )

        if not recipient_list:
            messages.warning(
                request,
                f'⚠️ Нет получателей для {organization.short_name_ru}. '
                f'Настройте EmailSettings или добавьте получателей в подразделения.'
            )
            send_log.status = 'completed'
            send_log.skipped_count = 1
            send_log.save()
            MedicalNotificationSendDetail.objects.create(
                send_log=send_log,
                status='skipped',
                skip_reason='no_recipients',
                error_message='Нет получателей. Настройте EmailSettings'
            )
            return

        # Получаем ВСЕХ сотрудников организации (включая тех, у кого вообще нет медосмотров)
        employees_qs = Employee.objects.filter(
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
            messages.warning(request, f'⚠️ Нет данных для отправки для {organization.short_name_ru}')
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
            return

        # Получаем шаблон письма
        from deadline_control.models import EmailTemplate, EmailTemplateType

        try:
            template_type = EmailTemplateType.objects.get(code='medical_examination')
            template = EmailTemplate.objects.filter(
                organization=organization,
                template_type=template_type,
                is_active=True,
                is_default=True
            ).first()
        except EmailTemplateType.DoesNotExist:
            template = None

        # Формируем текст письма
        if template:
            # Используем HTML шаблон
            subject = template.get_formatted_subject({
                'organization_name': organization.short_name_ru
            })

            # Формируем HTML секции
            overdue_section = self._format_html_section(overdue, 'overdue') if overdue else ''
            upcoming_section = self._format_html_section(upcoming, 'upcoming') if upcoming else ''
            no_date_section = self._format_html_section(no_date, 'no_date') if no_date else ''

            # Формируем контекст для шаблона
            medical_url = request.build_absolute_uri('/deadline-control/medical/')

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
        else:
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

            messages.success(
                request,
                f'✅ Уведомление о медосмотрах отправлено!\n'
                f'Получатели: {", ".join(recipient_list)}\n'
                f'Без даты: {len(no_date)}, Просроченные: {len(overdue)}, Предстоящие: {len(upcoming)}'
            )

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
            messages.error(request, f'❌ Ошибка при отправке email: {str(e)}')

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
        lines.append('Это уведомление из системы управления охраной труда OT_online')
        lines.append('Отправлено вручную администратором')

        return '\n'.join(lines)

    def _filter_valid_emails(self, email_list):
        """
        Фильтрует список email адресов, удаляя некорректные (защита от IDNA ошибок).
        Возвращает список только валидных email адресов.
        """
        from django.core.validators import validate_email
        from django.core.exceptions import ValidationError as DjangoValidationError

        valid_emails = []

        for email in email_list:
            if not email or not email.strip():
                continue

            email = email.strip()

            # Проверка на двойные точки
            if '..' in email:
                logger.warning(f"Пропускаем некорректный email (двойные точки): {email}")
                continue

            # Проверка на точку в начале/конце
            if email.startswith('.') or email.endswith('.'):
                logger.warning(f"Пропускаем некорректный email (точка в начале/конце): {email}")
                continue

            # Проверка формата email
            try:
                validate_email(email)
            except DjangoValidationError:
                logger.warning(f"Пропускаем некорректный email (неверный формат): {email}")
                continue

            # Проверка IDNA кодирования домена
            if '@' in email:
                try:
                    _, domain = email.rsplit('@', 1)
                    domain.encode('idna')
                    valid_emails.append(email)
                except Exception as e:
                    logger.warning(f"Пропускаем некорректный email (IDNA ошибка): {email} - {str(e)}")
                    continue
            else:
                # Email без @ - игнорируем
                logger.warning(f"Пропускаем некорректный email (нет @): {email}")
                continue

        return valid_emails

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


# ------------------------------------------------------------------
# 📑 Эталонные нормы — древовидное представление
# ------------------------------------------------------------------

@admin.register(MedicalExaminationNorm)
class MedicalExaminationNormAdmin(admin.ModelAdmin):
    change_list_template = "admin/directory/medicalnorm/change_list_tree.html"

    list_display = ("position_name", "harmful_factor", "periodicity")
    list_filter = ("harmful_factor",)
    search_fields = ("position_name",)

    # Отключаем стандартное добавление - используем только add_multiple
    def has_add_permission(self, request):
        return False

    def get_urls(self):
        from django.urls import path
        urls = super().get_urls()
        custom_urls = [
            path('add-multiple/', self.add_multiple_view, name='deadline_control_medicalexaminationnorm_add_multiple'),
        ]
        return custom_urls + urls

    def add_multiple_view(self, request):
        """
        View для добавления/редактирования множественных вредных факторов к профессии
        """
        from django.shortcuts import render, redirect
        from django.contrib import messages
        from django.forms import formset_factory

        context = self.admin_site.each_context(request)

        # Получаем position_id из GET параметров
        position_id = request.GET.get('position')
        initial_position_name = ''
        existing_norms = []

        # Если передан position_id, загружаем существующие нормы
        if position_id:
            try:
                position = Position.objects.get(pk=position_id)
                initial_position_name = position.position_name
                # Загружаем существующие нормы для этой профессии
                existing_norms = MedicalExaminationNorm.objects.filter(
                    position_name=initial_position_name
                ).select_related('harmful_factor')
            except Position.DoesNotExist:
                pass

        if request.method == 'POST':
            position_form = PositionNormForm(request.POST)
            formset = HarmfulFactorNormFormSet(request.POST)

            if position_form.is_valid() and formset.is_valid():
                position_name = position_form.cleaned_data['position_name']
                created_count = 0
                deleted_count = 0

                # Собираем список факторов, которые должны остаться
                factors_to_keep = set()

                for form in formset:
                    if form.cleaned_data and not form.cleaned_data.get('DELETE', False):
                        harmful_factor = form.cleaned_data.get('harmful_factor')
                        if harmful_factor:
                            factors_to_keep.add(harmful_factor.id)

                            # Проверяем, существует ли уже такая норма
                            existing = MedicalExaminationNorm.objects.filter(
                                position_name=position_name,
                                harmful_factor=harmful_factor
                            ).first()

                            if existing:
                                # Обновляем существующую норму
                                existing.periodicity_override = form.cleaned_data.get('periodicity_override')
                                existing.notes = form.cleaned_data.get('notes', '')
                                existing.save()
                            else:
                                # Создаём новую норму
                                MedicalExaminationNorm.objects.create(
                                    position_name=position_name,
                                    harmful_factor=harmful_factor,
                                    periodicity_override=form.cleaned_data.get('periodicity_override'),
                                    notes=form.cleaned_data.get('notes', '')
                                )
                                created_count += 1

                # Удаляем нормы, которые были отмечены на удаление
                for form in formset:
                    if form.cleaned_data and form.cleaned_data.get('DELETE', False):
                        harmful_factor = form.cleaned_data.get('harmful_factor')
                        if harmful_factor:
                            deleted = MedicalExaminationNorm.objects.filter(
                                position_name=position_name,
                                harmful_factor=harmful_factor
                            ).delete()
                            if deleted[0] > 0:
                                deleted_count += 1

                msg_parts = []
                if created_count > 0:
                    msg_parts.append(f'создано: {created_count}')
                if deleted_count > 0:
                    msg_parts.append(f'удалено: {deleted_count}')

                if msg_parts:
                    messages.success(request, f'✅ Изменения сохранены ({", ".join(msg_parts)})')
                else:
                    messages.info(request, 'Изменений не было')

                return redirect('admin:deadline_control_medicalexaminationnorm_changelist')
        else:
            # Инициализация форм
            position_form = PositionNormForm(initial={'position_name': initial_position_name})

            # Формируем initial data для formset из существующих норм
            initial_data = []
            for norm in existing_norms:
                initial_data.append({
                    'harmful_factor': norm.harmful_factor,
                    'periodicity_override': norm.periodicity_override,
                    'notes': norm.notes,
                })

            # Создаём formset с нужным количеством extra форм
            if initial_data:
                # Если есть существующие данные, показываем их + 1 пустую форму
                CustomFormSet = formset_factory(
                    HarmfulFactorNormForm,
                    extra=1,
                    can_delete=True
                )
                formset = CustomFormSet(initial=initial_data)
            else:
                # Если нет данных, показываем 1 пустую форму
                formset = HarmfulFactorNormFormSet()

        context.update({
            'title': 'Редактировать вредные факторы профессии' if existing_norms else 'Добавить вредные факторы для профессии',
            'position_form': position_form,
            'formset': formset,
            'opts': self.model._meta,
            'existing_norms': existing_norms,
        })

        return render(request, 'admin/directory/medicalnorm/add_multiple.html', context)

    def changelist_view(self, request, extra_context=None):
        """
        Формируем контекст professions = [{ name, norms, has_overrides }, ...],
        чтобы шаблон показывал дерево с индикаторами переопределений.
        """
        extra_context = extra_context or {}

        # Все уникальные имена профессий из норм
        names = MedicalExaminationNorm.objects.values_list(
            "position_name", flat=True
        ).distinct().order_by("position_name")

        # Получаем информацию о профессиях с переопределениями
        overridden_professions = set(
            PositionMedicalFactor.objects.values_list(
                "position__position_name", flat=True
            ).distinct()
        )

        professions = []
        for name in names:
            # Нормы для этой профессии
            norms = MedicalExaminationNorm.objects.filter(
                position_name=name
            ).select_related("harmful_factor")

            # Проверяем, есть ли переопределения
            has_overrides = name in overridden_professions

            # Находим эталонную (первую) должность с таким названием
            reference_position = Position.objects.filter(position_name=name).first()

            professions.append({
                "name": name,
                "norms": norms,
                "has_overrides": has_overrides,
                "reference_position": reference_position  # Добавляем ссылку на эталонную должность
            })

        extra_context["professions"] = professions
        return super().changelist_view(request, extra_context)


# ------------------------------------------------------------------
# 👨‍⚕️ Журнал медосмотров сотрудников
# ------------------------------------------------------------------

class DeadlineWindowFilter(SimpleListFilter):
    """Фильтр по сроку: просрочено / скоро / позже / без даты."""
    title = "Срок"
    parameter_name = "deadline_state"

    def lookups(self, request, model_admin):
        return (
            ("overdue", "Просрочено"),
            ("soon", "До 14 дней"),
            ("future", "Больше 14 дней"),
            ("nodate", "Без даты"),
        )

    def queryset(self, request, queryset):
        value = self.value()
        today = timezone.now().date()
        warning_date = today + timedelta(days=14)

        if value == "overdue":
            return queryset.filter(next_date__lt=today)
        if value == "soon":
            return queryset.filter(next_date__gte=today, next_date__lte=warning_date)
        if value == "future":
            return queryset.filter(next_date__gt=warning_date)
        if value == "nodate":
            return queryset.filter(next_date__isnull=True)
        return queryset


@admin.register(EmployeeMedicalExamination)
class EmployeeMedicalExaminationAdmin(admin.ModelAdmin):
    list_display = (
        "employee", "employee_organization", "harmful_factor", "deadline_badge",
    )
    list_filter = (DeadlineWindowFilter, "status", "harmful_factor", "employee__organization")
    search_fields = ("employee__full_name_nominative", "employee__organization__short_name_ru")
    date_hierarchy = "date_completed"
    list_select_related = ("employee", "employee__organization", "harmful_factor")
    ordering = ("next_date",)
    list_per_page = 50

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if not request.user.is_superuser and hasattr(request.user, 'profile'):
            allowed_orgs = request.user.profile.organizations.all()
            qs = qs.filter(employee__organization__in=allowed_orgs)
        qs = apply_session_org_filter(
            request,
            qs,
            organization_lookup='employee__organization_id',
            get_filter_keys=('employee__organization__id__exact', 'employee__organization_id'),
        )
        return qs

    def employee_organization(self, obj):
        org = getattr(obj.employee, "organization", None)
        return org.short_name_ru if org else "-"
    employee_organization.short_description = "Организация"
    employee_organization.admin_order_field = "employee__organization__short_name_ru"

    def deadline_badge(self, obj):
        """Компактный бейдж со сроком и подсветкой."""
        if not obj.next_date:
            return format_html('<span style="background:#9e9e9e;color:white;padding:2px 8px;border-radius:6px;">Без даты</span>')

        days = obj.days_until_next()
        color = "#4caf50"
        label = f"{obj.next_date} · {days} дн."

        if days is None:
            color = "#9e9e9e"
            label = f"{obj.next_date}"
        elif days < 0:
            color = "#f44336"
            label = f"{obj.next_date} · -{abs(days)} дн."
        elif days <= 14:
            color = "#ff9800"
            label = f"{obj.next_date} · {days} дн."

        return format_html(
            '<span style="background:{bg};color:white;padding:2px 8px;border-radius:6px;font-weight:600;">{text}</span>',
            bg=color,
            text=label,
        )

    deadline_badge.short_description = "Срок"
    deadline_badge.admin_order_field = "next_date"
