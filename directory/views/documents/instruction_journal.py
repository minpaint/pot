# directory/views/documents/instruction_journal.py

from django import forms
from django.views.generic import TemplateView
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from django.contrib import messages
from django.http import HttpResponse
from django.db.models import Q
import logging
from io import BytesIO
from zipfile import ZipFile
from datetime import date

from directory.models import Employee
from directory.utils.permissions import AccessControlHelper

# Настройка логирования
logger = logging.getLogger(__name__)


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
        qs = Employee.objects.select_related(
            'organization', 'subdivision', 'department', 'position'
        )
        # Фильтруем по правам доступа
        qs = AccessControlHelper.filter_queryset(qs, self.request.user, self.request)
        # Только сотрудники с должностью
        qs = qs.filter(
            position__isnull=False,
            status='active'  # Только активные сотрудники
        )
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
        employees = list(self.get_base_queryset())

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
            # Генерация отдельных файлов по подразделениям
            return self._generate_by_subdivision(employees, date_povtorny, request, custom_context)
        else:
            # Генерация единого файла
            return self._generate_unified(employees, date_povtorny, request, custom_context)

    def _generate_unified(self, employees, date_povtorny, request, custom_context=None):
        """Генерация единого образца журнала для всех сотрудников"""
        from directory.document_generators.instruction_journal_generator import generate_instruction_journal

        try:
            doc = generate_instruction_journal(
                employees,
                date_povtorny=date_povtorny,
                user=request.user,
                custom_context=custom_context
            )

            if not doc:
                messages.error(request, "Ошибка при генерации образца журнала")
                return redirect(request.path)
        except ValueError as e:
            messages.error(request, str(e))
            return redirect(request.path)
        except Exception as e:
            logger.error(f"Ошибка при генерации образца журнала: {str(e)}", exc_info=True)
            messages.error(request, f"Ошибка при генерации образца журнала: {str(e)}")
            return redirect(request.path)

        response = HttpResponse(
            doc['content'],
            content_type='application/vnd.openxmlformats-officedocument.wordprocessingml.document'
        )
        from urllib.parse import quote
        filename_encoded = quote(doc['filename'])
        response['Content-Disposition'] = f'attachment; filename="{doc["filename"]}"; filename*=UTF-8\'\'{filename_encoded}'

        messages.success(request, 'Образец журнала инструктажей успешно сгенерирован')
        return response

    def _generate_by_subdivision(self, employees, date_povtorny, request, custom_context=None):
        """Генерация отдельных файлов по подразделениям в ZIP архиве"""
        from directory.document_generators.instruction_journal_generator import generate_instruction_journal

        buffer = BytesIO()
        files_generated = 0

        try:
            with ZipFile(buffer, 'w') as zip_buffer:
                # Группируем сотрудников по иерархии: подразделение → организация
                grouped = {}
                for emp in employees:
                    # Используем иерархическую логику: подразделение → организация
                    if emp.subdivision:
                        key = emp.subdivision.name
                    elif emp.organization:
                        key = emp.organization.short_name_ru
                    else:
                        key = 'Без подразделения'
                    grouped.setdefault(key, []).append(emp)

                logger.info(f"Сгруппировано по подразделениям/организациям: {list(grouped.keys())}")

                # Генерируем документ для каждого подразделения
                for subdivision_name, emps in grouped.items():
                    logger.info(f"Генерация для подразделения '{subdivision_name}': {len(emps)} сотрудников")

                    try:
                        doc = generate_instruction_journal(
                            emps,
                            date_povtorny=date_povtorny,
                            grouping_name=subdivision_name,
                            user=request.user,
                            custom_context=custom_context
                        )
                        if not doc:
                            logger.warning(f"Документ для подразделения '{subdivision_name}' не сгенерирован")
                            continue

                        # Формируем имя файла для подразделения
                        # Очищаем название от недопустимых символов
                        safe_name = subdivision_name.replace('"', '').replace('/', '_').replace('\\', '_').replace(':', '_').replace('*', '_').replace('?', '_').replace('<', '_').replace('>', '_').replace('|', '_')
                        filename = f"Образец_журнала_{safe_name}.docx"
                        zip_buffer.writestr(filename, doc['content'])
                        files_generated += 1
                        logger.info(f"Добавлен файл в архив: {filename}")
                    except Exception as e:
                        logger.error(f"Ошибка генерации для '{subdivision_name}': {str(e)}", exc_info=True)
                        messages.warning(request, f"Не удалось сгенерировать для подразделения '{subdivision_name}': {str(e)}")
                        continue
        except Exception as e:
            logger.error(f"Ошибка при создании ZIP архива: {str(e)}", exc_info=True)
            messages.error(request, f"Ошибка при создании архива: {str(e)}")
            return redirect(request.path)

        if files_generated == 0:
            messages.error(request, "Не удалось сгенерировать ни одного документа")
            return redirect(request.path)

        buffer.seek(0)

        response = HttpResponse(buffer.getvalue(), content_type='application/zip')
        response['Content-Disposition'] = 'attachment; filename="Образцы_журнала_по_подразделениям.zip"'

        messages.success(request, f'Сгенерировано файлов: {files_generated}')
        return response


def send_instruction_sample(request, subdivision_id):
    """
    Отправляет образец заполнения журнала инструктажей на email получателей подразделения.

    Использует трёхуровневую систему сбора получателей:
    1. SubdivisionEmail - email адреса, настроенные для подразделения
    2. Employee.email - email ответственных за охрану труда
    3. EmailSettings - общие email адреса организации
    """
    from django.shortcuts import get_object_or_404
    from django.core.mail import EmailMultiAlternatives
    from django.utils import timezone
    from django.utils.safestring import mark_safe
    from django.urls import reverse
    from directory.models import StructuralSubdivision
    from directory.utils.email_recipients import collect_recipients_for_subdivision
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

    # Получаем сотрудников подразделения с инструкциями
    employees = Employee.objects.filter(
        subdivision=subdivision,
        status='active',
        position__isnull=False
    ).select_related('organization', 'subdivision', 'department', 'position')

    # Фильтруем только сотрудников с инструкциями
    employees_with_instructions = []
    for emp in employees:
        position = emp.position
        has_instructions = bool(
            (position.safety_instructions_numbers and position.safety_instructions_numbers.strip()) or
            (position.contract_safety_instructions and position.contract_safety_instructions.strip()) or
            (position.company_vehicle_instructions and position.company_vehicle_instructions.strip())
        )
        if has_instructions:
            employees_with_instructions.append(emp)

    # Получаем вводные данные инструктажа из сессии
    briefing_data = request.session.get('briefing_data', {})
    briefing_date = briefing_data.get('date', date.today().strftime('%Y-%m-%d'))
    briefing_type = briefing_data.get('instruction_type', 'Повторный')
    briefing_reason = briefing_data.get('instruction_reason', '')

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

    # Создаём запись лога отправки (для одного подразделения)
    send_log = InstructionJournalSendLog.objects.create(
        organization=organization,
        initiated_by=request.user,
        briefing_date=briefing_date,
        briefing_type=briefing_type,
        briefing_reason=briefing_reason,
        total_subdivisions=1,  # Одно подразделение
        successful_count=0,
        failed_count=0,
        skipped_count=0,
        status='in_progress'
    )

    logger.info(f"Создан лог отправки ID={send_log.id} для одиночной отправки")

    if not employees_with_instructions:
        # Создаём запись о пропуске
        InstructionJournalSendDetail.objects.create(
            send_log=send_log,
            subdivision=subdivision,
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

    logger.info(f"Найдено {len(employees_with_instructions)} сотрудников с инструкциями")

    # Собираем получателей используя трёхуровневую систему
    # Для журналов инструктажей используем специализированное поле
    recipients = collect_recipients_for_subdivision(
        subdivision=subdivision,
        organization=organization,
        notification_type='instruction_journal'
    )

    if not recipients:
        # Создаём запись о пропуске
        InstructionJournalSendDetail.objects.create(
            send_log=send_log,
            subdivision=subdivision,
            status='skipped',
            skip_reason='no_recipients',
            recipients='[]',
            recipients_count=0,
            employees_count=len(employees_with_instructions),
            email_subject='',
            error_message='Не настроены получатели для подразделения'
        )
        send_log.skipped_count = 1
        send_log.status = 'failed'
        send_log.save()

        messages.error(
            request,
            f"Нет получателей для подразделения '{subdivision.name}'. "
            f"Настройте email в разделе 'Email для уведомлений' или добавьте email ответственным сотрудникам."
        )
        return redirect('directory:documents:instruction_journal')

    logger.info(f"Собрано {len(recipients)} получателей: {', '.join(recipients)}")

    # Генерируем документ
    try:
        doc = generate_instruction_journal(
            employees=employees_with_instructions,
            date_povtorny=briefing_date,
            user=request.user,
            grouping_name=subdivision.name
        )

        if not doc:
            # Создаём запись об ошибке
            InstructionJournalSendDetail.objects.create(
                send_log=send_log,
                subdivision=subdivision,
                status='failed',
                skip_reason='doc_generation_failed',
                recipients=json.dumps(recipients),
                recipients_count=len(recipients),
                employees_count=len(employees_with_instructions),
                email_subject='',
                error_message='Не удалось сгенерировать документ'
            )
            send_log.failed_count = 1
            send_log.status = 'failed'
            send_log.save()

            messages.error(request, "Ошибка при генерации документа")
            return redirect('directory:documents:instruction_journal')

        logger.info(f"Документ успешно сгенерирован: {doc['filename']}")
    except Exception as e:
        # Создаём запись об ошибке
        InstructionJournalSendDetail.objects.create(
            send_log=send_log,
            subdivision=subdivision,
            status='failed',
            skip_reason='doc_generation_failed',
            recipients=json.dumps(recipients),
            recipients_count=len(recipients),
            employees_count=len(employees_with_instructions),
            email_subject='',
            error_message=str(e)
        )
        send_log.failed_count = 1
        send_log.status = 'failed'
        send_log.save()

        logger.error(f"Ошибка генерации документа для {subdivision.name}: {str(e)}", exc_info=True)
        messages.error(request, f"Ошибка генерации документа: {str(e)}")
        return redirect('directory:documents:instruction_journal')

    # Отправляем email
    try:
        connection = email_settings.get_connection()
        from_email = email_settings.default_from_email or email_settings.email_host_user

        # Собираем уникальные отделы сотрудников
        departments = set()
        for emp in employees_with_instructions:
            if emp.department:
                departments.add(emp.department.name)

        # Формируем название отдела для шаблона
        if len(departments) == 0:
            department_name = "Без отдела"
        elif len(departments) == 1:
            department_name = list(departments)[0]
        else:
            department_name = "Все отделы"

        # Подготовка переменных для шаблона
        template_vars = {
            'organization_name': organization.full_name_ru,
            'subdivision_name': subdivision.name,
            'department_name': department_name,
            'date': briefing_data.get('date', date.today().strftime('%d.%m.%Y')),
            'instruction_type': briefing_type,
            'instruction_reason': briefing_reason,
            'employee_count': len(employees_with_instructions),
        }

        # Получаем шаблон письма из новой системы шаблонов
        template_data = email_settings.get_email_template('instruction_journal')
        if not template_data:
            # Создаём запись об ошибке
            InstructionJournalSendDetail.objects.create(
                send_log=send_log,
                subdivision=subdivision,
                status='failed',
                skip_reason='template_not_found',
                recipients=json.dumps(recipients),
                recipients_count=len(recipients),
                employees_count=len(employees_with_instructions),
                email_subject='',
                error_message='Шаблон письма не настроен'
            )
            send_log.failed_count = 1
            send_log.status = 'failed'
            send_log.save()

            messages.error(request, "Шаблон письма не настроен для этой организации")
            return redirect('directory:documents:instruction_journal')

        # Форматируем тему и текст письма с использованием переменных
        subject = template_data[0].format(**template_vars)
        html_message = template_data[1].format(**template_vars)

        # Создаем текстовую версию (для клиентов без HTML)
        from django.utils.html import strip_tags
        text_message = strip_tags(html_message)

        email = EmailMultiAlternatives(
            subject=subject,
            body=text_message,
            from_email=from_email,
            to=recipients,
            connection=connection
        )

        # Прикрепляем HTML версию
        email.attach_alternative(html_message, "text/html")

        # Прикрепляем документ
        email.attach(
            doc['filename'],
            doc['content'],
            'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
        )

        email.send(fail_silently=False)

        # Создаём запись об успехе
        InstructionJournalSendDetail.objects.create(
            send_log=send_log,
            subdivision=subdivision,
            status='success',
            recipients=json.dumps(recipients),
            recipients_count=len(recipients),
            employees_count=len(employees_with_instructions),
            email_subject=subject,
            sent_at=timezone.now()
        )

        send_log.successful_count = 1
        send_log.status = 'completed'
        send_log.save()

        logger.info(
            f"Образец журнала отправлен для {subdivision.name}. "
            f"Получатели: {', '.join(recipients)}. "
            f"Сотрудников: {len(employees_with_instructions)}"
        )

        # Итоговое сообщение с ссылкой на лог
        log_url = reverse('admin:deadline_control_instructionjournalsendlog_change', args=[send_log.pk])
        messages.success(
            request,
            mark_safe(
                f"✅ Образец журнала успешно отправлен на {len(recipients)} адрес(ов): {', '.join(recipients)}<br>"
                f"<a href='{log_url}' target='_blank' style='color:#0066cc;'>📊 Посмотреть детали отправки</a>"
            )
        )

    except Exception as e:
        # Создаём запись об ошибке отправки email
        InstructionJournalSendDetail.objects.create(
            send_log=send_log,
            subdivision=subdivision,
            status='failed',
            skip_reason='email_send_failed',
            recipients=json.dumps(recipients),
            recipients_count=len(recipients),
            employees_count=len(employees_with_instructions),
            email_subject=subject if 'subject' in locals() else '',
            error_message=str(e)
        )
        send_log.failed_count = 1
        send_log.status = 'failed'
        send_log.save()

        logger.error(f"Ошибка отправки email для {subdivision.name}: {str(e)}", exc_info=True)

        log_url = reverse('admin:deadline_control_instructionjournalsendlog_change', args=[send_log.pk])
        messages.error(
            request,
            mark_safe(
                f"❌ Ошибка отправки email: {str(e)}<br>"
                f"<a href='{log_url}' target='_blank'>📊 Посмотреть детали ошибки</a>"
            )
        )

    return redirect('directory:documents:instruction_journal')


def send_instruction_samples_for_organization(request, organization_id):
    """
    Отправляет образцы заполнения журнала инструктажей для ВСЕХ подразделений организации.

    Для каждого подразделения:
    - Собирает сотрудников с инструкциями
    - Генерирует документ
    - Собирает получателей через трёхуровневую систему
    - Отправляет email с вложением
    """
    from django.shortcuts import get_object_or_404
    from django.core.mail import EmailMultiAlternatives
    from django.utils import timezone
    from django.utils.safestring import mark_safe
    from django.urls import reverse
    from directory.models import Organization, StructuralSubdivision
    from directory.utils.email_recipients import collect_recipients_for_subdivision
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
        total_subdivisions=subdivisions.count(),
        successful_count=0,
        failed_count=0,
        skipped_count=0,
        status='in_progress'
    )

    logger.info(f"Создан лог рассылки ID={send_log.id}")

    # Статистика отправки
    total_subdivisions = 0
    successful_sent = 0
    failed_sent = 0
    skipped_count = 0
    total_recipients = set()  # Уникальные получатели
    total_employees = 0

    # Обрабатываем каждое подразделение
    for subdivision in subdivisions:
        logger.info(f"Обработка подразделения: {subdivision.name}")

        # Получаем сотрудников подразделения с инструкциями
        employees = Employee.objects.filter(
            subdivision=subdivision,
            status='active',
            position__isnull=False
        ).select_related('organization', 'subdivision', 'department', 'position')

        # Фильтруем только сотрудников с инструкциями
        employees_with_instructions = []
        for emp in employees:
            position = emp.position
            has_instructions = bool(
                (position.safety_instructions_numbers and position.safety_instructions_numbers.strip()) or
                (position.contract_safety_instructions and position.contract_safety_instructions.strip()) or
                (position.company_vehicle_instructions and position.company_vehicle_instructions.strip())
            )
            if has_instructions:
                employees_with_instructions.append(emp)

        if not employees_with_instructions:
            # Создаём запись о пропуске
            InstructionJournalSendDetail.objects.create(
                send_log=send_log,
                subdivision=subdivision,
                status='skipped',
                skip_reason='no_employees',
                recipients='[]',
                recipients_count=0,
                employees_count=0,
                email_subject='',
                error_message='Нет сотрудников с инструкциями'
            )
            skipped_count += 1
            logger.info(f"Подразделение '{subdivision.name}': нет сотрудников с инструкциями, пропускаем")
            continue

        total_subdivisions += 1
        logger.info(f"Найдено {len(employees_with_instructions)} сотрудников с инструкциями")

        # Собираем получателей для журналов инструктажей
        recipients = collect_recipients_for_subdivision(
            subdivision=subdivision,
            organization=organization,
            notification_type='instruction_journal'
        )

        if not recipients:
            # Создаём запись о пропуске
            InstructionJournalSendDetail.objects.create(
                send_log=send_log,
                subdivision=subdivision,
                status='skipped',
                skip_reason='no_recipients',
                recipients='[]',
                recipients_count=0,
                employees_count=len(employees_with_instructions),
                email_subject='',
                error_message='Не настроены получатели для подразделения'
            )
            skipped_count += 1
            logger.warning(f"Подразделение '{subdivision.name}': нет получателей, пропускаем")
            continue

        logger.info(f"Собрано {len(recipients)} получателей: {', '.join(recipients)}")
        total_recipients.update(recipients)

        # Генерируем документ
        try:
            # Формируем дополнительный контекст с данными инструктажа
            custom_context = {
                'instruction_type': briefing_data.get('instruction_type', 'Повторный'),
                'instruction_reason': briefing_data.get('instruction_reason', ''),
            }

            doc = generate_instruction_journal(
                employees=employees_with_instructions,
                date_povtorny=briefing_data['date'],
                user=request.user,
                grouping_name=subdivision.name,
                custom_context=custom_context
            )

            if not doc:
                # Создаём запись об ошибке
                InstructionJournalSendDetail.objects.create(
                    send_log=send_log,
                    subdivision=subdivision,
                    status='failed',
                    skip_reason='doc_generation_failed',
                    recipients=json.dumps(recipients),
                    recipients_count=len(recipients),
                    employees_count=len(employees_with_instructions),
                    email_subject='',
                    error_message='Не удалось сгенерировать документ'
                )
                failed_sent += 1
                logger.error(f"Не удалось сгенерировать документ для {subdivision.name}")
                continue

            logger.info(f"Документ успешно сгенерирован: {doc['filename']}")
        except Exception as e:
            # Создаём запись об ошибке
            InstructionJournalSendDetail.objects.create(
                send_log=send_log,
                subdivision=subdivision,
                status='failed',
                skip_reason='doc_generation_failed',
                recipients=json.dumps(recipients),
                recipients_count=len(recipients),
                employees_count=len(employees_with_instructions),
                email_subject='',
                error_message=str(e)
            )
            failed_sent += 1
            logger.error(f"Ошибка генерации документа для {subdivision.name}: {str(e)}", exc_info=True)
            continue

        # Отправляем email
        try:
            connection = email_settings.get_connection()
            from_email = email_settings.default_from_email or email_settings.email_host_user

            # Собираем уникальные отделы сотрудников
            departments = set()
            for emp in employees_with_instructions:
                if emp.department:
                    departments.add(emp.department.name)

            # Формируем название отдела для шаблона
            if len(departments) == 0:
                department_name = "Без отдела"
            elif len(departments) == 1:
                department_name = list(departments)[0]
            else:
                department_name = "Все отделы"

            # Подготовка переменных для шаблона
            template_vars = {
                'organization_name': organization.full_name_ru,
                'subdivision_name': subdivision.name,
                'department_name': department_name,
                'date': briefing_data.get('date', date.today().strftime('%d.%m.%Y')),
                'instruction_type': briefing_data.get('instruction_type', 'Повторный'),
                'instruction_reason': briefing_data.get('instruction_reason', ''),
                'employee_count': len(employees_with_instructions),
            }

            # Получаем шаблон письма из новой системы шаблонов
            template_data = email_settings.get_email_template('instruction_journal')
            if not template_data:
                # Создаём запись об ошибке
                InstructionJournalSendDetail.objects.create(
                    send_log=send_log,
                    subdivision=subdivision,
                    status='failed',
                    skip_reason='template_not_found',
                    recipients=json.dumps(recipients),
                    recipients_count=len(recipients),
                    employees_count=len(employees_with_instructions),
                    email_subject='',
                    error_message='Шаблон письма не настроен'
                )
                failed_sent += 1
                logger.error(f"Шаблон письма не настроен для {subdivision.name}")
                continue

            # Форматируем тему и текст письма
            subject = template_data[0].format(**template_vars)
            html_message = template_data[1].format(**template_vars)

            # Создаем текстовую версию (для клиентов без HTML)
            from django.utils.html import strip_tags
            text_message = strip_tags(html_message)

            email = EmailMultiAlternatives(
                subject=subject,
                body=text_message,
                from_email=from_email,
                to=recipients,
                connection=connection
            )

            # Прикрепляем HTML версию
            email.attach_alternative(html_message, "text/html")

            # Прикрепляем документ
            email.attach(
                doc['filename'],
                doc['content'],
                'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
            )

            email.send(fail_silently=False)

            # Создаём запись об успехе
            InstructionJournalSendDetail.objects.create(
                send_log=send_log,
                subdivision=subdivision,
                status='success',
                recipients=json.dumps(recipients),
                recipients_count=len(recipients),
                employees_count=len(employees_with_instructions),
                email_subject=subject,
                sent_at=timezone.now()
            )

            logger.info(
                f"Образец отправлен для {subdivision.name}. "
                f"Получатели: {', '.join(recipients)}. "
                f"Сотрудников: {len(employees_with_instructions)}"
            )

            successful_sent += 1
            total_employees += len(employees_with_instructions)

        except Exception as e:
            # Создаём запись об ошибке отправки email
            InstructionJournalSendDetail.objects.create(
                send_log=send_log,
                subdivision=subdivision,
                status='failed',
                skip_reason='email_send_failed',
                recipients=json.dumps(recipients),
                recipients_count=len(recipients),
                employees_count=len(employees_with_instructions),
                email_subject=subject if 'subject' in locals() else '',
                error_message=str(e)
            )
            failed_sent += 1
            logger.error(f"Ошибка отправки email для {subdivision.name}: {str(e)}", exc_info=True)

    # Обновляем итоговую статистику лога
    send_log.successful_count = successful_sent
    send_log.failed_count = failed_sent
    send_log.skipped_count = skipped_count

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
    total_recipients = set()
    has_any_recipients = False

    for subdivision in subdivisions:
        # Получаем сотрудников с инструкциями
        employees = Employee.objects.filter(
            organization=organization,
            subdivision=subdivision,
            status='active',
            position__isnull=False
        ).select_related('position', 'department')

        # Фильтруем только сотрудников с инструкциями (проверяем все типы инструкций)
        employees_with_instructions = []
        for emp in employees:
            position = emp.position
            if position:
                has_instructions = bool(
                    (position.safety_instructions_numbers and position.safety_instructions_numbers.strip()) or
                    (position.contract_safety_instructions and position.contract_safety_instructions.strip()) or
                    (position.company_vehicle_instructions and position.company_vehicle_instructions.strip())
                )
                if has_instructions:
                    employees_with_instructions.append(emp)

        if not employees_with_instructions:
            continue

        # Собираем информацию о получателях для этого подразделения
        from directory.utils.email_recipients import collect_recipients_for_subdivision
        recipients = collect_recipients_for_subdivision(
            subdivision,
            organization,
            notification_type='instruction_journal'
        )

        # Собираем уникальные отделы сотрудников
        departments_in_subdivision = {}
        for emp in employees_with_instructions:
            dept_name = emp.department.name if emp.department else "Без отдела"
            if dept_name not in departments_in_subdivision:
                departments_in_subdivision[dept_name] = []
            departments_in_subdivision[dept_name].append(emp)

        # Определяем название отдела для шаблона
        if len(departments_in_subdivision) == 0:
            department_name = "Без отдела"
        elif len(departments_in_subdivision) == 1:
            department_name = list(departments_in_subdivision.keys())[0]
        else:
            department_name = "Все отделы"

        # Добавляем получателей в общий список
        total_recipients.update(recipients)
        has_recipients = len(recipients) > 0
        if has_recipients:
            has_any_recipients = True

        # Формируем переменные для подстановки в шаблон
        template_vars = {
            'organization_name': organization.full_name_ru,
            'subdivision_name': subdivision.name,
            'department_name': department_name,
            'employee_count': len(employees_with_instructions),
            'date': briefing_data.get('date', date.today().strftime('%d.%m.%Y')),
            'instruction_type': briefing_data.get('instruction_type', 'Повторный'),
            'instruction_reason': briefing_data.get('instruction_reason', ''),
        }

        # Получаем шаблон письма из новой системы шаблонов
        template_data = email_settings.get_email_template('instruction_journal')
        if template_data:
            subject = template_data[0].format(**template_vars)
        else:
            subject = "Шаблон не настроен"

        tree_data.append({
            'subdivision': subdivision,
            'department_name': department_name,
            'departments': departments_in_subdivision,
            'employees_count': len(employees_with_instructions),
            'recipients': recipients,
            'has_recipients': has_recipients,
            'email_subject': subject,
        })

    # Форматируем текст письма с примером (берём первое подразделение)
    template_data = email_settings.get_email_template('instruction_journal')
    if tree_data and template_data:
        example_vars = {
            'organization_name': organization.full_name_ru,
            'subdivision_name': tree_data[0]['subdivision'].name,
            'department_name': tree_data[0]['department_name'],
            'employee_count': tree_data[0]['employees_count'],
            'date': briefing_data.get('date', date.today().strftime('%d.%m.%Y')),
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
        'total_recipients': total_recipients,
        'total_recipients_count': len(total_recipients),
        'briefing_data': briefing_data,
        'email_body_preview': email_body_preview,
        'has_any_recipients': has_any_recipients,
    }

    return render(request, 'directory/documents/instruction_journal_preview.html', context)
