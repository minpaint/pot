"""
⚙️ Task-функции для асинхронной массовой генерации документов.

Каждая функция:
  • принимает id записи GenerationJob
  • подгружает параметры из job.params
  • вызывает существующий sync-генератор (или обёртку для архивов)
  • сохраняет результат в job.result_file
  • обновляет progress/status

Запуск worker: `manage.py db_worker`
Перезапуск после изменений: `sudo systemctl restart potby-worker`
"""
import logging
import re
import traceback
from datetime import datetime
from io import BytesIO
from zipfile import ZipFile, ZIP_DEFLATED

from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.utils import timezone
from django_tasks import task

from directory.models import Employee, GenerationJob

logger = logging.getLogger(__name__)

DOCX_CT = 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
ZIP_CT  = 'application/zip'


# ─── Общие хелперы ────────────────────────────────────────────────────────────

def _get_user(user_id):
    return get_user_model().objects.filter(pk=user_id).first()


def _load_employees(ids):
    """Загружает сотрудников в том же порядке, что переданы ids."""
    qs = Employee.objects.select_related(
        'organization', 'subdivision', 'department', 'position'
    ).filter(id__in=ids)
    by_id = {e.id: e for e in qs}
    return [by_id[i] for i in ids if i in by_id]


def _finalize(job, *, status, file_bytes=None, filename=None, content_type=None, error=''):
    """Финализирует задачу: сохраняет файл и обновляет статус через update() для избежания race."""
    update_fields = {'status': status, 'completed_at': timezone.now()}
    if error:
        update_fields['error_message'] = error
    if file_bytes and filename:
        # Сначала сохраняем файл через ORM (нужен job.id для пути)
        job.result_file.save(filename, ContentFile(file_bytes), save=False)
        update_fields['result_file'] = job.result_file.name
        update_fields['result_filename'] = filename
        update_fields['content_type'] = content_type or ''
    GenerationJob.objects.filter(pk=job.pk).update(**update_fields)


def _start_job(job):
    job.status = 'running'
    job.started_at = timezone.now()
    job.save(update_fields=['status', 'started_at'])


def _safe_name(value):
    return re.sub(r'[<>:"/\\|?*]', '_', str(value))


# ─── 1. Протоколы периодической проверки знаний / Удостоверения ───────────────

@task()
def run_periodic_protocol_job(job_id: int):
    """Протоколы ПЗ (один файл / ZIP по подразделениям) и удостоверения по ОТ."""
    from directory.document_generators.protocol_generator import generate_periodic_protocol
    from directory.document_generators.certificate_generator_rowwise import (
        generate_safety_certificates_rowwise as generate_safety_certificates,
    )

    try:
        job = GenerationJob.objects.get(pk=job_id)
    except GenerationJob.DoesNotExist:
        logger.error(f'GenerationJob #{job_id} не найден')
        return

    try:
        _start_job(job)
        user = _get_user(job.user_id)

        employee_ids = job.params.get('employee_ids', [])
        employees = _load_employees(employee_ids)
        if not employees:
            _finalize(job, status='failed', error='Нет сотрудников для генерации')
            return

        GenerationJob.objects.filter(pk=job.pk).update(progress_total=len(employees))

        jt = job.job_type

        check_type = job.params.get('check_type', 'периодическая') or 'периодическая'
        height_only = bool(job.params.get('height_only', False))

        if jt == 'periodic_protocol':
            grouping_name = job.params.get('grouping_name') or None
            doc = generate_periodic_protocol(
                employees, user=user, grouping_name=grouping_name,
                check_type=check_type, height_only=height_only,
            )
            if not doc:
                _finalize(job, status='failed', error='Не удалось сформировать протокол')
                return
            _finalize(job, status='done', file_bytes=doc['content'],
                      filename=doc['filename'], content_type=DOCX_CT)
            GenerationJob.objects.filter(pk=job.pk).update(progress_current=len(employees))
            return

        if jt == 'periodic_certificates':
            grouping_name = job.params.get('grouping_name') or None
            doc = generate_safety_certificates(employees, grouping_name=grouping_name)
            if not doc:
                _finalize(job, status='failed', error='Не удалось сформировать удостоверения')
                return
            _finalize(job, status='done', file_bytes=doc['content'],
                      filename=doc['filename'], content_type=DOCX_CT)
            GenerationJob.objects.filter(pk=job.pk).update(progress_current=len(employees))
            return

        if jt in ('periodic_protocol_by_sub', 'periodic_certificates_by_sub'):
            grouped = {}
            for emp in employees:
                if jt == 'periodic_certificates_by_sub':
                    key = emp.subdivision.name if emp.subdivision else 'Без подразделения'
                else:
                    key = emp.subdivision.name if emp.subdivision else None
                grouped.setdefault(key, []).append(emp)

            buffer = BytesIO()
            done = 0
            files_written = 0
            with ZipFile(buffer, 'w') as zf:
                for key, emps in grouped.items():
                    if jt == 'periodic_protocol_by_sub':
                        doc = generate_periodic_protocol(
                            emps, user=user, grouping_name=key,
                            check_type=check_type, height_only=height_only,
                        )
                    else:
                        doc = generate_safety_certificates(emps, grouping_name=key)
                    if doc:
                        zf.writestr(doc['filename'], doc['content'])
                        files_written += 1
                    done += len(emps)
                    GenerationJob.objects.filter(pk=job.pk).update(progress_current=done)

            if not files_written:
                _finalize(job, status='failed', error='Нет документов для архива')
                return

            org = employees[0].organization
            org_name = org.short_name_ru if org else 'Организация'
            clean = org_name.replace('"', '').replace("'", '').replace('«', '').replace('»', '')
            base = ('Протоколы проверки знаний по ОТ'
                    if jt == 'periodic_protocol_by_sub' else 'Удостоверения по ОТ')
            _finalize(job, status='done', file_bytes=buffer.getvalue(),
                      filename=f'{base} {clean}.zip', content_type=ZIP_CT)
            return

        _finalize(job, status='failed', error=f'Неизвестный job_type: {jt}')

    except Exception as e:
        logger.exception(f'Ошибка в задаче #{job_id}')
        _finalize(job, status='failed',
                  error=f'{type(e).__name__}: {e}\n\n{traceback.format_exc()}')


# ─── 2. Личные карточки по ОТ ─────────────────────────────────────────────────

@task()
def run_ot_card_bulk_job(job_id: int):
    """ZIP-архив личных карточек по ОТ для списка сотрудников."""
    from directory.document_generators.ot_card_generator import generate_personal_ot_card

    try:
        job = GenerationJob.objects.get(pk=job_id)
    except GenerationJob.DoesNotExist:
        logger.error(f'GenerationJob #{job_id} не найден')
        return

    try:
        _start_job(job)
        user = _get_user(job.user_id)

        employee_ids = job.params.get('employee_ids', [])
        employees = Employee.objects.active_for_operations().filter(
            id__in=employee_ids, position__isnull=False,
        ).select_related('position', 'organization', 'subdivision', 'department').order_by(
            'subdivision__name', 'department__name', 'full_name_nominative'
        )
        employees = list(employees)

        if not employees:
            _finalize(job, status='failed', error='Нет сотрудников для генерации')
            return

        GenerationJob.objects.filter(pk=job.pk).update(progress_total=len(employees))

        instruction_date = job.params.get('instruction_date', '')
        instruction_type = job.params.get('instruction_type', 'Повторный')
        instruction_reason = job.params.get('instruction_reason', '')

        custom_context = {
            'instruction_date': instruction_date,
            'instruction_type': instruction_type,
            'instruction_reason': instruction_reason,
        }

        zip_buffer = BytesIO()
        generated = 0
        errors = []

        with ZipFile(zip_buffer, 'w', ZIP_DEFLATED) as zf:
            for i, employee in enumerate(employees, 1):
                try:
                    result = generate_personal_ot_card(employee, user=user, custom_context=custom_context)
                except Exception as e:
                    errors.append(f'{employee.full_name_nominative}: {e}')
                    logger.error(f'Ошибка карточки ОТ {employee.full_name_nominative}: {e}')
                    continue

                if result and 'content' in result:
                    folder = (_safe_name(employee.subdivision.name) if employee.subdivision
                              else _safe_name(employee.organization.short_name_ru) + ' (без подразделения)')
                    safe_emp = _safe_name(employee.full_name_nominative)
                    safe_pos = _safe_name(employee.position.position_name)
                    zf.writestr(f'{folder}/{safe_emp}_{safe_pos}.docx', result['content'])
                    generated += 1
                else:
                    errors.append(f'{employee.full_name_nominative}: пустой результат')

                GenerationJob.objects.filter(pk=job.pk).update(progress_current=i)

            summary = (
                f"Массовая генерация личных карточек по охране труда\n"
                f"Дата генерации: {datetime.now().strftime('%d.%m.%Y %H:%M')}\n"
                f"Вид инструктажа: {instruction_type}\n"
                f"Дата инструктажа: {instruction_date or 'не указана'}\n"
                f"Сгенерировано карточек: {generated}\n"
            )
            if errors:
                summary += "\nОшибки:\n" + "\n".join(errors)
            zf.writestr('_summary.txt', summary.encode('utf-8'))

        ts = datetime.now().strftime('%Y%m%d_%H%M%S')
        _finalize(job, status='done', file_bytes=zip_buffer.getvalue(),
                  filename=f'Личные_карточки_ОТ_{ts}.zip', content_type=ZIP_CT)

    except Exception as e:
        logger.exception(f'Ошибка в задаче #{job_id}')
        _finalize(job, status='failed',
                  error=f'{type(e).__name__}: {e}\n\n{traceback.format_exc()}')


# ─── 3. Журнал инструктажей ────────────────────────────────────────────────────

@task()
def run_instruction_journal_job(job_id: int):
    """Журнал инструктажей: один DOCX или ZIP по подразделениям."""
    from directory.document_generators.instruction_journal_generator import generate_instruction_journal

    try:
        job = GenerationJob.objects.get(pk=job_id)
    except GenerationJob.DoesNotExist:
        logger.error(f'GenerationJob #{job_id} не найден')
        return

    try:
        _start_job(job)
        user = _get_user(job.user_id)

        employee_ids = job.params.get('employee_ids', [])
        employees = _load_employees(employee_ids)
        if not employees:
            _finalize(job, status='failed', error='Нет сотрудников для генерации')
            return

        GenerationJob.objects.filter(pk=job.pk).update(progress_total=len(employees))

        date_povtorny = job.params.get('date_povtorny', '')
        custom_context = {
            'instruction_type': job.params.get('instruction_type', 'Повторный'),
            'instruction_reason': job.params.get('instruction_reason', ''),
        }

        jt = job.job_type

        if jt == 'instruction_journal_unified':
            doc = generate_instruction_journal(
                employees, date_povtorny=date_povtorny, user=user, custom_context=custom_context
            )
            if not doc:
                _finalize(job, status='failed', error='Не удалось сформировать журнал')
                return
            _finalize(job, status='done', file_bytes=doc['content'],
                      filename=doc['filename'], content_type=DOCX_CT)
            GenerationJob.objects.filter(pk=job.pk).update(progress_current=len(employees))
            return

        # instruction_journal_by_sub — ZIP
        grouped = {}
        for emp in employees:
            key = (emp.subdivision.name if emp.subdivision
                   else emp.organization.short_name_ru if emp.organization
                   else 'Без подразделения')
            grouped.setdefault(key, []).append(emp)

        buffer = BytesIO()
        done = 0
        files_generated = 0
        with ZipFile(buffer, 'w') as zf:
            for sub_name, emps in grouped.items():
                try:
                    doc = generate_instruction_journal(
                        emps, date_povtorny=date_povtorny,
                        grouping_name=sub_name, user=user, custom_context=custom_context
                    )
                    if doc:
                        safe = sub_name.replace('"', '').replace('/', '_').replace('\\', '_')
                        zf.writestr(f'Образец_журнала_{safe}.docx', doc['content'])
                        files_generated += 1
                except Exception as e:
                    logger.error(f"Ошибка журнала для '{sub_name}': {e}", exc_info=True)
                done += len(emps)
                GenerationJob.objects.filter(pk=job.pk).update(progress_current=done)

        if not files_generated:
            _finalize(job, status='failed', error='Не удалось сгенерировать ни одного файла')
            return

        _finalize(job, status='done', file_bytes=buffer.getvalue(),
                  filename='Образцы_журнала_по_подразделениям.zip', content_type=ZIP_CT)

    except Exception as e:
        logger.exception(f'Ошибка в задаче #{job_id}')
        _finalize(job, status='failed',
                  error=f'{type(e).__name__}: {e}\n\n{traceback.format_exc()}')


# ─── 4. Карточки СИЗ ──────────────────────────────────────────────────────────

@task()
def run_siz_cards_bulk_job(job_id: int):
    """ZIP-архив карточек СИЗ: по подразделениям или по организации."""
    from directory.document_generators.siz_card_docx_generator import generate_siz_card_docx
    from directory.models import StructuralSubdivision, Organization
    from directory.views.siz import (
        has_effective_siz_norms,
        _subdivision_employee_queryset,
        _safe_name as siz_safe_name,
    )

    try:
        job = GenerationJob.objects.get(pk=job_id)
    except GenerationJob.DoesNotExist:
        logger.error(f'GenerationJob #{job_id} не найден')
        return

    try:
        _start_job(job)
        user = _get_user(job.user_id)
        jt = job.job_type
        issue_date = job.params.get('issue_date', '')
        issue_date_display = ''
        if issue_date:
            try:
                issue_date_display = datetime.strptime(issue_date, '%Y-%m-%d').strftime('%d.%m.%Y')
            except ValueError:
                issue_date_display = issue_date
        custom_context = {'siz_issue_date': issue_date_display}

        zip_buffer = BytesIO()
        generated = 0
        errors = []

        if jt == 'siz_cards_org':
            # Сотрудники без подразделения из организации
            org_id = job.params.get('org_id')
            org = Organization.objects.get(pk=org_id)

            from django.db.models import Value
            from django.db.models.functions import Coalesce
            employees = Employee.objects.active_for_operations().filter(
                organization=org, position__isnull=False, subdivision__isnull=True,
            ).annotate(
                effective_subdivision_id=Coalesce(
                    'position__subdivision_id',
                    'position__department__subdivision_id',
                    Value(None),
                )
            ).filter(effective_subdivision_id__isnull=True).select_related('position')

            employees = list(employees)
            GenerationJob.objects.filter(pk=job.pk).update(progress_total=len(employees))

            with ZipFile(zip_buffer, 'w', ZIP_DEFLATED) as zf:
                for i, emp in enumerate(employees, 1):
                    if not emp.position or not has_effective_siz_norms(emp.position):
                        GenerationJob.objects.filter(pk=job.pk).update(progress_current=i)
                        continue
                    try:
                        result = generate_siz_card_docx(emp, user, custom_context, raise_on_error=True)
                    except Exception as e:
                        errors.append(f'{emp.full_name_nominative}: {e}')
                        continue
                    if result and 'content' in result:
                        zf.writestr(f'{siz_safe_name(emp.full_name_nominative)}_карточка_СИЗ.docx',
                                    result['content'])
                        generated += 1
                    GenerationJob.objects.filter(pk=job.pk).update(progress_current=i)

                _add_summary(zf, generated, errors, extra=f'Организация: {org.short_name_ru}')

            filename = f'Карточки_СИЗ_{siz_safe_name(org.short_name_ru)}_{datetime.now().strftime("%Y%m%d_%H%M%S")}.zip'

        else:
            # siz_cards_bulk — по списку подразделений
            subdivision_ids = job.params.get('subdivision_ids', [])
            subdivisions = list(StructuralSubdivision.objects.filter(pk__in=subdivision_ids))

            # Считаем всех сотрудников для прогресс-бара
            total = sum(
                _subdivision_employee_queryset(sub).count()
                for sub in subdivisions
            )
            GenerationJob.objects.filter(pk=job.pk).update(progress_total=total)
            done = 0

            with ZipFile(zip_buffer, 'w', ZIP_DEFLATED) as zf:
                for sub in subdivisions:
                    for emp in _subdivision_employee_queryset(sub):
                        if not emp.position or not has_effective_siz_norms(emp.position):
                            done += 1
                            GenerationJob.objects.filter(pk=job.pk).update(progress_current=done)
                            continue
                        try:
                            result = generate_siz_card_docx(emp, user, custom_context, raise_on_error=True)
                        except Exception as e:
                            errors.append(f'{emp.full_name_nominative}: {e}')
                            done += 1
                            GenerationJob.objects.filter(pk=job.pk).update(progress_current=done)
                            continue
                        if result and 'content' in result:
                            zf.writestr(
                                f'{siz_safe_name(sub.name)}/{siz_safe_name(emp.full_name_nominative)}_карточка_СИЗ.docx',
                                result['content']
                            )
                            generated += 1
                        done += 1
                        GenerationJob.objects.filter(pk=job.pk).update(progress_current=done)

                _add_summary(zf, generated, errors)

            filename = f'Карточки_СИЗ_{datetime.now().strftime("%Y%m%d_%H%M%S")}.zip'

        _finalize(job, status='done', file_bytes=zip_buffer.getvalue(),
                  filename=filename, content_type=ZIP_CT)

    except Exception as e:
        logger.exception(f'Ошибка в задаче #{job_id}')
        _finalize(job, status='failed',
                  error=f'{type(e).__name__}: {e}\n\n{traceback.format_exc()}')


def _add_summary(zf, generated, errors, extra=''):
    summary = (
        f"Массовая генерация карточек СИЗ\n"
        f"Дата: {datetime.now().strftime('%d.%m.%Y %H:%M')}\n"
        + (f"{extra}\n" if extra else '')
        + f"Сгенерировано: {generated}\n"
    )
    if errors:
        summary += "\nОшибки:\n" + "\n".join(errors)
    zf.writestr('_summary.txt', summary.encode('utf-8'))


# ─── 5. Документы приёма (admin_hiring) ───────────────────────────────────────

@task()
def run_admin_hiring_generate_job(job_id: int):
    """ZIP-архив документов приёма для выбранных EmployeeHiring."""
    from directory.models import EmployeeHiring
    from directory.utils.declension import get_initials_from_name

    try:
        job = GenerationJob.objects.get(pk=job_id)
    except GenerationJob.DoesNotExist:
        logger.error(f'GenerationJob #{job_id} не найден')
        return

    try:
        _start_job(job)
        user = _get_user(job.user_id)

        hiring_ids = job.params.get('hiring_ids', [])
        document_types = job.params.get('document_types', [])

        hirings = list(EmployeeHiring.objects.filter(id__in=hiring_ids).select_related(
            'employee', 'position', 'organization', 'subdivision', 'department'
        ))
        if not hirings:
            _finalize(job, status='failed', error='Записи о приёме не найдены')
            return

        GenerationJob.objects.filter(pk=job.pk).update(progress_total=len(hirings))

        from directory.document_generators.order_generator import generate_all_orders
        from directory.document_generators.protocol_generator import generate_knowledge_protocol
        from directory.document_generators.familiarization_generator import generate_familiarization_document
        from directory.document_generators.ot_card_generator import generate_personal_ot_card
        from directory.document_generators.journal_example_generator import generate_journal_example
        from directory.document_generators.siz_card_docx_generator import generate_siz_card_docx
        from directory.document_generators.vvodny_journal_generator import generate_vvodny_journal

        generator_map = {
            'all_orders':             generate_all_orders,
            'knowledge_protocol':     generate_knowledge_protocol,
            'doc_familiarization':    generate_familiarization_document,
            'personal_ot_card':       generate_personal_ot_card,
            'journal_example':        generate_journal_example,
            'siz_card':               generate_siz_card_docx,
            'vvodny_journal_template': generate_vvodny_journal,
        }

        all_files = []

        for i, hiring in enumerate(hirings, 1):
            employee = hiring.employee
            for doc_type in document_types:
                try:
                    generator_func = generator_map.get(doc_type)
                    if not generator_func:
                        continue
                    if doc_type == 'doc_familiarization':
                        result = generator_func(employee=employee, user=user, document_list=None)
                    else:
                        result = generator_func(employee=employee, user=user)

                    initials = get_initials_from_name(employee.full_name_nominative)
                    if isinstance(result, list):
                        for doc in result:
                            if isinstance(doc, dict) and 'content' in doc and 'filename' in doc:
                                all_files.append((doc['content'], f'{initials}_{doc["filename"]}'))
                    elif isinstance(result, dict) and 'content' in result and 'filename' in result:
                        all_files.append((result['content'], f'{initials}_{result["filename"]}'))
                except Exception as e:
                    logger.error(f'Ошибка {doc_type} для {employee.full_name_nominative}: {e}', exc_info=True)

            GenerationJob.objects.filter(pk=job.pk).update(progress_current=i)

        if not all_files:
            _finalize(job, status='failed', error='Не удалось сгенерировать ни одного документа')
            return

        zip_buffer = BytesIO()
        with ZipFile(zip_buffer, 'w', ZIP_DEFLATED) as zf:
            for content, filename in all_files:
                zf.writestr(filename, content)

        if len(hirings) == 1:
            initials = get_initials_from_name(hirings[0].employee.full_name_nominative)
            zip_name = f'Документы_{initials}.zip'
        else:
            zip_name = f'Документы_приема_{len(hirings)}_сотрудников.zip'

        _finalize(job, status='done', file_bytes=zip_buffer.getvalue(),
                  filename=zip_name, content_type=ZIP_CT)

    except Exception as e:
        logger.exception(f'Ошибка в задаче #{job_id}')
        _finalize(job, status='failed',
                  error=f'{type(e).__name__}: {e}\n\n{traceback.format_exc()}')
