# -*- coding: utf-8 -*-
"""
📄 Генераторы всех документов обучения на производстве

Содержит функции генерации для всех типов документов:
- Заявление (application)
- Приказ (order)
- Карточка теории (theory_card)
- Представление (presentation)
- Протокол комиссии (protocol)
- Заявление на пробную работу (trial_application)
- Заключение по пробной работе (trial_conclusion)
- Дневник обучения (diary)
"""
import logging
from typing import Dict, Any, Optional

from .base import generate_training_document, get_template_path

logger = logging.getLogger(__name__)


# ============================================================================
# ЗАЯВЛЕНИЕ (application.docx)
# ============================================================================

def generate_application(training, user=None, custom_context: Optional[Dict[str, Any]] = None):
    """
    Генерирует заявление сотрудника на обучение.

    Args:
        training: Объект ProductionTraining
        user: Пользователь (опционально)
        custom_context: Дополнительный контекст (опционально)

    Returns:
        Dict или None
    """
    template_path = get_template_path('application.docx')
    return generate_training_document(
        training=training,
        template_path=template_path,
        document_name='Заявление',
        user=user,
        custom_context=custom_context,
        use_vml=True
    )


# ============================================================================
# ПРИКАЗ НА ОБУЧЕНИЕ (order.docx)
# ============================================================================

def generate_order(training, user=None, custom_context: Optional[Dict[str, Any]] = None):
    """
    Генерирует приказ на обучение.

    Args:
        training: Объект ProductionTraining
        user: Пользователь (опционально)
        custom_context: Дополнительный контекст (опционально)

    Returns:
        Dict или None
    """
    template_path = get_template_path('order.docx')

    # Добавляем специфичный контекст для приказа
    context = custom_context or {}
    if 'order_number' not in context and training.registration_number:
        context['order_number'] = training.registration_number

    return generate_training_document(
        training=training,
        template_path=template_path,
        document_name='Приказ',
        user=user,
        custom_context=context,
        use_vml=True
    )


# ============================================================================
# КАРТОЧКА ТЕОРИИ (theory_card.docx)
# ============================================================================

def generate_theory_card(training, user=None, custom_context: Optional[Dict[str, Any]] = None):
    """
    Генерирует карточку теоретического обучения.

    Args:
        training: Объект ProductionTraining
        user: Пользователь (опционально)
        custom_context: Дополнительный контекст (опционально)

    Returns:
        Dict или None
    """
    template_path = get_template_path('theory_card.docx')

    # Добавляем даты теоретических занятий
    context = custom_context or {}
    theory_dates = training.get_theory_dates()
    if theory_dates:
        context['theory_dates'] = theory_dates

    return generate_training_document(
        training=training,
        template_path=template_path,
        document_name='Карточка_теории',
        user=user,
        custom_context=context,
        use_vml=True
    )


# ============================================================================
# ПРЕДСТАВЛЕНИЕ (presentation.docx)
# ============================================================================

def generate_presentation(training, user=None, custom_context: Optional[Dict[str, Any]] = None):
    """
    Генерирует представление на сотрудника.

    Args:
        training: Объект ProductionTraining
        user: Пользователь (опционально)
        custom_context: Дополнительный контекст (опционально)

    Returns:
        Dict или None
    """
    template_path = get_template_path('presentation.docx')
    return generate_training_document(
        training=training,
        template_path=template_path,
        document_name='Представление',
        user=user,
        custom_context=custom_context,
        use_vml=True
    )


# ============================================================================
# ПРОТОКОЛ КОМИССИИ (protocol.docx)
# ============================================================================

def generate_protocol(training, user=None, custom_context: Optional[Dict[str, Any]] = None):
    """
    Генерирует протокол квалификационной комиссии.

    Args:
        training: Объект ProductionTraining
        user: Пользователь (опционально)
        custom_context: Дополнительный контекст (опционально)

    Returns:
        Dict или None
    """
    template_path = get_template_path('protocol.docx')

    # Добавляем специфичный контекст для протокола
    context = custom_context or {}

    # Номер и дата протокола
    if 'protocol_number' not in context and training.protocol_number:
        context['protocol_number'] = training.protocol_number
    if 'protocol_date' not in context and training.protocol_date:
        context['protocol_date'] = training.protocol_date.strftime('%d.%m.%Y')

    # Состав комиссии
    if training.commission:
        commission = training.commission
        members = commission.members.select_related('employee').all()

        # Председатель
        chairman = members.filter(role='chairman').first()
        if chairman:
            context['commission_chairman_name'] = chairman.employee.full_name_nominative
            if chairman.employee.position:
                context['commission_chairman_position'] = chairman.employee.position.name

        # Члены комиссии
        regular_members = members.filter(role='member')
        context['commission_members_list'] = [
            {
                'name': m.employee.full_name_nominative,
                'position': m.employee.position.name if m.employee.position else ''
            }
            for m in regular_members
        ]

    return generate_training_document(
        training=training,
        template_path=template_path,
        document_name='Протокол',
        user=user,
        custom_context=context,
        use_vml=True
    )


# ============================================================================
# ЗАЯВЛЕНИЕ НА ПРОБНУЮ РАБОТУ (trial_application.docx)
# ============================================================================

def generate_trial_application(training, user=None, custom_context: Optional[Dict[str, Any]] = None):
    """
    Генерирует заявление на допуск к пробной работе.

    Args:
        training: Объект ProductionTraining
        user: Пользователь (опционально)
        custom_context: Дополнительный контекст (опционально)

    Returns:
        Dict или None
    """
    template_path = get_template_path('trial_application.docx')

    # Добавляем дату пробной работы
    context = custom_context or {}
    if 'practical_date' not in context and training.practical_date:
        context['practical_date'] = training.practical_date.strftime('%d.%m.%Y')
    if 'practical_work_topic' not in context and training.practical_work_topic:
        context['practical_work_topic'] = training.practical_work_topic

    return generate_training_document(
        training=training,
        template_path=template_path,
        document_name='Заявление_на_пробную_работу',
        user=user,
        custom_context=context,
        use_vml=True
    )


# ============================================================================
# ЗАКЛЮЧЕНИЕ ПО ПРОБНОЙ РАБОТЕ (trial_conclusion.docx)
# ============================================================================

def generate_trial_conclusion(training, user=None, custom_context: Optional[Dict[str, Any]] = None):
    """
    Генерирует заключение по пробной работе.

    Args:
        training: Объект ProductionTraining
        user: Пользователь (опционально)
        custom_context: Дополнительный контекст (опционально)

    Returns:
        Dict или None
    """
    template_path = get_template_path('trial_conclusion.docx')

    # Добавляем результаты пробной работы
    context = custom_context or {}
    if 'practical_score' not in context and training.practical_score:
        context['practical_score'] = training.practical_score
    if 'practical_work_topic' not in context and training.practical_work_topic:
        context['practical_work_topic'] = training.practical_work_topic

    return generate_training_document(
        training=training,
        template_path=template_path,
        document_name='Заключение_пробная_работа',
        user=user,
        custom_context=context,
        use_vml=True
    )


# ============================================================================
# ДНЕВНИК ОБУЧЕНИЯ (diary_podgotovka/diary_perepodgotovka)
# ============================================================================

def generate_diary(training, user=None, custom_context: Optional[Dict[str, Any]] = None):
    """
    Генерирует дневник обучения (подготовка или переподготовка).

    Выбор шаблона происходит автоматически на основе типа обучения:
    - preparation → diary_podgotovka_voditel_pogruzchika.docx
    - retraining → diary_perepodgotovka_voditel_pogruzchika.docx

    Args:
        training: Объект ProductionTraining
        user: Пользователь (опционально)
        custom_context: Дополнительный контекст (опционально)

    Returns:
        Dict или None
    """
    # Получаем путь к шаблону дневника из модели
    template_path = training.get_diary_template_path()

    if not template_path:
        logger.error(f"Не найден шаблон дневника для обучения {training.id}")
        return None

    # Добавляем записи дневника
    context = custom_context or {}
    diary_entries = training.get_diary_entries()
    context['diary_entries'] = diary_entries

    # Информация о программе обучения
    if training.program:
        context['program_sections'] = training.program.get_sections()

    return generate_training_document(
        training=training,
        template_path=template_path,
        document_name='Дневник',
        user=user,
        custom_context=context,
        use_vml=True
    )


# ============================================================================
# ГЕНЕРАЦИЯ ВСЕХ ДОКУМЕНТОВ
# ============================================================================

def generate_all_training_documents(training, user=None):
    """
    Генерирует все документы для обучения.

    Args:
        training: Объект ProductionTraining
        user: Пользователь (опционально)

    Returns:
        Dict[str, Dict]: Словарь с результатами генерации
                         {'application': {...}, 'order': {...}, ...}
    """
    results = {}

    generators = {
        'application': generate_application,
        'order': generate_order,
        'theory_card': generate_theory_card,
        'presentation': generate_presentation,
        'protocol': generate_protocol,
        'trial_application': generate_trial_application,
        'trial_conclusion': generate_trial_conclusion,
        'diary': generate_diary,
    }

    for doc_type, generator_func in generators.items():
        try:
            result = generator_func(training, user)
            if result:
                results[doc_type] = result
                logger.info(f"✅ {doc_type}: {result['filename']}")
            else:
                results[doc_type] = None
                logger.warning(f"❌ {doc_type}: не сгенерирован")
        except Exception as e:
            logger.error(f"❌ {doc_type}: ошибка - {e}")
            results[doc_type] = None

    return results
