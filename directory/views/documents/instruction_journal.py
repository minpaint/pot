# directory/views/documents/instruction_journal.py

from collections import defaultdict
from datetime import date, datetime
import logging
from io import BytesIO
from zipfile import ZipFile

from django.views.generic import TemplateView
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from django.contrib import messages
from django.http import HttpResponse, JsonResponse
from django.utils.html import strip_tags

from directory.models import Employee, Organization
from directory.utils.permissions import AccessControlHelper

# Настройка логирования
logger = logging.getLogger(__name__)


def has_employee_instructions(emp):
    """Проверяет наличие хотя бы одного номера инструкции у должности."""
    position = emp.position
    return bool(
        (position.safety_instructions_numbers and position.safety_instructions_numbers.strip()) or
        (position.contract_safety_instructions and position.contract_safety_instructions.strip()) or
        (position.company_vehicle_instructions and position.company_vehicle_instructions.strip())
    )


def group_employees_by_department(employees):
    """
    Делит сотрудников на основное подразделение и отделы, оставляя только тех, у кого есть инструкции.
    """
    subdivision_employees = []
    departments_employees = defaultdict(list)

    for emp in employees:
        if not has_employee_instructions(emp):
            continue
        if emp.department:
            departments_employees[emp.department].append(emp)
        else:
            subdivision_employees.append(emp)

    return subdivision_employees, departments_employees


def extract_unique_emails(recipient_items):
    """
    Возвращает уникальные email, сохраняя порядок.
    recipient_items: список словарей с ключом email.
    """
    seen = set()
    unique = []
    for item in recipient_items:
        email_value = (item.get('email') or '').strip().lower()
        if email_value and email_value not in seen:
            seen.add(email_value)
            unique.append(email_value)
    return unique


def format_briefing_date_for_template(briefing_date_value):
    """Преобразует дату для подстановки в шаблон письма."""
    if not briefing_date_value:
        return date.today().strftime('%d.%m.%Y')
    try:
        return datetime.strptime(briefing_date_value, '%Y-%m-%d').strftime('%d.%m.%Y')
    except Exception:
        return briefing_date_value


class InstructionJournalView(LoginRequiredMixin, TemplateView):
    """
    Представление для формирования образца заполнения журнала повторных инструктажей.
    Использует древовидное представление: Организация → Подразделение → Отдел.

    Позволяет:
    - Выбрать дату повторного инструктажа
    - Выбрать сотрудников через галочки
    - Скачать единый файл со всеми выбранными сотрудниками
    - Скачать ZIP с отдельными файлами по подразделениям
    """
    template_name = 'directory/documents/instruction_journal_tree.html'

    def get_base_queryset(self):
        """Возвращает базовый queryset всех активных сотрудников с должностью"""
        qs = Employee.objects.active_for_operations().select_related(
            'organization', 'subdivision', 'department', 'position'
        )
        # Фильтруем по правам доступа
        qs = AccessControlHelper.filter_queryset(qs, self.request.user, self.request)
        # Только сотрудники с должностью
        qs = qs.filter(position__isnull=False)
        return qs.order_by(
            'organization__short_name_ru',
            'subdivision__name',
            'department__name',
            'full_name_nominative'
        )

    def build_tree_structure(self, employees):
        """
        Строит древовидную структуру: Организация → Подразделение → Отдел → Сотрудники.

        Возвращает словарь вида:
        {
            organization: {
                'name': str,
                'items': [employee_data],
                'subdivisions': {
                    subdivision: {
                        'name': str,
                        'items': [employee_data],
                        'departments': {
                            department: {
                                'name': str,
                                'items': [employee_data]
                            }
                        }
                    }
                }
            }
        }
        где employee_data = {
            'employee': Employee объект,
            'has_instructions': bool,
            'instructions': str
        }
        """
        tree = {}

        for emp in employees:
            org = emp.organization
            sub = emp.subdivision
            dept = emp.department

            # Проверяем наличие инструкций у должности
            position = emp.position
            has_instructions = bool(
                (position.safety_instructions_numbers and position.safety_instructions_numbers.strip()) or
                (position.contract_safety_instructions and position.contract_safety_instructions.strip()) or
                (position.company_vehicle_instructions and position.company_vehicle_instructions.strip())
            )

            # Формируем данные о сотруднике
            employee_data = {
                'employee': emp,
                'has_instructions': has_instructions,
                'instructions': position.safety_instructions_numbers or ''
            }

            # Инициализируем организацию
            if org not in tree:
                tree[org] = {
                    'name': org.short_name_ru,
                    'items': [],
                    'subdivisions': {}
                }

            # Если нет подразделения, добавляем сотрудника напрямую к организации
            if not sub:
                tree[org]['items'].append(employee_data)
                continue

            # Инициализируем подразделение
            if sub not in tree[org]['subdivisions']:
                tree[org]['subdivisions'][sub] = {
                    'name': sub.name,
                    'items': [],
                    'departments': {}
                }

            # Если нет отдела, добавляем сотрудника к подразделению
            if not dept:
                tree[org]['subdivisions'][sub]['items'].append(employee_data)
                continue

            # Инициализируем отдел
            if dept not in tree[org]['subdivisions'][sub]['departments']:
                tree[org]['subdivisions'][sub]['departments'][dept] = {
                    'name': dept.name,
                    'items': []
                }

            # Добавляем сотрудника к отделу
            tree[org]['subdivisions'][sub]['departments'][dept]['items'].append(employee_data)

        return tree

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        # 🔍 Получаем доступные организации пользователя
        user = self.request.user

        if user.is_superuser:
            accessible_orgs = Organization.objects.all()
        else:
            # Очищаем кеш перед получением организаций
            if hasattr(self.request, '_user_orgs_cache'):
                delattr(self.request, '_user_orgs_cache')
            accessible_orgs = AccessControlHelper.get_accessible_organizations(user, self.request)

        # 📋 Определяем выбранную организацию: GET (приоритет) → сессия
        org_id_param = self.request.GET.get('org', '') or self.request.session.get('selected_org_id', '')
        selected_org_id = None

        if org_id_param:
            try:
                org_id = int(org_id_param)
                if accessible_orgs.filter(id=org_id).exists():
                    selected_org_id = org_id
            except (ValueError, TypeError):
                pass

        # 🎯 Автоподстановка при единственной доступной организации
        if selected_org_id is None and accessible_orgs.count() == 1:
            selected_org_id = accessible_orgs.first().id
            self.request.session['selected_org_id'] = selected_org_id

        context['selected_org_id'] = selected_org_id

        # ✅ Фильтруем сотрудников: по выбранной орг или все доступные
        qs = self.get_base_queryset()
        if selected_org_id:
            qs = qs.filter(organization_id=selected_org_id)
        employees = list(qs)

        context['title'] = 'Образец заполнения журнала повторных инструктажей'
        context['tree'] = self.build_tree_structure(employees)
        context['tree_settings'] = {
            'icons': {
                'organization': '🏢',
                'subdivision': '🏭',
                'department': '📂',
                'employee': '👤'
            }
        }
        # Устанавливаем текущую дату по умолчанию
        context['default_date'] = date.today().strftime('%Y-%m-%d')

        return context

    def post(self, request, *args, **kwargs):
        """Обработка POST-запроса для генерации документов"""

        # Получаем дату повторного инструктажа
        date_povtorny = request.POST.get('date_povtorny')
        if not date_povtorny:
            messages.error(request, "Необходимо указать дату повторного инструктажа")
            return redirect(request.path)

        # Получаем вид инструктажа
        instruction_type = request.POST.get('instruction_type', 'Повторный')

        # Получаем причину проведения
        instruction_reason = request.POST.get('instruction_reason', '')

        # Получаем выбранных сотрудников
        employees_qs = self.get_base_queryset()
        selected_ids = request.POST.getlist('employee_ids')
        if selected_ids:
            employees_qs = employees_qs.filter(id__in=selected_ids)

        employees = list(employees_qs)
        if not employees:
            messages.error(request, "Нет выбранных сотрудников для журнала")
            return redirect(request.path)

        # Определяем действие: единый файл или по подразделениям
        action = request.POST.get('action')
        group_by_subdivision = action == 'download_by_subdivision'

        # Формируем дополнительный контекст
        custom_context = {
            'instruction_type': instruction_type,
            'instruction_reason': instruction_reason,
        }

        if group_by_subdivision:
            return self._enqueue_journal_job(request, employees, date_povtorny, custom_context,
                                             'instruction_journal_by_sub')
        else:
            return self._enqueue_journal_job(request, employees, date_povtorny, custom_context,
                                             'instruction_journal_unified')

    def _enqueue_journal_job(self, request, employees, date_povtorny, custom_context, job_type):
        """Ставит задачу генерации журнала в очередь и редиректит на страницу прогресса."""
        from directory.models import GenerationJob
        from directory.generation_tasks import run_instruction_journal_job
        from django.urls import reverse

        first = employees[0]
        org_name = first.organization.short_name_ru if first.organization else ''
        label = 'один файл' if job_type == 'instruction_journal_unified' else 'по подразделениям'

        job = GenerationJob.objects.create(
            user=request.user,
            job_type=job_type,
            status='pending',
            title=f'Журнал инструктажей ({label}) — {org_name} ({len(employees)} чел.)',
            params={
                'employee_ids': [e.id for e in employees],
                'date_povtorny': date_povtorny,
                'instruction_type': custom_context.get('instruction_type', 'Повторный'),
                'instruction_reason': custom_context.get('instruction_reason', ''),
            },
            progress_total=len(employees),
        )
        run_instruction_journal_job.enqueue(job.id)

        messages.success(
            request,
            f'Задача генерации журнала поставлена в очередь ({len(employees)} сотр.).'
        )
        return redirect(reverse('directory:generation_job_detail', args=[job.id]))


def send_instruction_sample(request, subdivision_id):
    """
    Отправляет образец заполнения журнала инструктажей на email получателей подразделения.

    Отправляет отдельные документы для основного подразделения (без отдела)
    и для каждого отдела, поддерживая fallback получателей на подразделение.
    """
    from django.shortcuts import get_object_or_404
    from django.core.mail import EmailMultiAlternatives
    from django.utils import timezone
    from django.utils.safestring import mark_safe
    from django.urls import reverse
    from directory.models import StructuralSubdivision
    from directory.utils.email_recipients import (
        get_recipients_detailed,
        get_recipients_for_department,
    )
    from deadline_control.models import EmailSettings, InstructionJournalSendLog, InstructionJournalSendDetail
    from directory.document_generators.instruction_journal_generator import generate_instruction_journal
    import json

    # Получаем подразделение
    subdivision = get_object_or_404(StructuralSubdivision, pk=subdivision_id)
    organization = subdivision.organization

    # Проверяем права доступа
    if not AccessControlHelper.can_access_object(request.user, subdivision):
        messages.error(request, "У вас нет прав доступа к этому подразделению")
        return redirect('directory:documents:instruction_journal')

    logger.info(f"Начало отправки образца журнала для подразделения '{subdivision.name}'")

    # Получаем всех сотрудников подразделения
    all_employees = Employee.objects.active_for_operations().filter(
        subdivision=subdivision,
        position__isnull=False
    ).select_related('organization', 'subdivision', 'department', 'position')

    subdivision_employees, departments_employees = group_employees_by_department(all_employees)
    total_groups = (1 if subdivision_employees else 0) + len(departments_employees)

    # Получаем вводные данные инструктажа из сессии
    briefing_data = request.session.get('briefing_data', {})
    briefing_date = briefing_data.get('date', date.today().strftime('%Y-%m-%d'))
    briefing_type = briefing_data.get('instruction_type', 'Повторный')
    briefing_reason = briefing_data.get('instruction_reason', '')
    custom_context = {
        'instruction_type': briefing_type,
        'instruction_reason': briefing_reason,
    }

    # Получаем настройки email
    try:
        email_settings = EmailSettings.get_settings(organization)
    except Exception as e:
        messages.error(request, f"Не удалось получить настройки email: {str(e)}")
        return redirect('directory:documents:instruction_journal')

    if not email_settings.is_active:
        messages.error(request, f"Email уведомления отключены для {organization.short_name_ru}")
        return redirect('directory:documents:instruction_journal')

    if not email_settings.email_host:
        messages.error(request, f"SMTP сервер не настроен для {organization.short_name_ru}")
        return redirect('directory:documents:instruction_journal')

    # Создаём запись лога отправки (для одного подразделения, но нескольких групп)
    send_log = InstructionJournalSendLog.objects.create(
        organization=organization,
        initiated_by=request.user,
        briefing_date=briefing_date,
        briefing_type=briefing_type,
        briefing_reason=briefing_reason,
        total_subdivisions=max(total_groups, 1),
        successful_count=0,
        failed_count=0,
        skipped_count=0,
        status='in_progress'
    )

    logger.info(f"Создан лог отправки ID={send_log.id} (групп отправки: {max(total_groups, 1)})")

    if not subdivision_employees and not departments_employees:
        InstructionJournalSendDetail.objects.create(
            send_log=send_log,
            subdivision=subdivision,
            department=None,
            status='skipped',
            skip_reason='no_employees',
            recipients='[]',
            recipients_count=0,
            employees_count=0,
            email_subject='',
            error_message='Нет сотрудников с инструкциями'
        )
        send_log.skipped_count = 1
        send_log.status = 'failed'
        send_log.save()

        messages.warning(request, f"В подразделении '{subdivision.name}' нет сотрудников с инструкциями")
        return redirect('directory:documents:instruction_journal')

    template_data = email_settings.get_email_template('instruction_journal')
    if not template_data:
        InstructionJournalSendDetail.objects.create(
            send_log=send_log,
            subdivision=subdivision,
            department=None,
            status='failed',
            skip_reason='template_not_found',
            recipients='[]',
            recipients_count=0,
            employees_count=len(subdivision_employees),
            email_subject='',
            error_message='Шаблон письма не настроен'
        )
        send_log.failed_count = 1
        send_log.status = 'failed'
        send_log.save()

        messages.error(request, "Шаблон письма не настроен для этой организации")
        return redirect('directory:documents:instruction_journal')

    total_sent = 0
    total_failed = 0
    total_skipped = 0
    sent_to_emails = []

    connection = email_settings.get_connection()
    try:
        from_email = email_settings.default_from_email or email_settings.email_host_user

        # Обработка основного подразделения (без отдела)
        if subdivision_employees:
            recipients_info = get_recipients_detailed(
                subdivision=subdivision,
                organization=organization,
                notification_type='instruction_journal'
            )
            unique_recipients = extract_unique_emails(recipients_info['recipients'])

            if not unique_recipients:
                InstructionJournalSendDetail.objects.create(
                    send_log=send_log,
                    subdivision=subdivision,
                    department=None,
                    status='skipped',
                    skip_reason='no_recipients',
                    recipients='[]',
                    recipients_count=0,
                    employees_count=len(subdivision_employees),
                    email_subject='',
                    error_message='Не настроены получатели для основного подразделения'
                )
                total_skipped += 1
            else:
                try:
                    doc = generate_instruction_journal(
                        employees=subdivision_employees,
                        date_povtorny=briefing_date,
                        user=request.user,
                        grouping_name=f"{subdivision.name} (основное подразделение)",
                        custom_context=custom_context
                    )
                except Exception as exc:
                    InstructionJournalSendDetail.objects.create(
                        send_log=send_log,
                        subdivision=subdivision,
                        department=None,
                        status='failed',
                        skip_reason='doc_generation_failed',
                        recipients=json.dumps(unique_recipients),
                        recipients_count=len(unique_recipients),
                        employees_count=len(subdivision_employees),
                        email_subject='',
                        error_message=str(exc)
                    )
                    logger.error("Ошибка генерации документа для основного подразделения: %s", exc, exc_info=True)
                    total_failed += 1
                else:
                    template_vars = {
                        'organization_name': organization.full_name_ru,
                        'subdivision_name': subdivision.name,
                        'department_name': "Основное подразделение",
                        'date': format_briefing_date_for_template(briefing_date),
                        'instruction_type': briefing_type,
                        'instruction_reason': briefing_reason,
                        'employee_count': len(subdivision_employees),
                    }

                    subject = template_data[0].format(**template_vars)
                    html_message = template_data[1].format(**template_vars)
                    text_message = strip_tags(html_message)

                    try:
                        email = EmailMultiAlternatives(
                            subject=subject,
                            body=text_message,
                            from_email=from_email,
                            to=unique_recipients,
                            connection=connection
                        )
                        email.attach_alternative(html_message, "text/html")
                        email.attach(
                            doc['filename'],
                            doc['content'],
                            'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
                        )
                        email.send(fail_silently=False)

                        InstructionJournalSendDetail.objects.create(
                            send_log=send_log,
                            subdivision=subdivision,
                            department=None,
                            status='success',
                            recipients=json.dumps(unique_recipients),
                            recipients_count=len(unique_recipients),
                            employees_count=len(subdivision_employees),
                            email_subject=subject,
                            sent_at=timezone.now()
                        )
                        total_sent += 1
                        sent_to_emails.extend(unique_recipients)
                    except Exception as exc:
                        InstructionJournalSendDetail.objects.create(
                            send_log=send_log,
                            subdivision=subdivision,
                            department=None,
                            status='failed',
                            skip_reason='email_send_failed',
                            recipients=json.dumps(unique_recipients),
                            recipients_count=len(unique_recipients),
                            employees_count=len(subdivision_employees),
                            email_subject=subject,
                            error_message=str(exc)
                        )
                        logger.error("Ошибка отправки email для основного подразделения: %s", exc, exc_info=True)
                        total_failed += 1

        # Обработка отделов
        for department, dept_employees in departments_employees.items():
            recipients_info = get_recipients_for_department(
                department=department,
                subdivision=subdivision,
                organization=organization,
                notification_type='instruction_journal'
            )
            unique_recipients = extract_unique_emails(recipients_info['recipients'])

            if not unique_recipients:
                InstructionJournalSendDetail.objects.create(
                    send_log=send_log,
                    subdivision=subdivision,
                    department=department,
                    status='skipped',
                    skip_reason='no_recipients',
                    recipients='[]',
                    recipients_count=0,
                    employees_count=len(dept_employees),
                    email_subject='',
                    error_message='Не настроены получатели для отдела'
                )
                total_skipped += 1
                continue

            try:
                doc = generate_instruction_journal(
                    employees=dept_employees,
                    date_povtorny=briefing_date,
                    user=request.user,
                    grouping_name=f"{subdivision.name} - {department.name}",
                    custom_context=custom_context
                )
            except Exception as exc:
                InstructionJournalSendDetail.objects.create(
                    send_log=send_log,
                    subdivision=subdivision,
                    department=department,
                    status='failed',
                    skip_reason='doc_generation_failed',
                    recipients=json.dumps(unique_recipients),
                    recipients_count=len(unique_recipients),
                    employees_count=len(dept_employees),
                    email_subject='',
                    error_message=str(exc)
                )
                logger.error("Ошибка генерации документа для отдела %s: %s", department.name, exc, exc_info=True)
                total_failed += 1
                continue

            template_vars = {
                'organization_name': organization.full_name_ru,
                'subdivision_name': subdivision.name,
                'department_name': department.name,
                'date': format_briefing_date_for_template(briefing_date),
                'instruction_type': briefing_type,
                'instruction_reason': briefing_reason,
                'employee_count': len(dept_employees),
            }

            subject = template_data[0].format(**template_vars)
            html_message = template_data[1].format(**template_vars)
            text_message = strip_tags(html_message)

            try:
                email = EmailMultiAlternatives(
                    subject=subject,
                    body=text_message,
                    from_email=from_email,
                    to=unique_recipients,
                    connection=connection
                )
                email.attach_alternative(html_message, "text/html")
                email.attach(
                    doc['filename'],
                    doc['content'],
                    'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
                )
                email.send(fail_silently=False)

                InstructionJournalSendDetail.objects.create(
                    send_log=send_log,
                    subdivision=subdivision,
                    department=department,
                    status='success',
                    recipients=json.dumps(unique_recipients),
                    recipients_count=len(unique_recipients),
                    employees_count=len(dept_employees),
                    email_subject=subject,
                    sent_at=timezone.now()
                )

                fallback_msg = " (fallback на подразделение)" if recipients_info.get('fallback_used') else ""
                logger.info("✅ Отдел '%s': отправлено на %s email%s", department.name, len(unique_recipients), fallback_msg)

                total_sent += 1
                sent_to_emails.extend(unique_recipients)
            except Exception as exc:
                InstructionJournalSendDetail.objects.create(
                    send_log=send_log,
                    subdivision=subdivision,
                    department=department,
                    status='failed',
                    skip_reason='email_send_failed',
                    recipients=json.dumps(unique_recipients),
                    recipients_count=len(unique_recipients),
                    employees_count=len(dept_employees),
                    email_subject=subject,
                    error_message=str(exc)
                )
                logger.error("Ошибка отправки email для отдела %s: %s", department.name, exc, exc_info=True)
                total_failed += 1
    finally:
        try:
            connection.close()
        except Exception:
            pass

    send_log.successful_count = total_sent
    send_log.failed_count = total_failed
    send_log.skipped_count = total_skipped

    if total_sent > 0 and total_failed == 0 and total_skipped == 0:
        send_log.status = 'completed'
    elif total_sent > 0:
        send_log.status = 'partial'
    else:
        send_log.status = 'failed'

    send_log.save()

    unique_emails = list(set(sent_to_emails))
    log_url = reverse('admin:deadline_control_instructionjournalsendlog_change', args=[send_log.pk])

    if total_sent > 0:
        messages.success(
            request,
            mark_safe(
                f"✅ Отправлено {total_sent} образцов журнала на {len(unique_emails)} уникальных email адресов<br>"
                f"<small>Успешно: {total_sent}, Ошибок: {total_failed}, Пропущено: {total_skipped}</small><br>"
                f"<a href='{log_url}' target='_blank' style='color:#0066cc;'>📊 Посмотреть детали отправки</a>"
            )
        )
    else:
        messages.error(
            request,
            mark_safe(
                f"❌ Не удалось отправить образцы журнала<br>"
                f"<a href='{log_url}' target='_blank'>📊 Посмотреть детали</a>"
            )
        )

    return redirect('directory:documents:instruction_journal')


def send_instruction_samples_for_organization(request, organization_id):
    """
    Отправляет образцы заполнения журнала инструктажей для ВСЕХ подразделений организации.

    Для каждого подразделения:
    - Делит сотрудников на основное подразделение и отделы
    - Генерирует отдельный документ для каждой группы
    - Собирает получателей с поддержкой fallback на подразделение
    - Отправляет email с вложением и логирует результат
    """
    from django.shortcuts import get_object_or_404
    from django.utils import timezone
    from django.utils.safestring import mark_safe
    from django.utils.html import strip_tags
    from django.urls import reverse
    from directory.models import Organization, StructuralSubdivision
    from directory.utils.email_recipients import (
        get_recipients_detailed,
        get_recipients_for_department,
    )
    from directory.utils.bulk_email_sender import BulkEmailSender
    from deadline_control.models import EmailSettings, InstructionJournalSendLog, InstructionJournalSendDetail
    from directory.document_generators.instruction_journal_generator import generate_instruction_journal
    import json

    # Получаем организацию
    organization = get_object_or_404(Organization, pk=organization_id)

    # Проверяем права доступа (проверяем через организацию)
    if not request.user.is_superuser:
        if not hasattr(request.user, 'profile'):
            messages.error(request, "У вас нет прав доступа к этой организации")
            return redirect('directory:documents:instruction_journal')

        if organization not in request.user.profile.organizations.all():
            messages.error(request, "У вас нет прав доступа к этой организации")
            return redirect('directory:documents:instruction_journal')

    logger.info(f"Начало массовой отправки образцов для организации '{organization.short_name_ru}'")

    # Получаем вводные данные инструктажа из сессии
    briefing_data = request.session.get('briefing_data', {})
    if not briefing_data or not briefing_data.get('date'):
        messages.error(
            request,
            "❌ Вводные данные инструктажа не найдены. Пожалуйста, заполните форму с датой и видом инструктажа."
        )
        return redirect('directory:documents:instruction_journal')

    logger.info(f"Используются данные инструктажа: {briefing_data}")

    # Получаем настройки email
    try:
        email_settings = EmailSettings.get_settings(organization)
    except Exception as e:
        messages.error(request, f"Не удалось получить настройки email: {str(e)}")
        return redirect('directory:documents:instruction_journal')

    if not email_settings.is_active:
        messages.error(request, f"Email уведомления отключены для {organization.short_name_ru}")
        return redirect('directory:documents:instruction_journal')

    if not email_settings.email_host:
        messages.error(request, f"SMTP сервер не настроен для {organization.short_name_ru}")
        return redirect('directory:documents:instruction_journal')

    template_data = email_settings.get_email_template('instruction_journal')
    if not template_data:
        messages.error(request, "Шаблон письма не настроен для этой организации")
        return redirect('directory:documents:instruction_journal')

    # Получаем все подразделения организации
    subdivisions = StructuralSubdivision.objects.filter(organization=organization)

    if not subdivisions.exists():
        messages.warning(request, f"У организации '{organization.short_name_ru}' нет подразделений")
        return redirect('directory:documents:instruction_journal')

    # Создаём запись лога рассылки
    send_log = InstructionJournalSendLog.objects.create(
        organization=organization,
        initiated_by=request.user,
        briefing_date=briefing_data['date'],
        briefing_type=briefing_data.get('instruction_type', 'Повторный'),
        briefing_reason=briefing_data.get('instruction_reason', ''),
        total_subdivisions=0,
        successful_count=0,
        failed_count=0,
        skipped_count=0,
        status='in_progress'
    )

    logger.info(f"Создан лог рассылки ID={send_log.id}")

    # Статистика отправки
    total_groups = 0
    successful_sent = 0
    failed_sent = 0
    skipped_count = 0
    total_recipients = set()  # Уникальные получатели
    total_employees = 0

    # Инициализируем BulkEmailSender с настройками из EmailSettings
    try:
        bulk_sender = BulkEmailSender(
            email_settings=email_settings,
            delay_seconds=float(email_settings.email_delay_seconds),
            max_retries=email_settings.max_retry_attempts,
            connection_timeout=email_settings.connection_timeout
        )
    except Exception as e:
        logger.error(f"Ошибка инициализации BulkEmailSender: {str(e)}", exc_info=True)
        send_log.status = 'failed'
        send_log.save()
        messages.error(request, f"Ошибка подключения к SMTP серверу: {str(e)}")
        return redirect('directory:documents:instruction_journal')

    # Используем context manager для автоматического управления SMTP соединением
    with bulk_sender:
        # Обрабатываем каждое подразделение
        for subdivision in subdivisions:
            logger.info(f"Обработка подразделения: {subdivision.name}")

            employees = Employee.objects.active_for_operations().filter(
                subdivision=subdivision,
                position__isnull=False
            ).select_related('organization', 'subdivision', 'department', 'position')

            subdivision_employees, departments_employees = group_employees_by_department(employees)

            if not subdivision_employees and not departments_employees:
                InstructionJournalSendDetail.objects.create(
                    send_log=send_log,
                    subdivision=subdivision,
                    department=None,
                    status='skipped',
                    skip_reason='no_employees',
                    recipients='[]',
                    recipients_count=0,
                    employees_count=0,
                    email_subject='',
                    error_message='Нет сотрудников с инструкциями'
                )
                skipped_count += 1
                total_groups += 1
                logger.info("Подразделение '%s': нет сотрудников с инструкциями, пропускаем", subdivision.name)
                continue

            custom_context = {
                'instruction_type': briefing_data.get('instruction_type', 'Повторный'),
                'instruction_reason': briefing_data.get('instruction_reason', ''),
            }

            # Обрабатываем основное подразделение
            if subdivision_employees:
                total_groups += 1
                recipients_info = get_recipients_detailed(
                    subdivision=subdivision,
                    organization=organization,
                    notification_type='instruction_journal'
                )
                unique_recipients = extract_unique_emails(recipients_info['recipients'])

                if not unique_recipients:
                    InstructionJournalSendDetail.objects.create(
                        send_log=send_log,
                        subdivision=subdivision,
                        department=None,
                        status='skipped',
                        skip_reason='no_recipients',
                        recipients='[]',
                        recipients_count=0,
                        employees_count=len(subdivision_employees),
                        email_subject='',
                        error_message='Не настроены получатели для основного подразделения'
                    )
                    skipped_count += 1
                else:
                    try:
                        doc = generate_instruction_journal(
                            employees=subdivision_employees,
                            date_povtorny=briefing_data['date'],
                            user=request.user,
                            grouping_name=f"{subdivision.name} (основное подразделение)",
                            custom_context=custom_context
                        )
                    except Exception as exc:
                        InstructionJournalSendDetail.objects.create(
                            send_log=send_log,
                            subdivision=subdivision,
                            department=None,
                            status='failed',
                            skip_reason='doc_generation_failed',
                            recipients=json.dumps(unique_recipients),
                            recipients_count=len(unique_recipients),
                            employees_count=len(subdivision_employees),
                            email_subject='',
                            error_message=str(exc)
                        )
                        failed_sent += 1
                        logger.error("Ошибка генерации документа для %s: %s", subdivision.name, exc, exc_info=True)
                    else:
                        template_vars = {
                            'organization_name': organization.full_name_ru,
                            'subdivision_name': subdivision.name,
                            'department_name': "Основное подразделение",
                            'date': format_briefing_date_for_template(briefing_data.get('date')),
                            'instruction_type': briefing_data.get('instruction_type', 'Повторный'),
                            'instruction_reason': briefing_data.get('instruction_reason', ''),
                            'employee_count': len(subdivision_employees),
                        }

                        subject = template_data[0].format(**template_vars)
                        html_message = template_data[1].format(**template_vars)
                        text_message = strip_tags(html_message)

                        success, error = bulk_sender.send_email(
                            subject=subject,
                            body_text=text_message,
                            to_emails=unique_recipients,
                            body_html=html_message,
                            attachment_name=doc['filename'],
                            attachment_content=doc['content'],
                            attachment_mimetype='application/vnd.openxmlformats-officedocument.wordprocessingml.document'
                        )

                        if success:
                            InstructionJournalSendDetail.objects.create(
                                send_log=send_log,
                                subdivision=subdivision,
                                department=None,
                                status='success',
                                recipients=json.dumps(unique_recipients),
                                recipients_count=len(unique_recipients),
                                employees_count=len(subdivision_employees),
                                email_subject=subject,
                                sent_at=timezone.now()
                            )
                            successful_sent += 1
                            total_employees += len(subdivision_employees)
                            total_recipients.update(unique_recipients)
                        else:
                            InstructionJournalSendDetail.objects.create(
                                send_log=send_log,
                                subdivision=subdivision,
                                department=None,
                                status='failed',
                                skip_reason='email_send_failed',
                                recipients=json.dumps(unique_recipients),
                                recipients_count=len(unique_recipients),
                                employees_count=len(subdivision_employees),
                                email_subject=subject,
                                error_message=error or 'Неизвестная ошибка отправки'
                            )
                            failed_sent += 1
                            logger.error("❌ Ошибка отправки email для %s: %s", subdivision.name, error)

            # Обрабатываем отделы
            for department, dept_employees in departments_employees.items():
                total_groups += 1
                recipients_info = get_recipients_for_department(
                    department=department,
                    subdivision=subdivision,
                    organization=organization,
                    notification_type='instruction_journal'
                )
                unique_recipients = extract_unique_emails(recipients_info['recipients'])

                if not unique_recipients:
                    InstructionJournalSendDetail.objects.create(
                        send_log=send_log,
                        subdivision=subdivision,
                        department=department,
                        status='skipped',
                        skip_reason='no_recipients',
                        recipients='[]',
                        recipients_count=0,
                        employees_count=len(dept_employees),
                        email_subject='',
                        error_message='Не настроены получатели для отдела'
                    )
                    skipped_count += 1
                    continue

                try:
                    doc = generate_instruction_journal(
                        employees=dept_employees,
                        date_povtorny=briefing_data['date'],
                        user=request.user,
                        grouping_name=f"{subdivision.name} - {department.name}",
                        custom_context=custom_context
                    )
                except Exception as exc:
                    InstructionJournalSendDetail.objects.create(
                        send_log=send_log,
                        subdivision=subdivision,
                        department=department,
                        status='failed',
                        skip_reason='doc_generation_failed',
                        recipients=json.dumps(unique_recipients),
                        recipients_count=len(unique_recipients),
                        employees_count=len(dept_employees),
                        email_subject='',
                        error_message=str(exc)
                    )
                    failed_sent += 1
                    logger.error("Ошибка генерации документа для отдела %s: %s", department.name, exc, exc_info=True)
                    continue

                template_vars = {
                    'organization_name': organization.full_name_ru,
                    'subdivision_name': subdivision.name,
                    'department_name': department.name,
                    'date': format_briefing_date_for_template(briefing_data.get('date')),
                    'instruction_type': briefing_data.get('instruction_type', 'Повторный'),
                    'instruction_reason': briefing_data.get('instruction_reason', ''),
                    'employee_count': len(dept_employees),
                }

                subject = template_data[0].format(**template_vars)
                html_message = template_data[1].format(**template_vars)
                text_message = strip_tags(html_message)

                success, error = bulk_sender.send_email(
                    subject=subject,
                    body_text=text_message,
                    to_emails=unique_recipients,
                    body_html=html_message,
                    attachment_name=doc['filename'],
                    attachment_content=doc['content'],
                    attachment_mimetype='application/vnd.openxmlformats-officedocument.wordprocessingml.document'
                )

                if success:
                    InstructionJournalSendDetail.objects.create(
                        send_log=send_log,
                        subdivision=subdivision,
                        department=department,
                        status='success',
                        recipients=json.dumps(unique_recipients),
                        recipients_count=len(unique_recipients),
                        employees_count=len(dept_employees),
                        email_subject=subject,
                        sent_at=timezone.now()
                    )

                    successful_sent += 1
                    total_employees += len(dept_employees)
                    total_recipients.update(unique_recipients)

                    fallback_msg = " (fallback на подразделение)" if recipients_info.get('fallback_used') else ""
                    logger.info("✅ Отдел '%s': отправлено на %s email%s", department.name, len(unique_recipients), fallback_msg)
                else:
                    InstructionJournalSendDetail.objects.create(
                        send_log=send_log,
                        subdivision=subdivision,
                        department=department,
                        status='failed',
                        skip_reason='email_send_failed',
                        recipients=json.dumps(unique_recipients),
                        recipients_count=len(unique_recipients),
                        employees_count=len(dept_employees),
                        email_subject=subject,
                        error_message=error or 'Неизвестная ошибка отправки'
                    )
                    failed_sent += 1
                    logger.error("❌ Ошибка отправки email для отдела %s: %s", department.name, error)

    # Обновляем итоговую статистику лога
    send_log.successful_count = successful_sent
    send_log.failed_count = failed_sent
    send_log.skipped_count = skipped_count
    send_log.total_subdivisions = max(total_groups, subdivisions.count())

    # Определяем финальный статус
    if successful_sent > 0 and failed_sent == 0 and skipped_count == 0:
        send_log.status = 'completed'  # Всё отправлено успешно
    elif successful_sent > 0:
        send_log.status = 'partial'  # Частично (есть ошибки или пропуски)
    else:
        send_log.status = 'failed'  # Ничего не отправлено

    send_log.save()

    logger.info(
        f"Массовая отправка завершена. ID лога: {send_log.id}. "
        f"Успешно: {successful_sent}, Ошибок: {failed_sent}, Пропущено: {skipped_count}"
    )

    # Итоговое сообщение с ссылкой на лог
    if successful_sent > 0:
        log_url = reverse('admin:deadline_control_instructionjournalsendlog_change', args=[send_log.pk])
        messages.success(
            request,
            mark_safe(
                f"✅ Массовая отправка завершена!<br>"
                f"Отправлено: <strong>{successful_sent}</strong><br>"
                f"Ошибок: <strong>{failed_sent}</strong><br>"
                f"Пропущено: <strong>{skipped_count}</strong><br>"
                f"Уникальных получателей: <strong>{len(total_recipients)}</strong><br>"
                f"Всего сотрудников: <strong>{total_employees}</strong><br><br>"
                f"<a href='{log_url}' target='_blank' style='color:#fff;background:#2196f3;padding:8px 16px;border-radius:4px;text-decoration:none;'>📊 Посмотреть детальный отчёт</a>"
            )
        )

    if failed_sent > 0 or skipped_count > 0:
        log_url = reverse('admin:deadline_control_instructionjournalsendlog_change', args=[send_log.pk])
        messages.warning(
            request,
            mark_safe(
                f"⚠️ Внимание: есть подразделения, для которых не удалось отправить письмо.<br>"
                f"<a href='{log_url}' target='_blank'>📊 Проверьте детали в отчёте</a>"
            )
        )

    if successful_sent == 0 and failed_sent == 0 and skipped_count == 0:
        messages.info(
            request,
            f"ℹ️ Нет подразделений с сотрудниками для отправки в организации '{organization.short_name_ru}'"
        )

    return redirect('directory:documents:instruction_journal')


@login_required
def preview_mass_send_instruction_samples(request, organization_id):
    """
    📋 Предварительный просмотр массовой отправки образцов журнала инструктажей.

    Показывает дерево: Организация → Подразделение → Отдел
    с информацией о получателях перед массовой отправкой.
    """
    from directory.models import Organization, StructuralSubdivision, Employee
    from directory.utils.email_recipients import (
        get_recipients_detailed,
        get_recipients_for_department,
    )
    from deadline_control.models import EmailSettings

    try:
        organization = Organization.objects.get(id=organization_id)
    except Organization.DoesNotExist:
        messages.error(request, "❌ Организация не найдена")
        return redirect('directory:documents:instruction_journal')

    # Проверка прав доступа
    if not request.user.is_superuser and hasattr(request.user, 'profile'):
        allowed_orgs = request.user.profile.organizations.all()
        if organization not in allowed_orgs:
            messages.error(request, "❌ У вас нет доступа к этой организации")
            return redirect('directory:documents:instruction_journal')

    # Получаем настройки email
    try:
        email_settings = EmailSettings.objects.get(organization=organization)
        if not email_settings.is_active:
            messages.warning(request, "⚠️ Отправка email отключена для этой организации")
            return redirect('directory:documents:instruction_journal')
    except EmailSettings.DoesNotExist:
        messages.error(request, "❌ Настройки email не найдены для организации")
        return redirect('directory:documents:instruction_journal')

    # Получаем и сохраняем вводные данные инструктажа
    if request.method == 'POST':
        # Проверяем, это запрос на отправку или на показ preview
        if 'send_emails' in request.POST:
            # Это запрос на реальную отправку (с кнопки "Отправить всем" на странице preview)
            return send_instruction_samples_for_organization(request, organization_id)
        else:
            # Это запрос на показ preview - сохраняем данные из формы в сессию
            briefing_data = {
                'date': request.POST.get('date_povtorny', ''),
                'instruction_type': request.POST.get('instruction_type', 'Повторный'),
                'instruction_reason': request.POST.get('instruction_reason', ''),
            }
            request.session['briefing_data'] = briefing_data
            logger.info(f"Сохранены данные инструктажа в сессию: {briefing_data}")
    else:
        # GET запрос - получаем вводные данные инструктажа из сессии
        briefing_data = request.session.get('briefing_data', {})

    # Собираем данные для предварительного просмотра
    subdivisions = StructuralSubdivision.objects.filter(
        organization=organization
    ).order_by('name')

    tree_data = []
    unique_recipients = set()
    total_recipients_shown = 0
    total_employees = 0
    has_any_recipients = False

    template_data = email_settings.get_email_template('instruction_journal')
    if not template_data:
        messages.error(request, "Шаблон письма не настроен для этой организации")
        return redirect('directory:documents:instruction_journal')

    for subdivision in subdivisions:
        # Получаем сотрудников с инструкциями
        employees = Employee.objects.active_for_operations().filter(
            organization=organization,
            subdivision=subdivision,
            position__isnull=False
        ).select_related('position', 'department')

        subdivision_employees, departments_employees = group_employees_by_department(employees)
        employees_total = len(subdivision_employees) + sum(len(emp_list) for emp_list in departments_employees.values())

        if employees_total == 0:
            continue

        total_employees += employees_total

        # Получатели основного подразделения (без отдела)
        subdivision_recipients_data = get_recipients_detailed(
            subdivision=subdivision,
            organization=organization,
            notification_type='instruction_journal'
        )
        subdivision_unique_emails = extract_unique_emails(subdivision_recipients_data['recipients'])
        unique_recipients.update(subdivision_unique_emails)
        total_recipients_shown += subdivision_recipients_data['total_count']
        subdivision_has_recipients = subdivision_recipients_data['has_recipients']
        has_any_recipients = has_any_recipients or subdivision_has_recipients

        subdivision_subject_vars = {
            'organization_name': organization.full_name_ru,
            'subdivision_name': subdivision.name,
            'department_name': "Основное подразделение (без отдела)",
            'employee_count': len(subdivision_employees),
            'date': format_briefing_date_for_template(briefing_data.get('date')),
            'instruction_type': briefing_data.get('instruction_type', 'Повторный'),
            'instruction_reason': briefing_data.get('instruction_reason', ''),
        }
        subdivision_subject = template_data[0].format(**subdivision_subject_vars)

        # Получатели по отделам
        departments_data = []
        for department, dept_employees in departments_employees.items():
            dept_recipients_data = get_recipients_for_department(
                department=department,
                subdivision=subdivision,
                organization=organization,
                notification_type='instruction_journal'
            )
            dept_unique_emails = extract_unique_emails(dept_recipients_data['recipients'])
            unique_recipients.update(dept_unique_emails)
            total_recipients_shown += dept_recipients_data['total_count']
            has_any_recipients = has_any_recipients or dept_recipients_data['has_recipients']

            dept_subject_vars = {
                'organization_name': organization.full_name_ru,
                'subdivision_name': subdivision.name,
                'department_name': department.name,
                'employee_count': len(dept_employees),
                'date': format_briefing_date_for_template(briefing_data.get('date')),
                'instruction_type': briefing_data.get('instruction_type', 'Повторный'),
                'instruction_reason': briefing_data.get('instruction_reason', ''),
            }
            dept_subject = template_data[0].format(**dept_subject_vars)

            departments_data.append({
                'department': department,
                'department_name': department.name,
                'employees_count': len(dept_employees),
                'recipients': dept_recipients_data['recipients'],
                'recipients_count': dept_recipients_data['total_count'],
                'unique_recipients_count': dept_recipients_data['unique_emails_count'],
                'has_recipients': dept_recipients_data['has_recipients'],
                'fallback_used': dept_recipients_data.get('fallback_used', False),
                'email_subject': dept_subject,
            })

        subdivision_any_recipients = subdivision_has_recipients or any(
            dept['has_recipients'] for dept in departments_data
        )

        tree_data.append({
            'subdivision': subdivision,
            'subdivision_employees_count': len(subdivision_employees),
            'subdivision_recipients': subdivision_recipients_data['recipients'],
            'subdivision_recipients_count': subdivision_recipients_data['total_count'],
            'subdivision_unique_recipients_count': subdivision_recipients_data['unique_emails_count'],
            'subdivision_has_recipients': subdivision_has_recipients,
            'subdivision_email_subject': subdivision_subject,
            'departments': departments_data,
            'total_employees_count': employees_total,
            'has_recipients': subdivision_any_recipients,
        })

    # Форматируем текст письма с примером (берём первое подразделение)
    if tree_data and template_data:
        example_vars = {
            'organization_name': organization.full_name_ru,
            'subdivision_name': tree_data[0]['subdivision'].name,
            'department_name': "Основное подразделение (без отдела)",
            'employee_count': tree_data[0].get('total_employees_count', 0),
            'date': format_briefing_date_for_template(briefing_data.get('date')),
            'instruction_type': briefing_data.get('instruction_type', 'Повторный'),
            'instruction_reason': briefing_data.get('instruction_reason', ''),
        }
        email_body_preview = template_data[1].format(**example_vars)
    elif template_data:
        email_body_preview = template_data[1]
    else:
        email_body_preview = "Шаблон письма не настроен"

    context = {
        'organization': organization,
        'tree_data': tree_data,
        'total_recipients_count': len(unique_recipients),
        'total_recipients_shown': total_recipients_shown,
        'total_employees': total_employees,
        'briefing_data': briefing_data,
        'email_body_preview': email_body_preview,
        'has_any_recipients': has_any_recipients,
    }

    return render(request, 'directory/documents/instruction_journal_preview.html', context)
