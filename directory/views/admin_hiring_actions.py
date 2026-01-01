# directory/views/admin_hiring_actions.py

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib import messages
from django.http import HttpResponse
from django.utils.safestring import mark_safe
from django.core.mail import EmailMultiAlternatives
from django.utils.html import strip_tags
from django.utils import timezone

from directory.models import EmployeeHiring, DocumentTemplateType, DocumentEmailSendLog
from deadline_control.models import EmailSettings
from directory.utils.declension import get_initials_from_name
from directory.utils.email_recipients import collect_recipients_for_subdivision

import logging
import io
import zipfile
from urllib.parse import quote

logger = logging.getLogger(__name__)


def is_staff(user):
    """Проверка что пользователь - сотрудник админки"""
    return user.is_staff


@login_required
@user_passes_test(is_staff)
def admin_hiring_documents_action(request):
    """
    Обработка массовых действий из админки EmployeeHiring:
    - generate: генерация и скачивание документов
    - send: генерация и отправка документов по email
    """

    # Получаем параметры из GET (первый запрос от admin action) или POST (после выбора документов)
    if request.method == 'GET':
        hiring_ids = request.GET.getlist('ids')
        action = request.GET.get('action')
    else:
        hiring_ids = request.POST.getlist('hiring_ids')
        action = request.POST.get('action')

    if not hiring_ids:
        messages.error(request, "Не выбрано ни одной записи о приеме на работу")
        return redirect('admin:directory_employeehiring_changelist')

    if action not in ['generate', 'send']:
        messages.error(request, "Неверное действие")
        return redirect('admin:directory_employeehiring_changelist')

    # Получаем объекты EmployeeHiring
    hirings = EmployeeHiring.objects.filter(id__in=hiring_ids).select_related(
        'employee', 'position', 'organization', 'subdivision', 'department'
    )

    if not hirings.exists():
        messages.error(request, "Записи о приеме не найдены")
        return redirect('admin:directory_employeehiring_changelist')

    # Если это GET запрос - показываем форму выбора типов документов
    if request.method == 'GET':
        # Получаем типы документов из справочника
        document_types_choices = [
            (template_type.code, template_type.name)
            for template_type in DocumentTemplateType.objects.filter(
                is_active=True,
                show_in_hiring=True
            )
            if template_type.code != 'periodic_protocol'
        ]

        # Типы документов по умолчанию
        default_document_types = [
            'all_orders',
            'knowledge_protocol',
            'doc_familiarization',
            'personal_ot_card',
            'journal_example',
            'siz_card',
        ]

        action_title = "Генерация документов" if action == 'generate' else "Отправка документов"

        context = {
            'hirings': hirings,
            'hiring_ids': hiring_ids,
            'action': action,
            'action_title': action_title,
            'document_types_choices': document_types_choices,
            'default_document_types': default_document_types,
            'site_header': 'Администрирование OT_online',
        }

        return render(request, 'admin/directory/employeehiring/select_documents.html', context)

    # POST запрос - обрабатываем выбранные типы документов
    document_types = request.POST.getlist('document_types')

    if not document_types:
        messages.error(request, "Не выбран ни один тип документа")
        return redirect('admin:directory_employeehiring_changelist')

    if action == 'generate':
        return _handle_generate_documents(request, hirings, document_types)
    else:  # send
        return _handle_send_documents(request, hirings, document_types)


def _handle_generate_documents(request, hirings, document_types):
    """Генерация и скачивание документов для выбранных записей о приеме"""

    # Импортируем генераторы
    from directory.document_generators.order_generator import generate_all_orders
    from directory.document_generators.protocol_generator import generate_knowledge_protocol
    from directory.document_generators.familiarization_generator import generate_familiarization_document
    from directory.document_generators.ot_card_generator import generate_personal_ot_card
    from directory.document_generators.journal_example_generator import generate_journal_example
    from directory.document_generators.siz_card_docx_generator import generate_siz_card_docx
    from directory.document_generators.vvodny_journal_generator import generate_vvodny_journal

    generator_map = {
        'all_orders': generate_all_orders,
        'knowledge_protocol': generate_knowledge_protocol,
        'doc_familiarization': generate_familiarization_document,
        'personal_ot_card': generate_personal_ot_card,
        'journal_example': generate_journal_example,
        'siz_card': generate_siz_card_docx,
        'vvodny_journal_template': generate_vvodny_journal,
    }

    all_files = []  # Список всех файлов для архива

    # Генерируем документы для каждой записи о приеме
    for hiring in hirings:
        employee = hiring.employee

        for doc_type in document_types:
            try:
                generator_func = generator_map.get(doc_type)
                if generator_func:
                    if doc_type == 'doc_familiarization':
                        result = generator_func(employee=employee, user=request.user, document_list=None)
                    else:
                        result = generator_func(employee=employee, user=request.user)

                    # Обрабатываем результат
                    if result:
                        if isinstance(result, list):
                            for doc in result:
                                if isinstance(doc, dict) and 'content' in doc and 'filename' in doc:
                                    # Добавляем префикс с ФИО для различения файлов
                                    employee_initials = get_initials_from_name(employee.full_name_nominative)
                                    prefixed_filename = f"{employee_initials}_{doc['filename']}"
                                    all_files.append((doc['content'], prefixed_filename))
                        elif isinstance(result, dict) and 'content' in result and 'filename' in result:
                            employee_initials = get_initials_from_name(employee.full_name_nominative)
                            prefixed_filename = f"{employee_initials}_{result['filename']}"
                            all_files.append((result['content'], prefixed_filename))
            except Exception as e:
                logger.error(
                    f"Ошибка при генерации {doc_type} для {employee.full_name_nominative}: {str(e)}",
                    exc_info=True
                )
                messages.warning(
                    request,
                    f"Ошибка при генерации документа {doc_type} для {employee.full_name_nominative}"
                )
                continue

    if not all_files:
        messages.error(request, "Не удалось сгенерировать ни один документ")
        return redirect('admin:directory_employeehiring_changelist')

    # Создаем архив
    try:
        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zipf:
            for content, filename in all_files:
                zipf.writestr(filename, content)

        zip_buffer.seek(0)

        if len(hirings) == 1:
            employee_initials = get_initials_from_name(hirings[0].employee.full_name_nominative)
            zip_filename = f"Документы_{employee_initials}.zip"
        else:
            zip_filename = f"Документы_приема_{len(hirings)}_сотрудников.zip"

        response = HttpResponse(zip_buffer.getvalue(), content_type='application/zip')
        encoded_filename = quote(zip_filename)
        response['Content-Disposition'] = f"attachment; filename*=UTF-8''{encoded_filename}"

        messages.success(request, f"✅ Успешно сгенерировано документов: {len(all_files)}")
        return response

    except Exception as e:
        logger.error(f"Ошибка при создании архива: {str(e)}", exc_info=True)
        messages.error(request, f"Ошибка при создании архива: {str(e)}")
        return redirect('admin:directory_employeehiring_changelist')


def _handle_send_documents(request, hirings, document_types):
    """Генерация и отправка документов по email для выбранных записей о приеме"""

    # Импортируем генераторы
    from directory.document_generators.order_generator import generate_all_orders
    from directory.document_generators.protocol_generator import generate_knowledge_protocol
    from directory.document_generators.familiarization_generator import generate_familiarization_document
    from directory.document_generators.ot_card_generator import generate_personal_ot_card
    from directory.document_generators.journal_example_generator import generate_journal_example
    from directory.document_generators.siz_card_docx_generator import generate_siz_card_docx
    from directory.document_generators.vvodny_journal_generator import generate_vvodny_journal

    generator_map = {
        'all_orders': generate_all_orders,
        'knowledge_protocol': generate_knowledge_protocol,
        'doc_familiarization': generate_familiarization_document,
        'personal_ot_card': generate_personal_ot_card,
        'journal_example': generate_journal_example,
        'siz_card': generate_siz_card_docx,
        'vvodny_journal_template': generate_vvodny_journal,
    }

    success_count = 0
    error_count = 0

    # Обрабатываем каждую запись о приеме отдельно
    for hiring in hirings:
        try:
            employee = hiring.employee
            organization = hiring.organization
            subdivision = hiring.subdivision

            # Получаем настройки email
            try:
                email_settings = EmailSettings.get_settings(organization)
            except Exception as e:
                messages.error(
                    request,
                    f"Ошибка настроек email для {employee.full_name_nominative}: {str(e)}"
                )
                error_count += 1
                continue

            if not email_settings.is_active:
                messages.warning(
                    request,
                    f"Email уведомления отключены для {organization.short_name_ru}"
                )
                error_count += 1
                continue

            if not email_settings.email_host:
                messages.warning(
                    request,
                    f"SMTP не настроен для {organization.short_name_ru}"
                )
                error_count += 1
                continue

            # Генерируем документы
            generated_files = []

            for doc_type in document_types:
                try:
                    generator_func = generator_map.get(doc_type)
                    if generator_func:
                        if doc_type == 'doc_familiarization':
                            result = generator_func(employee=employee, user=request.user, document_list=None)
                        else:
                            result = generator_func(employee=employee, user=request.user)

                        if result:
                            if isinstance(result, list):
                                for doc in result:
                                    if isinstance(doc, dict) and 'content' in doc and 'filename' in doc:
                                        generated_files.append((doc['content'], doc['filename']))
                            elif isinstance(result, dict) and 'content' in result and 'filename' in result:
                                generated_files.append((result['content'], result['filename']))
                except Exception as e:
                    logger.error(f"Ошибка генерации {doc_type}: {str(e)}", exc_info=True)
                    continue

            if not generated_files:
                messages.warning(
                    request,
                    f"Не удалось сгенерировать документы для {employee.full_name_nominative}"
                )
                error_count += 1
                continue

            # Собираем получателей
            if subdivision:
                recipients = collect_recipients_for_subdivision(
                    subdivision=subdivision,
                    organization=organization,
                    notification_type='general'
                )
            else:
                recipients = email_settings.get_recipient_list()

            if not recipients:
                messages.warning(
                    request,
                    f"Нет получателей для {employee.full_name_nominative}"
                )
                error_count += 1
                continue

            # Получаем шаблон письма
            template_data = email_settings.get_email_template('documents_priem')

            if not template_data:
                messages.warning(
                    request,
                    f"Шаблон письма не настроен для {organization.short_name_ru}"
                )
                error_count += 1
                continue

            subject_template, body_template = template_data

            # Подготавливаем переменные для шаблона
            template_vars = {
                'organization_name': organization.short_name_ru or organization.full_name_ru,
                'employee_name': employee.full_name_nominative,
                'position_name': hiring.position.position_name,
                'subdivision_name': subdivision.name if subdivision else "Без подразделения",
                'department_name': hiring.department.name if hiring.department else "Без отдела",
                'hiring_date': hiring.hiring_date.strftime('%d.%m.%Y'),
                'start_date': hiring.start_date.strftime('%d.%m.%Y') if hiring.start_date else '',
                'hiring_type': hiring.get_hiring_type_display(),
                'document_count': len(generated_files),
                'date': timezone.now().strftime('%d.%m.%Y'),
            }

            # Форматируем тему и тело письма
            try:
                subject = subject_template.format(**template_vars)
                html_message = body_template.format(**template_vars)
            except KeyError as e:
                messages.warning(
                    request,
                    f"Ошибка в шаблоне письма для {employee.full_name_nominative}: переменная {e} не найдена"
                )
                error_count += 1
                continue

            # Создаем и отправляем email
            try:
                connection = email_settings.get_connection()
                from_email = email_settings.default_from_email or email_settings.email_host_user
                text_message = strip_tags(html_message)

                email = EmailMultiAlternatives(
                    subject=subject,
                    body=text_message,
                    from_email=from_email,
                    to=recipients,
                    connection=connection
                )

                email.attach_alternative(html_message, "text/html")

                # Прикрепляем документы
                for file_content, filename in generated_files:
                    try:
                        email.attach(
                            filename,
                            file_content,
                            'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
                        )
                    except Exception as e:
                        logger.error(f"Ошибка прикрепления {filename}: {str(e)}", exc_info=True)
                        continue

                # Отправляем
                email.send(fail_silently=False)

                logger.info(
                    f"Документы отправлены для {employee.full_name_nominative}. "
                    f"Получатели: {', '.join(recipients)}. Документов: {len(generated_files)}"
                )

                # Логируем успешную отправку в БД
                try:
                    DocumentEmailSendLog.objects.create(
                        employee=employee,
                        hiring=hiring,
                        document_types=document_types,
                        recipients=recipients,
                        recipients_count=len(recipients),
                        documents_count=len(generated_files),
                        status='success',
                        email_subject=subject,
                        sent_by=request.user
                    )
                except Exception as log_error:
                    logger.error(f"Ошибка логирования отправки: {str(log_error)}", exc_info=True)

                success_count += 1

            except Exception as e:
                logger.error(
                    f"Ошибка отправки email для {employee.full_name_nominative}: {str(e)}",
                    exc_info=True
                )
                messages.warning(
                    request,
                    f"Ошибка отправки для {employee.full_name_nominative}: {str(e)}"
                )

                # Логируем неудачную отправку в БД
                try:
                    DocumentEmailSendLog.objects.create(
                        employee=employee,
                        hiring=hiring,
                        document_types=document_types,
                        recipients=recipients if 'recipients' in locals() else [],
                        recipients_count=len(recipients) if 'recipients' in locals() else 0,
                        documents_count=len(generated_files),
                        status='failed',
                        error_message=str(e),
                        email_subject=subject if 'subject' in locals() else '',
                        sent_by=request.user
                    )
                except Exception as log_error:
                    logger.error(f"Ошибка логирования неудачной отправки: {str(log_error)}", exc_info=True)

                error_count += 1
                continue

        except Exception as e:
            logger.error(
                f"Общая ошибка обработки hiring_id={hiring.id}: {str(e)}",
                exc_info=True
            )
            error_count += 1
            continue

    # Итоговое сообщение
    if success_count > 0:
        messages.success(
            request,
            mark_safe(
                f"✅ Документы успешно отправлены для {success_count} "
                f"сотрудник{'а' if success_count == 1 else 'ов'}"
            )
        )

    if error_count > 0:
        messages.warning(
            request,
            f"⚠️ Ошибки при обработке {error_count} записей. Подробности см. выше."
        )

    return redirect('admin:directory_employeehiring_changelist')
