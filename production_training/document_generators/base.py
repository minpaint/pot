# -*- coding: utf-8 -*-
"""
📄 Базовый модуль для генерации документов обучения на производстве

Содержит общие функции для работы с шаблонами ProductionTraining.
"""
import os
import logging
import datetime
from pathlib import Path
from typing import Dict, Any, Optional
from io import BytesIO

from docxtpl import DocxTemplate
from django.conf import settings
from django.core.files.base import ContentFile

from directory.utils.docx_vml import replace_vml_text_in_docx
from directory.utils.declension import decline_full_name, get_initials_before_surname
from production_training.document_templates.field_mapping import get_vml_replacements

logger = logging.getLogger(__name__)


# ============================================================================
# МАППИНГ ИМЁН ШАБЛОНОВ
# ============================================================================

TEMPLATE_NAMES = {
    'application.docx': '1.Заявление.docx',
    'order.docx': '2. Приказ о назначении обучения.docx',
    'theory_card.docx': '3. Карточка теория.docx',
    'trial_application.docx': '5. Завление на квалификационный экзамен.docx',
    'trial_conclusion.docx': '6. Заключение на пробную работу.docx',
    'presentation.docx': '7. Представление на квалификационную работу.docx',
    'protocol.docx': '8. Протокол квалификационной комиссии.docx',
    # Дневники выбираются по типу обучения в ProductionTraining.get_diary_template_path()
    'diary_podgotovka_voditel_pogruzchika.docx': '4.1.diary_podgotovka_voditel_pogruzchika.docx',
    'diary_perepodgotovka_voditel_pogruzchika.docx': '4.diary_perepodgotovka_voditel_pogruzchika.docx',
}


def prepare_training_context(training) -> Dict[str, Any]:
    """
    Подготавливает базовый контекст для генерации документов обучения.

    Args:
        training: Объект ProductionTraining

    Returns:
        Dict[str, Any]: Контекст с данными обучения
    """
    context = {}

    # === ОРГАНИЗАЦИЯ ===
    if training.organization:
        context['organization_full_name_ru'] = training.organization.full_name_ru
        context['organization_short_name_ru'] = training.organization.short_name_ru
        context['organization_full_name_by'] = training.organization.full_name_by
        context['organization_short_name_by'] = training.organization.short_name_by
        context['organization_location'] = getattr(training.organization, 'location', 'г. Минск')

    # === СОТРУДНИК ===
    if training.employee:
        fio = training.employee.full_name_nominative
        fio_by = training.employee.full_name_by or fio

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

        if training.employee.education_level:
            context['education_level'] = training.employee.education_level
            context['education_level_ru'] = training.employee.education_level
            context['education_level_by'] = training.employee.education_level

        context['prior_qualification'] = training.employee.prior_qualification
        context['qualification_document_number'] = training.employee.qualification_document_number
        context['qualification_document_date'] = training.employee.qualification_document_date
        if training.employee.qualification_document_date:
            context['qualification_document_date_formatted'] = (
                training.employee.qualification_document_date.strftime('%d.%m.%Y')
            )

    # === ПРОФЕССИЯ ОБУЧЕНИЯ ===
    if training.profession:
        context['profession_nominative_ru'] = training.profession.name_ru_nominative
        context['profession_genitive_ru'] = training.profession.name_ru_genitive
        context['profession_nominative_by'] = training.profession.name_by_nominative
        context['profession_genitive_by'] = training.profession.name_by_genitive

    # === ТИП ОБУЧЕНИЯ ===
    if training.training_type:
        context['training_type_ru'] = training.training_type.name_ru
        context['training_type_by'] = training.training_type.name_by
        context['training_type_code'] = training.training_type.code

    # === РАЗРЯД ===
    if training.qualification_grade:
        context['qualification_grade_number'] = training.qualification_grade.grade_number
        context['qualification_grade_ru'] = training.qualification_grade.label_ru
        context['qualification_grade_by'] = training.qualification_grade.label_by

    # === ПРОГРАММА ===
    if training.program:
        context['program_name'] = training.program.name
        context['program_total_hours'] = training.program.get_total_hours()
        context['program_theory_hours'] = training.program.get_theory_hours()
        context['program_practice_hours'] = training.program.get_practice_hours()

    # === ДАТЫ ===
    context['start_date'] = training.start_date
    context['end_date'] = training.end_date
    context['exam_date'] = training.exam_date
    context['practical_date'] = training.practical_date
    context['protocol_date'] = training.protocol_date
    context['issue_date'] = training.issue_date

    # Форматированные даты
    if training.start_date:
        context['start_date_formatted'] = training.start_date.strftime('%d.%m.%Y')
    if training.end_date:
        context['end_date_formatted'] = training.end_date.strftime('%d.%m.%Y')
    if training.exam_date:
        context['exam_date_formatted'] = training.get_exam_date_formatted('ru')
        context['exam_date_formatted_by'] = training.get_exam_date_formatted('by')
    if training.practical_date:
        context['practical_date_formatted'] = training.get_practical_date_formatted('ru')
        context['practical_date_formatted_by'] = training.get_practical_date_formatted('by')

    # Период обучения
    context['period_str_ru'] = training.get_period_str('ru')
    context['period_str_by'] = training.get_period_str('by')

    # === РОЛИ (с падежами и инициалами) ===
    # Инструктор
    if training.instructor:
        instructor_fio = training.instructor.full_name_nominative
        context['instructor_name'] = instructor_fio
        context['instructor_name_genitive'] = decline_full_name(instructor_fio, 'gent')
        context['instructor_name_dative'] = decline_full_name(instructor_fio, 'datv')
        context['instructor_initials'] = get_initials_before_surname(instructor_fio)
    else:
        context['instructor_name'] = ''
        context['instructor_name_genitive'] = ''
        context['instructor_name_dative'] = ''
        context['instructor_initials'] = ''

    # Консультант по теории
    if training.theory_consultant:
        consultant_fio = training.theory_consultant.full_name_nominative
        context['consultant_name'] = consultant_fio
        context['consultant_name_genitive'] = decline_full_name(consultant_fio, 'gent')
        context['consultant_name_dative'] = decline_full_name(consultant_fio, 'datv')
        context['consultant_initials'] = get_initials_before_surname(consultant_fio)
    else:
        context['consultant_name'] = ''
        context['consultant_name_genitive'] = ''
        context['consultant_name_dative'] = ''
        context['consultant_initials'] = ''

    # Председатель комиссии
    if training.commission_chairman:
        chairman_fio = training.commission_chairman.full_name_nominative
        context['chairman_name'] = chairman_fio
        context['chairman_name_genitive'] = decline_full_name(chairman_fio, 'gent')
        context['chairman_initials'] = get_initials_before_surname(chairman_fio)
    else:
        context['chairman_name'] = ''
        context['chairman_name_genitive'] = ''
        context['chairman_initials'] = ''

    # Члены комиссии
    context['commission_members'] = training.get_commission_members_list()
    # Список членов комиссии с инициалами
    if training.commission_members.exists():
        members_initials = [
            get_initials_before_surname(m.full_name_nominative)
            for m in training.commission_members.all()
        ]
        context['commission_members_initials'] = ', '.join(members_initials)
    else:
        context['commission_members_initials'] = ''

    # === КОМИССИЯ ===
    if training.commission:
        context['commission_name'] = str(training.commission)

    # === ОЦЕНКИ ===
    context['exam_score'] = training.exam_score or ''
    context['practical_score'] = training.practical_score or ''
    context['practical_work_topic'] = training.practical_work_topic or ''

    # === ДОКУМЕНТЫ ===
    context['registration_number'] = training.registration_number or ''
    context['protocol_number'] = training.protocol_number or ''

    # === МЕСТО ПРОВЕДЕНИЯ ===
    context['training_city_ru'] = training.training_city_ru or ''
    context['training_city_by'] = training.training_city_by or ''

    # === ДОПОЛНИТЕЛЬНЫЕ ДАННЫЕ ===
    context['prior_qualification'] = training.prior_qualification or ''
    context['workplace'] = training.workplace or ''

    # === ТЕКУЩАЯ ПРОФЕССИЯ НА ПРЕДПРИЯТИИ ===
    if training.current_position:
        context['current_position_name'] = training.current_position.name

    # === ДАТЫ ДЛЯ ТЕОРИИ ===
    theory_dates = training.get_theory_dates()
    context['theory_dates'] = theory_dates
    if len(theory_dates) >= 2:
        context['theory_date_1'] = theory_dates[0].strftime('%d.%m.%Y')
        context['theory_date_2'] = theory_dates[1].strftime('%d.%m.%Y')

    # === ЗАПИСИ ДНЕВНИКА ===
    context['diary_entries'] = training.get_diary_entries()

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
        training: Объект ProductionTraining
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

        # Проверка: есть ли в шаблоне Jinja2-разметка
        # Для документов обучения используем только VML-замены
        # docxtpl не используется, так как шаблоны созданы для VML

        # Открываем шаблон напрямую и читаем как bytes
        with open(template_path, 'rb') as f:
            docx_bytes = f.read()

        # VML-замены (основной способ заполнения документов обучения)
        if use_vml:
            try:
                vml_replacements = get_vml_replacements(training)
                logger.info(f"VML-замены подготовлены: {len(vml_replacements)} полей")
                # replace_vml_text_in_docx принимает bytes и возвращает bytes
                result_bytes = replace_vml_text_in_docx(docx_bytes, vml_replacements)
                # Преобразуем обратно в BytesIO для совместимости
                output = BytesIO(result_bytes)
            except Exception as e:
                logger.error(f"Ошибка при VML-заменах: {e}")
                raise
        else:
            output = BytesIO(docx_bytes)

        # Генерация имени файла
        employee_name = training.employee.full_name_nominative if training.employee else 'Без_сотрудника'
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
