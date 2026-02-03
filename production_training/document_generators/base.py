# -*- coding: utf-8 -*-
"""
📄 Базовый модуль для генерации документов обучения на производстве

Содержит общие функции для работы с шаблонами TrainingAssignment.
"""
import os
import re
import logging
import datetime
import math
from pathlib import Path
from typing import Dict, Any, Optional
from io import BytesIO

from docxtpl import DocxTemplate
from django.conf import settings
from django.core.files.base import ContentFile

from directory.utils.docx_vml import replace_vml_text_in_docx
from directory.utils.declension import decline_full_name, decline_phrase, get_initials_before_surname, get_initials_from_name
from directory.document_generators.base import parse_organization_name
from production_training.document_templates.field_mapping import get_vml_replacements
from production_training import schedule as training_schedule

logger = logging.getLogger(__name__)


# ============================================================================
# МАППИНГ ИМЁН ШАБЛОНОВ
# ============================================================================

TEMPLATE_NAMES = {
    'application.docx': '1.Заявление.docx',
    'order.docx': '2. Приказ о назначении обучения.docx',
    'theory_card.docx': '3. Карточка теория.docx',
    'presentation.docx': '5. Представление на квалификационную работу.docx',
    'trial_conclusion.docx': '6. Заключение на пробную работу.docx',
    'trial_application.docx': '7. Заявление на квалификационный экзамен.docx',
    'protocol.docx': '8. Протокол квалификационной комиссии.docx',
    # Дневники выбираются по типу обучения в TrainingAssignment.get_diary_template_path()
    'diary_podgotovka_voditel_pogruzchika.docx': '4.1.diary_podgotovka_voditel_pogruzchika.docx',
    'diary_perepodgotovka_voditel_pogruzchika.docx': '4.diary_perepodgotovka_voditel_pogruzchika.docx',
}

ROLE_MISSING_LABEL = 'Роль не указана в курсе'


def _format_date(value: Optional[datetime.date]) -> str:
    if not value:
        return ''
    return value.strftime('%d.%m.%Y')


def _build_person_context(person, position_name: str = '') -> Dict[str, Any]:
    if not person:
        return {
            'full_name_nominative': '',
            'full_name_genitive': '',
            'full_name_dative': '',
            'full_name_accusative': '',
            'short_name': '',
            'short_name_genitive': '',
            'position_nominative': '',
            'position_genitive': '',
            'position_dative': '',
            'position_accusative': '',
        }

    full_name = person.full_name_nominative
    full_name_gen = decline_full_name(full_name, 'gent')
    full_name_dat = decline_full_name(full_name, 'datv')
    full_name_acc = decline_full_name(full_name, 'accs')

    position = position_name
    if not position and getattr(person, 'position', None):
        position = person.position.position_name

    return {
        'full_name_nominative': full_name,
        'full_name_genitive': full_name_gen,
        'full_name_dative': full_name_dat,
        'full_name_accusative': full_name_acc,
        'short_name': get_initials_before_surname(full_name),
        'short_name_genitive': get_initials_before_surname(full_name_gen),
        'position_nominative': position,
        'position_genitive': decline_phrase(position, 'gent') if position else '',
        'position_dative': decline_phrase(position, 'datv') if position else '',
        'position_accusative': decline_phrase(position, 'accs') if position else '',
    }


def _mark_role_missing(context: Dict[str, Any]) -> Dict[str, Any]:
    """Заполняет контекст роли сообщением об отсутствии в курсе."""
    for key in (
        'full_name_nominative',
        'full_name_genitive',
        'full_name_dative',
        'full_name_accusative',
        'short_name',
        'short_name_genitive',
    ):
        context[key] = ROLE_MISSING_LABEL
    context['is_missing'] = True
    return context


def _score_to_word(value: Optional[str]) -> str:
    if value is None:
        return ''
    try:
        num = int(str(value).strip())
    except (TypeError, ValueError):
        return ''
    words = {
        0: 'ноль',
        1: 'один',
        2: 'два',
        3: 'три',
        4: 'четыре',
        5: 'пять',
        6: 'шесть',
        7: 'семь',
        8: 'восемь',
        9: 'девять',
        10: 'десять',
    }
    return words.get(num, '')


def _parse_score(value: Optional[str]) -> Optional[float]:
    if value is None:
        return None
    raw = str(value).strip()
    if not raw:
        return None
    raw = raw.replace(',', '.')
    try:
        return float(raw)
    except ValueError:
        return None


def _round_score(value: Optional[float]) -> Optional[int]:
    if value is None:
        return None
    return int(math.floor(value + 0.5))


def prepare_training_context(training) -> Dict[str, Any]:
    """
    Подготавливает базовый контекст для генерации документов обучения.

    Args:
        training: Объект TrainingAssignment

    Returns:
        Dict[str, Any]: Контекст с данными обучения
    """
    context = {}

    # === ОРГАНИЗАЦИЯ ===
    if training.organization:
        legal_form, _ = parse_organization_name(training.organization.full_name_ru)
        context['organization'] = {
            'full_name_ru': training.organization.full_name_ru,
            'short_name_ru': training.organization.short_name_ru,
            'full_name_by': training.organization.full_name_by,
            'short_name_by': training.organization.short_name_by,
            'legal_form': legal_form,
        }
        context['organization_full_name_ru'] = training.organization.full_name_ru
        context['organization_short_name_ru'] = training.organization.short_name_ru
        context['organization_full_name_by'] = training.organization.full_name_by
        context['organization_short_name_by'] = training.organization.short_name_by
        context['organization_location'] = getattr(training.organization, 'location', 'г. Минск')

    # === СОТРУДНИК ===
    employee = getattr(training, 'employee', None)
    if employee:
        fio = employee.full_name_nominative
        fio_by = employee.full_name_by or fio
        position_name = ''
        current_position = getattr(training, 'current_position', None)
        if current_position:
            position_name = current_position.position_name
        elif employee.position:
            position_name = employee.position.position_name

        employee_context = _build_person_context(employee, position_name=position_name)
        employee_context['birth_date'] = _format_date(employee.date_of_birth)
        context['employee'] = employee_context

        # Падежные формы ФИО (русский)
        context['employee_fio_nominative'] = fio
        context['employee_fio_genitive'] = decline_full_name(fio, 'gent')
        context['employee_fio_dative'] = decline_full_name(fio, 'datv')
        context['employee_fio_accusative'] = decline_full_name(fio, 'accs')
        context['employee_fio_instrumental'] = decline_full_name(fio, 'ablt')

        # Белорусская версия
        context['employee_fio_by'] = fio_by
        context['employee_fio_genitive_by'] = decline_full_name(fio_by, 'gent')
        context['employee_fio_dative_by'] = decline_full_name(fio_by, 'datv')

        # Инициалы
        context['employee_initials'] = get_initials_before_surname(fio)
        context['employee_initials_by'] = get_initials_before_surname(fio_by)

        # Разбить на фамилию, имя, отчество (русский)
        parts = fio.split()
        if len(parts) >= 1:
            context['employee_surname'] = parts[0]
        if len(parts) >= 2:
            context['employee_name'] = parts[1]
        if len(parts) >= 3:
            context['employee_patronymic'] = parts[2]

        # Разбить на фамилию, имя, отчество (белорусский)
        parts_by = fio_by.split()
        if len(parts_by) >= 1:
            context['employee_surname_by'] = parts_by[0]
        if len(parts_by) >= 2:
            context['employee_name_by'] = parts_by[1]
        if len(parts_by) >= 3:
            context['employee_patronymic_by'] = parts_by[2]

        if employee.education_level:
            context['education_level'] = {
                'name_ru': employee.education_level,
                'name_by': employee.education_level,
            }
            context['education_level_ru'] = employee.education_level
            context['education_level_by'] = employee.education_level
            context['education_level_value'] = employee.education_level
        else:
            context['education_level'] = {'name_ru': '', 'name_by': ''}
            context['education_level_value'] = ''

        context['prior_qualification'] = employee.prior_qualification
        context['qualification_document_number'] = employee.qualification_document_number
        context['qualification_document_date'] = employee.qualification_document_date
        if employee.qualification_document_date:
            context['qualification_document_date_formatted'] = (
                employee.qualification_document_date.strftime('%d.%m.%Y')
            )
    else:
        context['employee'] = _build_person_context(None)

    # === ПРОФЕССИЯ ОБУЧЕНИЯ ===
    if training.profession:
        context['profession'] = {
            'name_ru_nominative': training.profession.name_ru_nominative,
            'name_ru_genitive': training.profession.name_ru_genitive,
            'name_by_nominative': training.profession.name_by_nominative,
            'name_by_genitive': training.profession.name_by_genitive,
        }
        context['profession_nominative_ru'] = training.profession.name_ru_nominative
        context['profession_genitive_ru'] = training.profession.name_ru_genitive
        context['profession_nominative_by'] = training.profession.name_by_nominative
        context['profession_genitive_by'] = training.profession.name_by_genitive
    else:
        context['profession'] = {
            'name_ru_nominative': '',
            'name_ru_genitive': '',
            'name_by_nominative': '',
            'name_by_genitive': '',
        }

    # === ТИП ОБУЧЕНИЯ ===
    if training.training_type:
        name_ru = training.training_type.name_ru
        context['training_type'] = {
            'name_ru': name_ru,
            'name_by': training.training_type.name_by,
            'name_ru_genitive': decline_phrase(name_ru, 'gent'),
            'name_ru_accusative': decline_phrase(name_ru, 'accs'),
            'code': training.training_type.code,
        }
        context['training_type_ru'] = training.training_type.name_ru
        context['training_type_by'] = training.training_type.name_by
        context['training_type_code'] = training.training_type.code
    else:
        context['training_type'] = {
            'name_ru': '',
            'name_by': '',
            'name_ru_genitive': '',
            'name_ru_accusative': '',
            'code': '',
        }

    # === РАЗРЯД ===
    if training.qualification_grade:
        label_ru = training.qualification_grade.label_ru
        grade_number = training.qualification_grade.grade_number
        # Извлекаем слово из скобок и склоняем: "3 (третий)" -> "третьего разряда"
        match = re.search(r'\(([^)]+)\)', label_ru)
        if match:
            word_in_brackets = match.group(1)
            label_ru_genitive = f"{decline_phrase(word_in_brackets, 'gent')} разряда"
        else:
            label_ru_genitive = decline_phrase(label_ru, 'gent')
        # Короткий формат: "3-й" вместо "3 (третий)"
        label_ru_short = f"{grade_number}-й" if grade_number else ''
        context['qualification_grade'] = {
            'grade_number': grade_number,
            'label_ru': label_ru,
            'label_ru_short': label_ru_short,
            'label_by': training.qualification_grade.label_by,
            'label_ru_genitive': label_ru_genitive,
        }
        context['qualification_grade_number'] = grade_number
        context['qualification_grade_ru'] = training.qualification_grade.label_ru
        context['qualification_grade_by'] = training.qualification_grade.label_by
    else:
        context['qualification_grade'] = {
            'grade_number': '',
            'label_ru': '',
            'label_ru_short': '',
            'label_by': '',
            'label_ru_genitive': '',
        }

    # === ПРОГРАММА ===
    if training.program:
        context['program_name'] = training.program.name
        context['program_total_hours'] = training.program.get_total_hours()
        context['program_theory_hours'] = training.program.get_theory_hours()
        context['program_practice_hours'] = training.program.get_practice_hours()

    # === ДАТЫ ===
    context['start_date'] = _format_date(getattr(training, 'start_date', None))
    context['end_date'] = _format_date(getattr(training, 'end_date', None))
    context['exam_date'] = _format_date(getattr(training, 'exam_date', None))
    context['practical_date'] = _format_date(getattr(training, 'practical_date', None))
    context['protocol_date'] = _format_date(getattr(training, 'protocol_date', None))
    context['issue_date'] = _format_date(getattr(training, 'issue_date', None))
    start_date_value = getattr(training, 'start_date', None)
    context['start_year'] = start_date_value.year if start_date_value else ''

    # Форматированные даты
    if start_date_value:
        context['start_date_formatted'] = start_date_value.strftime('%d.%m.%Y')
    end_date_value = getattr(training, 'end_date', None)
    if end_date_value:
        context['end_date_formatted'] = end_date_value.strftime('%d.%m.%Y')
    if getattr(training, 'exam_date', None) and hasattr(training, 'get_exam_date_formatted'):
        context['exam_date_formatted'] = training.get_exam_date_formatted('ru')
        context['exam_date_formatted_by'] = training.get_exam_date_formatted('by')
    if getattr(training, 'practical_date', None) and hasattr(training, 'get_practical_date_formatted'):
        context['practical_date_formatted'] = training.get_practical_date_formatted('ru')
        context['practical_date_formatted_by'] = training.get_practical_date_formatted('by')

    # Период обучения
    if hasattr(training, 'get_period_str'):
        context['period_str_ru'] = training.get_period_str('ru')
        context['period_str_by'] = training.get_period_str('by')
    else:
        context['period_str_ru'] = ''
        context['period_str_by'] = ''

    # === РОЛИ (с падежами и инициалами) ===
    resolved_commission = training.commission
    if not resolved_commission and employee:
        try:
            from directory.utils.commission_service import find_appropriate_commission
            resolved_commission = find_appropriate_commission(
                employee,
                commission_type='qualification'
            )
        except Exception:
            resolved_commission = None
    # Инструктор
    instructor_person = training.instructor
    if instructor_person:
        instructor_fio = instructor_person.full_name_nominative
        context['instructor_name'] = instructor_fio
        context['instructor_name_genitive'] = decline_full_name(instructor_fio, 'gent')
        context['instructor_name_dative'] = decline_full_name(instructor_fio, 'datv')
        context['instructor_initials'] = get_initials_before_surname(instructor_fio)
    else:
        context['instructor_name'] = ROLE_MISSING_LABEL
        context['instructor_name_genitive'] = ROLE_MISSING_LABEL
        context['instructor_name_dative'] = ROLE_MISSING_LABEL
        context['instructor_initials'] = ROLE_MISSING_LABEL

    # Консультант по теории
    consultant_person = training.theory_consultant
    if consultant_person:
        consultant_fio = consultant_person.full_name_nominative
        context['consultant_name'] = consultant_fio
        context['consultant_name_genitive'] = decline_full_name(consultant_fio, 'gent')
        context['consultant_name_dative'] = decline_full_name(consultant_fio, 'datv')
        context['consultant_initials'] = get_initials_before_surname(consultant_fio)
    else:
        context['consultant_name'] = ROLE_MISSING_LABEL
        context['consultant_name_genitive'] = ROLE_MISSING_LABEL
        context['consultant_name_dative'] = ROLE_MISSING_LABEL
        context['consultant_initials'] = ROLE_MISSING_LABEL

    commission_chairman_person = None
    commission_members_people = []
    if resolved_commission:
        commission_members_qs = resolved_commission.members.select_related(
            'employee',
            'employee__position'
        ).filter(is_active=True)
        chairman_member = commission_members_qs.filter(role='chairman').first()
        if not chairman_member:
            chairman_member = commission_members_qs.filter(role='vice_chairman').first()
        if chairman_member and chairman_member.employee_id:
            commission_chairman_person = chairman_member.employee
        commission_members_people = [
            m.employee
            for m in commission_members_qs.exclude(role='chairman')
            if m.employee_id
        ]
    if not commission_chairman_person:
        commission_chairman_person = training.commission_chairman
    if not commission_members_people:
        commission_members_people = list(training.commission_members.all())

    # Председатель комиссии
    if commission_chairman_person:
        chairman_fio = commission_chairman_person.full_name_nominative
        context['chairman_name'] = chairman_fio
        context['chairman_name_genitive'] = decline_full_name(chairman_fio, 'gent')
        context['chairman_initials'] = get_initials_before_surname(chairman_fio)
    else:
        context['chairman_name'] = ROLE_MISSING_LABEL
        context['chairman_name_genitive'] = ROLE_MISSING_LABEL
        context['chairman_initials'] = ROLE_MISSING_LABEL

    # Члены комиссии
    context['commission_members'] = ', '.join([
        member.full_name_nominative
        for member in commission_members_people
    ])
    # Список членов комиссии с инициалами
    if commission_members_people:
        members_initials = [
            get_initials_before_surname(m.full_name_nominative)
            for m in commission_members_people
        ]
        context['commission_members_initials'] = ', '.join(members_initials)
    else:
        context['commission_members_initials'] = ''

    # === КОМИССИЯ ===
    if resolved_commission:
        context['commission_name'] = str(resolved_commission)

    # === ОЦЕНКИ ===
    theory_score = getattr(training, 'theory_score', '') or ''
    exam_score = getattr(training, 'exam_score', '') or ''
    practical_score = getattr(training, 'practical_score', '') or ''

    if not exam_score:
        theory_value = _parse_score(theory_score)
        practical_value = _parse_score(practical_score)
        if theory_value is not None and practical_value is not None:
            averaged = (theory_value + practical_value) / 2
            rounded = _round_score(averaged)
            exam_score = str(rounded) if rounded is not None else ''

    context['theory_score'] = theory_score
    context['exam_score'] = exam_score
    context['practical_score'] = practical_score
    practical_work_topic = getattr(training, 'practical_work_topic', '') or ''
    if not practical_work_topic:
        program = getattr(training, 'program', None)
        practical_work_topic = getattr(program, 'practical_work_topic', '') if program else ''
    context['practical_work_topic'] = practical_work_topic
    context['theory_score_word'] = _score_to_word(theory_score)
    context['exam_score_word'] = _score_to_word(exam_score)
    context['practical_score_word'] = _score_to_word(practical_score)

    # === ДОКУМЕНТЫ ===
    context['registration_number'] = getattr(training, 'registration_number', '') or ''
    context['protocol_number'] = getattr(training, 'protocol_number', '') or ''
    context['order_number'] = getattr(training, 'registration_number', '') or ''

    # === МЕСТО ПРОВЕДЕНИЯ ===
    context['training_city_ru'] = getattr(training, 'training_city_ru', '') or ''
    context['training_city_by'] = getattr(training, 'training_city_by', '') or ''

    # === ДОПОЛНИТЕЛЬНЫЕ ДАННЫЕ ===
    prior_qualification = getattr(training, 'prior_qualification', None)
    if not prior_qualification and employee:
        prior_qualification = getattr(employee, 'prior_qualification', '')
    context['prior_qualification'] = prior_qualification or ''
    context['workplace'] = getattr(training, 'workplace', '') or ''

    # === ТЕКУЩАЯ ПРОФЕССИЯ НА ПРЕДПРИЯТИИ ===
    current_position = getattr(training, 'current_position', None)
    if not current_position and employee:
        current_position = getattr(employee, 'position', None)
    if current_position:
        context['current_position_name'] = current_position.position_name

    # === ДАТЫ ДЛЯ ТЕОРИИ ===
    theory_dates = training.get_theory_dates() if hasattr(training, 'get_theory_dates') else []
    context['theory_dates'] = theory_dates
    if len(theory_dates) >= 2:
        context['theory_date_1'] = theory_dates[0].strftime('%d.%m.%Y')
        context['theory_date_2'] = theory_dates[1].strftime('%d.%m.%Y')

    # Даты для консультаций
    context['consultation_start_date'] = _format_date(theory_dates[0]) if theory_dates else ''
    context['consultation_end_date'] = _format_date(theory_dates[-1]) if theory_dates else ''
    consultation_sessions = []
    consultant_short_name = ''
    if consultant_person:
        consultant_short_name = get_initials_from_name(consultant_person.full_name_nominative)
    else:
        consultant_short_name = ROLE_MISSING_LABEL
    hours_per_session = 2
    training_type_code = getattr(getattr(training, 'training_type', None), 'code', '') or ''
    if training_type_code.lower() == 'preparation':
        hours_per_session = 3
    for date in theory_dates:
        consultation_sessions.append({
            'date': _format_date(date),
            'kind': 'Консультация',
            'hours': hours_per_session,
            'consultant_initials': consultant_short_name,
        })
    context['consultation_sessions'] = consultation_sessions
    context['total_consultation_hours'] = sum(s.get('hours', 0) for s in consultation_sessions)

    # === ЗАПИСИ ДНЕВНИКА ===
    context['diary_entries'] = training.get_diary_entries() if hasattr(training, 'get_diary_entries') else []

    # === ДАТЫ ДОКУМЕНТОВ ===
    today_str = _format_date(datetime.date.today())
    context['application_date'] = today_str
    context['order_date'] = today_str
    # exam_application_date = дата протокола (end_date)
    context['exam_application_date'] = _format_date(getattr(training, 'protocol_date', None) or getattr(training, 'end_date', None))

    # report_date = дата пробной работы (practical_date)
    practical_date_value = getattr(training, 'practical_date', None)
    context['report_date'] = _format_date(practical_date_value)

    # submission_date = следующий рабочий день после practical_date
    # protocol_date = следующий рабочий день после submission_date (= end_date)
    if practical_date_value:
        work_schedule = '5/2'
        schedule_start = None
        if training.employee:
            work_schedule = getattr(training.employee, 'work_schedule', None) or '5/2'
            schedule_start = getattr(training.employee, 'start_date', None) or getattr(training.employee, 'hire_date', None)
        # submission_date = practical_date + 1 рабочий день
        submission_date_value = training_schedule.next_workday(
            practical_date_value + datetime.timedelta(days=1),
            work_schedule=work_schedule,
            schedule_start=schedule_start
        )
        context['submission_date'] = _format_date(submission_date_value)
    else:
        context['submission_date'] = ''

    context['submission_number'] = ''

    # === ВРЕМЯ ===
    planned_hours_value = getattr(training, 'planned_hours', None)
    if planned_hours_value is None:
        program = getattr(training, 'program', None)
        program_hours = getattr(program, 'practical_work_hours', None) if program else None
        if program_hours is not None:
            planned_hours_value = program_hours
    context['time_norm_hours'] = str(planned_hours_value or '')
    context['actual_time_hours'] = str(getattr(training, 'actual_hours', '') or '')

    # === ИМЕНОВАННЫЕ РОЛИ ДЛЯ ШАБЛОНОВ ===
    def _role_context(person):
        ctx = _build_person_context(person)
        if not person:
            ctx = _mark_role_missing(ctx)
        return ctx

    instructor_ctx = _role_context(instructor_person)
    consultant_ctx = _role_context(consultant_person)
    chairman_ctx = _role_context(commission_chairman_person)
    director_ctx = chairman_ctx if commission_chairman_person else (
        instructor_ctx if training.instructor else consultant_ctx
    )
    if not director_ctx.get('is_missing'):
        if director_ctx.get('full_name_nominative'):
            director_ctx['short_name'] = get_initials_before_surname(
                director_ctx['full_name_nominative']
            )
        if director_ctx.get('full_name_genitive'):
            director_ctx['short_name_genitive'] = get_initials_before_surname(
                director_ctx['full_name_genitive']
            )
    training_supervisor_ctx = instructor_ctx if training.instructor else chairman_ctx
    responsible_person_person = training.responsible_person
    responsible_person_ctx = _role_context(responsible_person_person)

    context['director'] = director_ctx
    context['instructor'] = instructor_ctx
    context['theory_consultant'] = consultant_ctx
    context['consultant'] = consultant_ctx
    context['commission_chairman'] = chairman_ctx
    context['training_supervisor'] = training_supervisor_ctx
    context['responsible_person'] = responsible_person_ctx
    context['person'] = responsible_person_ctx
    context['theory_consultants'] = [consultant_ctx] if consultant_ctx.get('full_name_nominative') else []

    # === СПИСКИ ДЛЯ ЦИКЛОВ ===
    commission_members = [
        _build_person_context(member)
        for member in commission_members_people
    ] if commission_members_people else []
    context['commission_members'] = commission_members

    familiarization_list = []
    seen_entries = set()

    def _append_unique_context(role_ctx, role_key):
        if not role_ctx:
            return
        if not role_ctx.get('is_missing') and not role_ctx.get('full_name_nominative'):
            return
        if role_ctx.get('is_missing'):
            key = f"missing:{role_key}"
        else:
            key = (
                role_ctx.get('full_name_nominative', ''),
                role_ctx.get('position_nominative', ''),
            )
        if key in seen_entries:
            return
        seen_entries.add(key)
        familiarization_list.append(role_ctx)

    _append_unique_context(context.get('employee') or {}, 'employee')
    _append_unique_context(training_supervisor_ctx, 'training_supervisor')
    _append_unique_context(instructor_ctx, 'instructor')
    _append_unique_context(consultant_ctx, 'consultant')
    _append_unique_context(responsible_person_ctx, 'responsible_person')

    context['familiarization_list'] = familiarization_list

    # === КАНДИДАТЫ НА ЭКЗАМЕН ===
    exam_candidates = []
    if employee:
        theory_score_value = context.get('theory_score', '')
        exam_score_value = context.get('exam_score', '')
        practical_score_value = context.get('practical_score', '')
        # Получаем текстовые оценки (только слово, без цифры)
        theory_score_text = context.get('theory_score_word', _score_to_word(theory_score_value))
        exam_score_text = context.get('exam_score_word', _score_to_word(exam_score_value))
        practical_score_text = context.get('practical_score_word', _score_to_word(practical_score_value))
        exam_candidates.append({
            'full_name_nominative': context.get('employee', {}).get('full_name_nominative', ''),
            'birth_year': employee.date_of_birth.year if employee.date_of_birth else '',
            'education_level': employee.education_level or '',
            'profession': context.get('profession', {}).get('name_ru_nominative', ''),
            # Разряд в формате "3-й" вместо "3 (третий)"
            'rank': context.get('qualification_grade', {}).get('label_ru_short', ''),
            # Оценки: цифра для совместимости, текст для протокола
            'exam_score': exam_score_value,
            'exam_score_word': exam_score_text,
            'exam_score_text': exam_score_text,  # только текст для протокола
            'theory_score': theory_score_value,
            'theory_score_word': theory_score_text,
            'theory_score_text': theory_score_text,  # только текст для протокола
            'practical_score': practical_score_value,
            'practical_score_word': practical_score_text,
            'practical_score_text': practical_score_text,  # только текст для протокола
            'note': '',
        })
    context['exam_candidates'] = exam_candidates

    return context


def generate_training_document(
    training,
    template_path: str,
    document_name: str,
    user=None,
    custom_context: Optional[Dict[str, Any]] = None,
    use_vml: bool = True
) -> Optional[Dict[str, Any]]:
    """
    Универсальная функция генерации документов обучения.

    Args:
        training: Объект TrainingAssignment
        template_path: Путь к DOCX-шаблону
        document_name: Название типа документа (для имени файла)
        user: Пользователь, создающий документ (опционально)
        custom_context: Дополнительный контекст (опционально)
        use_vml: Использовать VML-замены (по умолчанию True)

    Returns:
        Optional[Dict]: {'content': BytesIO, 'filename': str} или None при ошибке
    """
    try:
        # Проверка существования шаблона
        if not os.path.exists(template_path):
            logger.error(f"Шаблон не найден: {template_path}")
            raise FileNotFoundError(f"Шаблон не найден: {template_path}")

        # Подготовка контекста
        context = prepare_training_context(training)

        # Добавление пользовательского контекста
        if custom_context:
            context.update(custom_context)

        logger.info(f"Контекст для {document_name} подготовлен: {len(context)} переменных")

        if use_vml:
            # Открываем шаблон напрямую и читаем как bytes
            with open(template_path, 'rb') as f:
                docx_bytes = f.read()
            try:
                vml_replacements = get_vml_replacements(training)
                logger.info(f"VML-замены подготовлены: {len(vml_replacements)} полей")
                result_bytes = replace_vml_text_in_docx(docx_bytes, vml_replacements)
                output = BytesIO(result_bytes)
            except Exception as e:
                logger.error(f"Ошибка при VML-заменах: {e}")
                raise
        else:
            template = DocxTemplate(template_path)
            template.render(context)
            output = BytesIO()
            template.save(output)
            output.seek(0)

        # Генерация имени файла
        employee = getattr(training, 'employee', None)
        employee_name = employee.full_name_nominative if employee else 'Без_сотрудника'
        safe_name = employee_name.replace(' ', '_')
        timestamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f"{document_name}_{safe_name}_{timestamp}.docx"

        logger.info(f"Документ '{document_name}' успешно сгенерирован: {filename}")

        return {
            'content': output,
            'filename': filename
        }

    except Exception as e:
        logger.error(f"Ошибка при генерации документа '{document_name}': {e}")
        import traceback
        logger.error(traceback.format_exc())
        return None


def get_template_path(template_name: str) -> str:
    """
    Получить абсолютный путь к шаблону документа обучения.

    Args:
        template_name: Логическое имя шаблона (например: 'application.docx')
                      Будет преобразовано в реальное имя файла через TEMPLATE_NAMES

    Returns:
        str: Абсолютный путь к шаблону
    """
    base_path = Path(settings.MEDIA_ROOT) / 'document_templates' / 'learning'
    # Используем маппинг для получения реального имени файла
    actual_name = TEMPLATE_NAMES.get(template_name, template_name)
    return str(base_path / actual_name)
