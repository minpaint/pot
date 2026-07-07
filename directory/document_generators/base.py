# directory/document_generators/base.py
"""
📄 Базовый модуль для генерации документов

Содержит общие функции для работы с шаблонами и контекстом.
"""
import os
import io
import logging
from typing import Dict, Any, Optional, Callable
import datetime
import traceback
from docxtpl import DocxTemplate
from django.conf import settings
from django.core.files.base import ContentFile

from directory.models.document_template import DocumentTemplate, GeneratedDocument
from directory.utils.declension import (
    decline_full_name, decline_phrase, get_initials_from_name, format_days, join_phrase_parts
)
from directory.utils.docx_vml import replace_vml_text_in_docx

# Настройка логирования
logger = logging.getLogger(__name__)

# Маппинг типов документов на человекочитаемые названия файлов
DOCUMENT_TYPE_NAMES = {
    'all_orders': 'Распоряжения',
    'knowledge_protocol': 'Протокол',
    'periodic_protocol': 'Протокол',
    'doc_familiarization': 'Лист ознакомления',
    'siz_card': 'Карточка СИЗ',
    'personal_ot_card': 'Личная карточка',
    'journal_example': 'Образец заполнения журнала инструктажей',
    'instruction_journal': 'Образец журнала инструктажей',
    'vvodny_journal_template': 'Образец журнала вводного инструктажа',
}

# Организационно-правовые формы для разбора названия
ORG_LEGAL_FORMS = [
    'Общество с ограниченной ответственностью',
    'Общество с дополнительной ответственностью',
    'Закрытое акционерное общество',
    'Открытое акционерное общество',
    'Акционерное общество',
    'Унитарное предприятие',
    'Частное унитарное предприятие',
    'Государственное унитарное предприятие',
    'Индивидуальный предприниматель',
]


def parse_organization_name(full_name: str) -> tuple:
    """
    Разбирает полное название организации на организационно-правовую форму и название.

    Например:
    'Общество с ограниченной ответственностью "Безопасность Плюс"'
    -> ('Общество с ограниченной ответственностью', '"Безопасность Плюс"')

    Returns:
        tuple: (legal_form, company_name)
    """
    if not full_name:
        return ('', '')

    name = full_name.strip()

    # Ищем организационно-правовую форму
    for legal_form in ORG_LEGAL_FORMS:
        if name.startswith(legal_form):
            # Нашли форму, остальное - название
            company_name = name[len(legal_form):].strip()
            # Если название не в кавычках - добавляем их
            if company_name and not company_name.startswith('"'):
                company_name = f'"{company_name}"'
            return (legal_form, company_name)

    # Не нашли известную форму - возвращаем всё как название
    return ('', full_name)


def get_document_template(document_type, employee=None) -> Optional[DocumentTemplate]:
    """
    Получает шаблон документа с учетом организации сотрудника.

    Порядок поиска:
    1. Если сотрудник принадлежит организации, ищется шаблон, привязанный к этой организации.
    2. Если не найден, ищется эталонный шаблон (is_default=True).
    3. Если ни один из вариантов не найден, возвращается None.

    Args:
        document_type (str): Код типа документа (например: 'siz_card', 'knowledge_protocol').
        employee (Employee, optional): Сотрудник, для которого выбирается шаблон.

    Returns:
        DocumentTemplate: Объект шаблона документа или None, если шаблон не найден.
    """
    # Получаем все активные шаблоны данного типа (теперь document_type это ForeignKey)
    templates = DocumentTemplate.objects.filter(
        document_type__code=document_type,
        is_active=True
    )

    # Если сотрудник принадлежит организации, ищем шаблон для этой организации
    if employee and employee.organization:
        org_template = templates.filter(organization=employee.organization).first()
        if org_template:
            logger.info(f"Найден шаблон для организации {employee.organization.short_name_ru}: {org_template.name}")
            return org_template

    # Если не найден шаблон для организации, ищем эталонный шаблон
    default_template = templates.filter(is_default=True).first()
    if default_template:
        logger.info(f"Найден эталонный шаблон: {default_template.name}")
        return default_template

    logger.error(f"Шаблон документа типа '{document_type}' не найден")
    return None


def prepare_employee_context(employee) -> Dict[str, Any]:
    """
    Подготавливает контекст с данными сотрудника для шаблона документа.
    Перешли с булева is_contractor на поле contract_type с возможными значениями
    'contractor', 'standard', 'part_time' и т.д.
    """
    # Получаем текущую дату в разных форматах
    now = datetime.datetime.now()
    date_str = now.strftime("%d.%m.%Y")
    day = now.strftime("%d")
    month = now.strftime("%m")
    year = now.strftime("%Y")
    year_short = now.strftime("%y")

    # Получаем тип договора
    contract_type = getattr(employee, 'contract_type', 'standard')
    # Для обратной совместимости оставляем флаг
    is_contractor = (contract_type == 'contractor')

    # Определяем, какое значение использовать для должности/работы
    position_name = ""
    if employee.position:
        if contract_type == 'contractor' and hasattr(employee.position, 'contract_work_name') and employee.position.contract_work_name:
            position_name = employee.position.contract_work_name
            logger.info(f"Используется наименование работы по договору подряда: {position_name}")
        else:
            position_name = employee.position.position_name
            logger.info(f"Используется должность: {position_name}")

    # Основной контекст данных сотрудника
    context = {
        'employee': employee,
        'contract_type': contract_type,    # добавлено
        'is_contractor': is_contractor,    # для совместимости, если шаблоны ещё используют

        # ФИО в разных падежах
        'fio_nominative': employee.full_name_nominative,
        'fio_genitive': decline_full_name(employee.full_name_nominative, 'gent'),
        'fio_dative': decline_full_name(employee.full_name_nominative, 'datv'),
        'fio_accusative': decline_full_name(employee.full_name_nominative, 'accs'),
        'fio_instrumental': decline_full_name(employee.full_name_nominative, 'ablt'),
        'fio_prepositional': decline_full_name(employee.full_name_nominative, 'loct'),

        # Сокращенное ФИО
        'fio_initials': get_initials_from_name(employee.full_name_nominative),

        # Должность/работа в разных падежах
        'position_nominative': position_name,
        'position_genitive': decline_phrase(position_name, 'gent'),
        'position_dative': decline_phrase(position_name, 'datv'),
        'position_accusative': decline_phrase(position_name, 'accs'),
        'position_instrumental': decline_phrase(position_name, 'ablt'),
        'position_prepositional': decline_phrase(position_name, 'loct'),

        # Подразделение и отдел
        'department': employee.department.name if employee.department else "",
        'department_genitive': decline_phrase(employee.department.name, 'gent') if employee.department else "",
        'department_dative': decline_phrase(employee.department.name, 'datv') if employee.department else "",

        'subdivision': employee.subdivision.name if employee.subdivision else "",
        'subdivision_genitive': decline_phrase(employee.subdivision.name, 'gent') if employee.subdivision else "",
        'subdivision_dative': decline_phrase(employee.subdivision.name, 'datv') if employee.subdivision else "",

        # Организация
        'organization_name': employee.organization.short_name_ru if employee.organization else "",
        'organization_name_genitive': decline_phrase(employee.organization.short_name_ru, 'gent') if employee.organization else "",
        'organization_name_dative': decline_phrase(employee.organization.short_name_ru, 'datv') if employee.organization else "",
        'organization_name_accusative': decline_phrase(employee.organization.short_name_ru, 'accs') if employee.organization else "",
        'organization_name_instrumental': decline_phrase(employee.organization.short_name_ru, 'ablt') if employee.organization else "",
        'organization_name_prepositional': decline_phrase(employee.organization.short_name_ru, 'loct') if employee.organization else "",

        'organization_full_name': employee.organization.full_name_ru if employee.organization else "",
        'organization_full_name_genitive': decline_phrase(employee.organization.full_name_ru, 'gent') if employee.organization else "",
        'organization_full_name_dative': decline_phrase(employee.organization.full_name_ru, 'datv') if employee.organization else "",
        'organization_full_name_accusative': decline_phrase(employee.organization.full_name_ru, 'accs') if employee.organization else "",
        'organization_full_name_instrumental': decline_phrase(employee.organization.full_name_ru, 'ablt') if employee.organization else "",
        'organization_full_name_prepositional': decline_phrase(employee.organization.full_name_ru, 'loct') if employee.organization else "",

        # Даты и номера документов
    }

    # Добавляем разбитое название организации (форма + название)
    if employee.organization:
        legal_form, company_name = parse_organization_name(employee.organization.full_name_ru)
        context.update({
            'organization_legal_form': legal_form,  # "Общество с ограниченной ответственностью"
            'organization_company_name': company_name,  # '"Безопасность Плюс"'
        })
    else:
        context.update({
            'organization_legal_form': '',
            'organization_company_name': '',
        })

    context.update({
        'current_date': date_str,
        'current_day': day,
        'current_month': month,
        'current_year': year,
        'current_year_short': year_short,

        'order_number': "",

        # Дополнительные поля
        'internship_duration': getattr(employee.position, 'internship_period_days', 2) if employee.position else 2,

        'location': employee.organization.location if employee.organization and hasattr(employee.organization, 'location') and employee.organization.location else "г. Минск",

        'employee_name_initials': get_initials_from_name(employee.full_name_nominative),
    })

    # Добавляем дату трудоустройства
    if employee.hire_date:
        hire_date_str = employee.hire_date.strftime("%d.%m.%Y")
        context['hire_date'] = hire_date_str
    else:
        context['hire_date'] = ""

    # Добавляем год рождения
    if employee.date_of_birth:
        context['year_of_birth'] = employee.date_of_birth.strftime('%Y')
    else:
        context['year_of_birth'] = ""

    # Добавляем вид работ по договору подряда (для личной карточки)
    if contract_type == 'contractor' and employee.position:
        context['GPD'] = getattr(employee.position, 'contract_work_name', '') or ""
    else:
        context['GPD'] = ""

    # Добавляем форматированную продолжительность стажировки
    internship_days = context.get('internship_duration', 2)

    # Учитываем стажировку при управлении служебным автомобилем (минимум 5 дней)
    drives_vehicle = employee.position and getattr(employee.position, 'drives_company_vehicle', False)
    if drives_vehicle and contract_type != 'contractor':
        internship_days = max(internship_days, 5)
        context['internship_duration'] = internship_days

    context['internship_duration_formatted'] = format_days(internship_days)

    # Добавляем период стажировки "с ДД.ММ.ГГГГ по ДД.ММ.ГГГГ"
    # Отнимаем 1 день, т.к. стажировка включает первый день
    # Для договора подряда стажировка не нужна
    if employee.hire_date and internship_days > 0 and contract_type != 'contractor':
        internship_start = employee.hire_date
        internship_end = internship_start + datetime.timedelta(days=internship_days - 1)
        context['internship_period'] = f"с {internship_start.strftime('%d.%m.%Y')} по {internship_end.strftime('%d.%m.%Y')}"
        context['has_internship'] = True
    else:
        context['internship_period'] = ""
        context['has_internship'] = False

    # Добавляем номера инструкций по охране труда
    # Для договора подряда - специальные инструкции для вида работ
    # Для остальных договоров - стандартные инструкции для должности + управление автомобилем
    if employee.position:
        if contract_type == 'contractor':
            # Для подрядчиков сначала берём спец. инструкции, иначе падаем обратно на общие
            contract_instr = getattr(employee.position, 'contract_safety_instructions', '') or ""
            if contract_instr:
                context['instruction_numbers'] = contract_instr
            else:
                from directory.utils.vehicle_utils import combine_instructions
                context['instruction_numbers'] = combine_instructions(employee)
        else:
            # Используем функцию объединения инструкций (основные + авто)
            from directory.utils.vehicle_utils import combine_instructions
            context['instruction_numbers'] = combine_instructions(employee)
    else:
        context['instruction_numbers'] = ""

    # Дублируем ключ для совместимости со старыми шаблонами
    context['instructions'] = context['instruction_numbers']
    # Удобный вариант в виде списка
    context['instruction_numbers_list'] = [
        instr.strip() for instr in context['instruction_numbers'].split(',')
        if instr and instr.strip()
    ]

    # Добавляем переменную driving_auto для отображения в шаблонах
    # Используется для заголовков и текста "(управление служебным автомобилем)"
    from directory.utils.vehicle_utils import needs_vehicle_training
    if needs_vehicle_training(employee):
        context['driving_auto'] = ' (управление служебным автомобилем)'
    else:
        context['driving_auto'] = ''


    # Умные переменные - готовые строки без лишних пробелов
    # Полная строка "должность отдела подразделения" в нужном падеже.
    # join_phrase_parts убирает дублирование на стыке частей:
    # «начальника склада» + «склада (аг Сеница)» -> «начальника склада (аг Сеница)»
    context['position_full_dative'] = join_phrase_parts(
        context['position_dative'],
        context['department_genitive'],
        context['subdivision_genitive'],
    )

    context['position_full_genitive'] = join_phrase_parts(
        context['position_genitive'],
        context['department_genitive'],
        context['subdivision_genitive'],
    )

    context['position_full_accusative'] = join_phrase_parts(
        context['position_accusative'],
        context['department_genitive'],
        context['subdivision_genitive'],
    )

    # Подписание
    from directory.views.documents.utils import get_document_signer
    signer, level, found = get_document_signer(employee)
    if found and signer:
        context.update({
            'director_position': signer.position.position_name if signer.position else "Директор",
            'director_name': signer.full_name_nominative,
            'director_name_initials': get_initials_from_name(signer.full_name_nominative),
            'director_level': level,
        })
    else:
        context.update({
            'director_position': "Директор",
            'director_name': "Иванов Иван Иванович",
            'director_name_initials': "И.И. Иванов",
        })

    return context

def generate_docx_from_template(template: DocumentTemplate, context: Dict[str, Any],
                                employee, user=None, post_processor: Optional[Callable] = None,
                                raise_on_error: bool = False,
                                vml_replacements: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
    """
    Генерирует документ DOCX на основе шаблона и контекста данных.
    Не сохраняет в базу данных, возвращает содержимое файла.

    Args:
        template (DocumentTemplate): Объект шаблона документа
        context (Dict[str, Any]): Словарь с данными для заполнения шаблона
        employee: Объект модели Employee
        user: Пользователь, создающий документ (опционально)
        post_processor: Функция пост-обработки документа (например, для обработки таблиц)
        vml_replacements: Словарь для замены текста в VML WordArt по имени shape
    Returns:
        Optional[Dict]: Словарь с 'content' (байты файла) и 'filename' или None при ошибке
    """
    try:
        template_path = template.template_file.path
        logger.info(f"Используется шаблон: {template.name} (ID: {template.id}), путь: {template_path}")

        if not os.path.exists(template_path):
            logger.error(f"Файл шаблона не найден: {template_path}")
            raise FileNotFoundError(f"Файл шаблона не найден: {template_path}")

        file_size = os.path.getsize(template_path)
        if file_size == 0:
            logger.error(f"Файл шаблона пуст: {template_path}")
            raise ValueError(f"Файл шаблона имеет нулевой размер: {template_path}")

        logger.info(f"Файл шаблона готов к обработке: {template_path}, размер: {file_size} байт")

        try:
            doc = DocxTemplate(template_path)
            logger.info("Шаблон успешно загружен в DocxTemplate")
        except Exception as e:
            logger.error(f"Ошибка при загрузке шаблона в DocxTemplate: {str(e)}")
            raise ValueError(f"Ошибка при загрузке шаблона в DocxTemplate: {str(e)}")

        try:
            # Удаляем объект employee из контекста перед рендерингом
            context_to_render = context.copy()
            context_to_render.pop('employee', None)
            doc.render(context_to_render)
            logger.info("Шаблон успешно заполнен данными")

            # Применяем пост-обработчик, если он указан
            if post_processor and callable(post_processor):
                try:
                    logger.info("Применение пост-обработчика к документу")
                    doc = post_processor(doc, context_to_render)
                    logger.info("Пост-обработчик успешно применен")
                except Exception as e:
                    logger.error(f"Ошибка при применении пост-обработчика: {str(e)}")
                    logger.error(traceback.format_exc())

        except Exception as e:
            logger.error(f"Ошибка при заполнении шаблона данными: {str(e)}")
            logger.error(f"Контекст при ошибке: {context_to_render.keys()}")
            raise ValueError(f"Ошибка при заполнении шаблона данными: {str(e)}")

        # Формируем человекочитаемое имя файла
        # document_type теперь ForeignKey, получаем код через .code
        doc_type_code = template.document_type.code if template.document_type else 'document'
        doc_type_name = DOCUMENT_TYPE_NAMES.get(doc_type_code, doc_type_code)
        employee_initials = get_initials_from_name(employee.full_name_nominative)
        filename = f"{doc_type_name}_{employee_initials}.docx"
        logger.info(f"Имя файла: {filename}")

        docx_buffer = io.BytesIO()
        doc.save(docx_buffer)
        docx_buffer.seek(0)

        file_content = docx_buffer.getvalue()
        if vml_replacements:
            file_content = replace_vml_text_in_docx(file_content, vml_replacements)
        if len(file_content) == 0:
            logger.error(f"Создан пустой DOCX файл для {filename}")
            raise ValueError("Создан пустой DOCX файл")

        logger.info(f"Создан DOCX файл {filename}, размер: {len(file_content)} байт")

        return {
            'content': file_content,
            'filename': filename,
        }

    except Exception as e:
        logger.error(f"Ошибка при генерации документа: {str(e)}")
        logger.error(traceback.format_exc())
        if raise_on_error:
            raise
        return None
