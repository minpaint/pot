"""
📧 Утилиты для сбора получателей email-рассылок.

Этот модуль реализует трёхуровневую систему сбора получателей:
1. SubdivisionEmail - email подразделения
2. Employee.email - email ответственных за охрану труда
3. EmailSettings.recipient_emails - общие email организации

Все источники работают параллельно, результаты объединяются без дубликатов.
"""
import logging
from typing import List, Optional, Set, Dict

logger = logging.getLogger(__name__)


def collect_recipients_for_subdivision(
    subdivision: Optional['StructuralSubdivision'],
    organization: 'Organization',
    include_subdivision_emails: bool = True,
    include_responsible_employees: bool = True,
    include_organization_emails: bool = True,
    notification_type: str = 'general'
) -> List[str]:
    """
    Собирает всех получателей email для подразделения из трёх источников.

    Логика объединения (БЕЗ приоритетов):
    - Все три источника работают параллельно
    - Результаты объединяются через set() для удаления дубликатов
    - Если один источник не работает, используются остальные (fail-safe)

    Источники (включаются по флагам):
    1. SubdivisionEmail - email, настроенные для конкретного подразделения
    2. Employee.email - сотрудники с должностью is_responsible_for_safety=True
    3. EmailSettings - получатели из настроек организации (зависит от notification_type)

    Args:
        subdivision: Структурное подразделение (может быть None)
        organization: Организация (обязательно)
        include_subdivision_emails: Включить источник 1 (SubdivisionEmail)
        include_responsible_employees: Включить источник 2 (Employee.email)
        include_organization_emails: Включить источник 3 (EmailSettings)
        notification_type: Тип уведомления ('general', 'instruction_journal')
            - 'general': общие уведомления (медосмотры) - использует recipient_emails
            - 'instruction_journal': журналы инструктажей - использует instruction_journal_recipients

    Returns:
        list[str]: Список уникальных email-адресов (без дубликатов)

    Examples:
        >>> # Полный сбор для общих уведомлений
        >>> collect_recipients_for_subdivision(subdivision, organization)
        ['engineer@company.com', 'ivanov@company.com', 'hr@company.com']

        >>> # Журналы инструктажей (специализированные получатели)
        >>> collect_recipients_for_subdivision(
        ...     subdivision, organization,
        ...     notification_type='instruction_journal'
        ... )
        ['ot.engineer@company.com', 'ivanov@company.com']

        >>> # Только email организации
        >>> collect_recipients_for_subdivision(
        ...     subdivision, organization,
        ...     include_subdivision_emails=False,
        ...     include_responsible_employees=False
        ... )
        ['hr@company.com', 'director@company.com']

    Notes:
        - Источники 1 и 2 работают только если subdivision != None
        - Источник 3 работает всегда (не зависит от подразделения)
        - Пустые email ('', None) автоматически исключаются
        - Отключенные записи (is_active=False) исключаются
        - Уволенные сотрудники (status='fired') исключаются
    """
    from directory.models import Employee

    recipients: Set[str] = set()  # Set для автоматического удаления дубликатов
    subdivision_name = subdivision.name if subdivision else "без подразделения"

    logger.info(
        f"🔍 Начинаем сбор получателей для '{subdivision_name}' "
        f"(организация: {organization.short_name_ru})"
    )

    # =================================================================
    # ИСТОЧНИК 1: Email подразделения (SubdivisionEmail)
    # =================================================================
    if include_subdivision_emails and subdivision:
        try:
            # Получаем активные email подразделения
            subdivision_emails_qs = subdivision.notification_emails.filter(
                is_active=True
            ).values_list('email', flat=True)

            subdivision_emails = list(subdivision_emails_qs)
            count = len(subdivision_emails)

            if count > 0:
                # Очищаем и добавляем email
                cleaned_emails = _clean_email_list(subdivision_emails)
                recipients.update(cleaned_emails)

                logger.info(
                    f"✅ [Источник 1: SubdivisionEmail] Подразделение '{subdivision.name}': "
                    f"найдено {count} активных email"
                )
                logger.debug(f"   Адреса: {', '.join(cleaned_emails)}")
            else:
                logger.debug(
                    f"ℹ️  [Источник 1: SubdivisionEmail] Подразделение '{subdivision.name}': "
                    f"email не настроены"
                )

        except Exception as e:
            logger.warning(
                f"⚠️ [Источник 1: SubdivisionEmail] Ошибка получения email для '{subdivision.name}': {e}",
                exc_info=True
            )

    elif include_subdivision_emails and not subdivision:
        logger.debug(
            "⏩  [Источник 1: SubdivisionEmail] Пропущен: subdivision=None"
        )

    # =================================================================
    # ИСТОЧНИК 2: Email ответственных за ОТ (Employee.email)
    # =================================================================
    if include_responsible_employees and subdivision:
        try:
            # Получаем активных ответственных за ОТ с email
            responsible_employees_qs = Employee.objects.active_for_operations().filter(
                subdivision=subdivision,
                position__is_responsible_for_safety=True,  # Флаг на должности
                email__isnull=False
            ).exclude(
                email=''  # Исключаем пустые email
            ).values_list('email', 'full_name_nominative')

            responsible_data = list(responsible_employees_qs)
            count = len(responsible_data)

            if count > 0:
                # Извлекаем только email и очищаем
                responsible_emails = [email for email, name in responsible_data]
                cleaned_emails = _clean_email_list(responsible_emails)
                recipients.update(cleaned_emails)

                logger.info(
                    f"✅ [Источник 2: Employee] Ответственные за ОТ в '{subdivision.name}': "
                    f"найдено {count} сотрудников с email"
                )

                # Логируем имена для отладки
                for email, name in responsible_data:
                    logger.debug(f"   • {name}: {email}")
            else:
                logger.debug(
                    f"ℹ️  [Источник 2: Employee] Ответственные за ОТ в '{subdivision.name}': "
                    f"не найдены или email не заполнены"
                )

        except Exception as e:
            logger.warning(
                f"⚠️ [Источник 2: Employee] Ошибка получения ответственных за ОТ для '{subdivision.name}': {e}",
                exc_info=True
            )

    elif include_responsible_employees and not subdivision:
        logger.debug(
            "⏩  [Источник 2: Employee] Пропущен: subdivision=None"
        )

    # =================================================================
    # ИСТОЧНИК 3: Email организации (EmailSettings)
    # =================================================================
    if include_organization_emails:
        try:
            # Получаем настройки email организации
            email_settings = organization.email_settings

            # Проверяем, активны ли настройки
            if email_settings.is_active:
                # Выбираем метод получения получателей в зависимости от типа уведомления
                if notification_type == 'instruction_journal':
                    org_emails = email_settings.get_instruction_journal_recipients()
                    source_name = "EmailSettings (журналы инструктажей)"
                else:
                    org_emails = email_settings.get_recipient_list()
                    source_name = "EmailSettings (общие)"

                count = len(org_emails)

                if count > 0:
                    # Очищаем и добавляем email
                    cleaned_emails = _clean_email_list(org_emails)
                    recipients.update(cleaned_emails)

                    logger.info(
                        f"✅ [Источник 3: {source_name}] Организация '{organization.short_name_ru}': "
                        f"найдено {count} email"
                    )
                    logger.debug(f"   Адреса: {', '.join(cleaned_emails)}")
                else:
                    logger.debug(
                        f"ℹ️  [Источник 3: {source_name}] Организация '{organization.short_name_ru}': "
                        f"список получателей пуст"
                    )
            else:
                logger.warning(
                    f"⚠️ [Источник 3: EmailSettings] EmailSettings для '{organization.short_name_ru}' "
                    f"отключены (is_active=False)"
                )

        except organization._meta.model.email_settings.RelatedObjectDoesNotExist:
            logger.warning(
                f"⚠️ [Источник 3: EmailSettings] EmailSettings не существует для организации "
                f"'{organization.short_name_ru}'. Создайте настройки в админке."
            )
        except Exception as e:
            logger.error(
                f"❌ [Источник 3: EmailSettings] Неожиданная ошибка при получении настроек "
                f"для '{organization.short_name_ru}': {e}",
                exc_info=True
            )

    # =================================================================
    # ИТОГОВАЯ СТАТИСТИКА
    # =================================================================
    total_count = len(recipients)

    if total_count > 0:
        logger.info(
            f"✅ ИТОГО для '{subdivision_name}': {total_count} уникальных получателей"
        )
        logger.debug(f"   Итоговый список: {', '.join(sorted(recipients))}")
    else:
        logger.warning(
            f"⚠️ ВНИМАНИЕ: Для '{subdivision_name}' не найдено ни одного получателя! "
            f"Проверьте настройки:\n"
            f"   1. SubdivisionEmail (админка → Структурные подразделения)\n"
            f"   2. Employee.email для ответственных за ОТ\n"
            f"   3. EmailSettings.recipient_emails (админка → Email Settings)"
        )

    return list(recipients)


def _clean_email_list(emails: List[str]) -> List[str]:
    """
    Очищает список email-адресов от пробелов и приводит к нижнему регистру.

    Args:
        emails: Список email-адресов

    Returns:
        list[str]: Очищенный список (без пустых строк)

    Examples:
        >>> _clean_email_list(['  Test@Example.com  ', 'admin@test.com', '', None])
        ['test@example.com', 'admin@test.com']
    """
    cleaned = []
    for email in emails:
        if email and isinstance(email, str):
            cleaned_email = email.strip().lower()
            if cleaned_email:  # Проверяем, что не пустая строка после очистки
                cleaned.append(cleaned_email)
    return cleaned


def get_recipients_detailed(
    subdivision: Optional['StructuralSubdivision'],
    organization: 'Organization',
    notification_type: str = 'general'
) -> Dict[str, any]:
    """
    Возвращает детальный список получателей без дедупликации для отображения в UI.

    Источники:
    1. SubdivisionEmail — активные email подразделения
    2. Employee.email — ответственные за ОТ БЕЗ отдела (department__isnull=True)
    3. EmailSettings — получатели организации (по типу уведомления)

    Возвращает словарь со всеми получателями (включая дубликаты) и статистикой.
    """
    from directory.models import Employee

    recipients_data: List[Dict[str, str]] = []
    unique_emails: Set[str] = set()

    # Источник 1: email подразделения
    if subdivision:
        try:
            subdivision_emails_qs = subdivision.notification_emails.filter(
                is_active=True
            ).values_list('email', flat=True)

            for email in subdivision_emails_qs:
                if not email:
                    continue
                email_clean = email.strip().lower()
                if not email_clean:
                    continue
                recipients_data.append({
                    'email': email_clean,
                    'full_name': subdivision.name,
                    'position': '',
                    'source': 'subdivision',
                    'source_display': 'Email подразделения',
                })
                unique_emails.add(email_clean)
        except Exception as exc:
            logger.warning("Не удалось получить email подразделения: %s", exc)

    # Источник 2: ответственные за ОТ без отдела
    if subdivision:
        try:
            responsible_employees_qs = Employee.objects.active_for_operations().filter(
                subdivision=subdivision,
                department__isnull=True,
                position__is_responsible_for_safety=True,
                email__isnull=False
            ).exclude(email='')

            for employee in responsible_employees_qs:
                email_clean = employee.email.strip().lower()
                if not email_clean:
                    continue
                recipients_data.append({
                    'email': email_clean,
                    'full_name': employee.full_name_nominative or employee.full_name,
                    'position': employee.position.position_name if employee.position else '',
                    'source': 'employee',
                    'source_display': 'Ответственный за охрану труда (подразделение)',
                })
                unique_emails.add(email_clean)
        except Exception as exc:
            logger.warning("Не удалось получить ответственных за ОТ: %s", exc)

    # Источник 3: email организации
    try:
        email_settings = organization.email_settings
        if email_settings.is_active:
            if notification_type == 'instruction_journal':
                org_emails = email_settings.get_instruction_journal_recipients()
            else:
                org_emails = email_settings.get_recipient_list()

            for email in org_emails:
                if not email:
                    continue
                email_clean = email.strip().lower()
                if not email_clean:
                    continue
                recipients_data.append({
                    'email': email_clean,
                    'full_name': organization.short_name_ru,
                    'position': '',
                    'source': 'organization',
                    'source_display': 'Email организации',
                })
                unique_emails.add(email_clean)
    except Exception as exc:
        logger.warning("Не удалось получить EmailSettings организации: %s", exc)

    return {
        'recipients': recipients_data,
        'total_count': len(recipients_data),
        'unique_emails_count': len(unique_emails),
        'has_recipients': len(recipients_data) > 0,
    }


def get_recipients_for_department(
    department: 'Department',
    subdivision: 'StructuralSubdivision',
    organization: 'Organization',
    notification_type: str = 'general'
) -> Dict[str, any]:
    """
    Получает получателей для конкретного отдела с fallback на подразделение.

    Логика:
    1. Email подразделения (у отдела своих нет)
    2. Ответственные в отделе. Если нет — fallback на ответственных подразделения.
    3. Email организации из EmailSettings
    """
    from directory.models import Employee

    recipients_data: List[Dict[str, str]] = []
    unique_emails: Set[str] = set()
    fallback_used = False

    # Источник 1: email подразделения
    try:
        subdivision_emails_qs = subdivision.notification_emails.filter(
            is_active=True
        ).values_list('email', flat=True)

        for email in subdivision_emails_qs:
            if not email:
                continue
            email_clean = email.strip().lower()
            if not email_clean:
                continue
            recipients_data.append({
                'email': email_clean,
                'full_name': subdivision.name,
                'position': '',
                'source': 'subdivision',
                'source_display': 'Email подразделения',
            })
            unique_emails.add(email_clean)
    except Exception as exc:
        logger.warning("Не удалось получить email подразделения: %s", exc)

    # Источник 2: ответственные за ОТ
    responsible_qs = Employee.objects.active_for_operations().filter(
        subdivision=subdivision,
        department=department,
        position__is_responsible_for_safety=True,
        email__isnull=False
    ).exclude(email='')

    if not responsible_qs.exists():
        fallback_used = True
        responsible_qs = Employee.objects.active_for_operations().filter(
            subdivision=subdivision,
            department__isnull=True,
            position__is_responsible_for_safety=True,
            email__isnull=False
        ).exclude(email='')

    for employee in responsible_qs:
        email_clean = employee.email.strip().lower()
        if not email_clean:
            continue
        recipients_data.append({
            'email': email_clean,
            'full_name': employee.full_name_nominative or employee.full_name,
            'position': employee.position.position_name if employee.position else '',
            'source': 'employee',
            'source_display': 'Ответственный за охрану труда (отдел)' if not fallback_used else 'Ответственный за охрану труда (подразделение)',
        })
        unique_emails.add(email_clean)

    # Источник 3: email организации
    try:
        email_settings = organization.email_settings
        if email_settings.is_active:
            if notification_type == 'instruction_journal':
                org_emails = email_settings.get_instruction_journal_recipients()
            else:
                org_emails = email_settings.get_recipient_list()

            for email in org_emails:
                if not email:
                    continue
                email_clean = email.strip().lower()
                if not email_clean:
                    continue
                recipients_data.append({
                    'email': email_clean,
                    'full_name': organization.short_name_ru,
                    'position': '',
                    'source': 'organization',
                    'source_display': 'Email организации',
                })
                unique_emails.add(email_clean)
    except Exception as exc:
        logger.warning("Не удалось получить EmailSettings организации: %s", exc)

    return {
        'recipients': recipients_data,
        'total_count': len(recipients_data),
        'unique_emails_count': len(unique_emails),
        'has_recipients': len(recipients_data) > 0,
        'fallback_used': fallback_used,
    }


def get_recipients_summary(
    subdivision: Optional['StructuralSubdivision'],
    organization: 'Organization'
) -> Dict[str, any]:
    """
    Возвращает детальную статистику по получателям из каждого источника.

    Полезно для отладки и отображения информации пользователю.

    Args:
        subdivision: Структурное подразделение
        organization: Организация

    Returns:
        dict: Статистика по источникам
            {
                'total': int,  # Общее количество уникальных получателей
                'subdivision_emails': list[str],  # Из SubdivisionEmail
                'responsible_employees': list[str],  # Из Employee.email
                'organization_emails': list[str],  # Из EmailSettings
                'all_recipients': list[str],  # Итоговый список (уникальные)
                'duplicates_removed': int,  # Количество удалённых дубликатов
            }

    Examples:
        >>> summary = get_recipients_summary(subdivision, organization)
        >>> print(f"Всего: {summary['total']}")
        >>> print(f"Из подразделения: {len(summary['subdivision_emails'])}")
    """
    from directory.models import Employee

    # Собираем из каждого источника отдельно
    subdivision_emails = []
    responsible_emails = []
    organization_emails = []

    # Источник 1: SubdivisionEmail
    if subdivision:
        try:
            subdivision_emails = list(
                subdivision.notification_emails.filter(
                    is_active=True
                ).values_list('email', flat=True)
            )
            subdivision_emails = _clean_email_list(subdivision_emails)
        except:
            pass

    # Источник 2: Employee.email
    if subdivision:
        try:
            responsible_emails = list(
                Employee.objects.active_for_operations().filter(
                    subdivision=subdivision,
                    position__is_responsible_for_safety=True,
                    email__isnull=False
                ).exclude(email='').values_list('email', flat=True)
            )
            responsible_emails = _clean_email_list(responsible_emails)
        except:
            pass

    # Источник 3: EmailSettings
    try:
        email_settings = organization.email_settings
        if email_settings.is_active:
            organization_emails = email_settings.get_recipient_list()
            organization_emails = _clean_email_list(organization_emails)
    except:
        pass

    # Объединяем и считаем дубликаты
    all_emails = subdivision_emails + responsible_emails + organization_emails
    unique_emails = list(set(all_emails))
    duplicates_count = len(all_emails) - len(unique_emails)

    return {
        'total': len(unique_emails),
        'subdivision_emails': subdivision_emails,
        'responsible_employees': responsible_emails,
        'organization_emails': organization_emails,
        'all_recipients': sorted(unique_emails),
        'duplicates_removed': duplicates_count,
    }
