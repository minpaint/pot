# -*- coding: utf-8 -*-
"""
Утилиты для автоматического расчета графика обучения.

Основано на шаблонах из XLSM и «План по часам ...»:
- Переподготовка: 5 недель нагрузки (40, 40, 40, 40, 32 часов) → 24 рабочих дня.
- Подготовка: 8 недель нагрузки (все по 40 часов) → 40 рабочих дней.

Расчеты ведутся по рабочим дням с учетом графика 5/2 (пн–пт) или 2/2 (2 дня
работы, 2 дня отдыха, цикл повторяется).
"""
from __future__ import annotations

import datetime
from typing import Dict, Iterable, List, Optional, Tuple

# Optional Belarus holidays calendar.
try:
    import holidays as holidays_lib
except ImportError:  # pragma: no cover - optional dependency
    holidays_lib = None

# Код типов обучения → недельные часы
WEEKLY_HOURS_BY_TYPE: Dict[str, List[int]] = {
    'retraining': [40, 40, 40, 40, 32],      # переподготовка
    'preparation': [40, 40, 40, 40, 40, 40, 40, 40],  # подготовка
}

DEFAULT_DAY_HOURS = 8
DEFAULT_WORK_SCHEDULE = '5/2'

_HOLIDAY_CACHE: Dict[int, object] = {}


def _get_holidays_for_year(year: int):
    if not holidays_lib:
        return None
    if year not in _HOLIDAY_CACHE:
        if hasattr(holidays_lib, 'country_holidays'):
            _HOLIDAY_CACHE[year] = holidays_lib.country_holidays('BY', years=[year])
        else:
            _HOLIDAY_CACHE[year] = holidays_lib.BY(years=[year])
    return _HOLIDAY_CACHE[year]


def normalize_work_schedule(work_schedule: Optional[str]) -> str:
    """Нормализовать тип графика работы."""
    return work_schedule if work_schedule in ('5/2', '2/2') else DEFAULT_WORK_SCHEDULE


def is_workday(
    date: datetime.date,
    work_schedule: Optional[str] = None,
    schedule_start: Optional[datetime.date] = None
) -> bool:
    """Проверить, является ли день рабочим для графика."""
    holidays_for_year = _get_holidays_for_year(date.year)
    if holidays_for_year and date in holidays_for_year:
        return False
    work_schedule = normalize_work_schedule(work_schedule)
    if work_schedule == '2/2':
        schedule_start = schedule_start or date
        delta_days = (date - schedule_start).days
        return (delta_days % 4) in (0, 1)
    return date.weekday() < 5


def next_workday(
    date: datetime.date,
    work_schedule: Optional[str] = None,
    schedule_start: Optional[datetime.date] = None
) -> datetime.date:
    """Получить следующий рабочий день (включая текущий, если он рабочий)."""
    current = date
    while not is_workday(current, work_schedule=work_schedule, schedule_start=schedule_start):
        current += datetime.timedelta(days=1)
    return current


def iter_workdays(
    start: datetime.date,
    days: int,
    work_schedule: Optional[str] = None,
    schedule_start: Optional[datetime.date] = None
) -> Iterable[datetime.date]:
    """Генерирует последовательность рабочих дат, включая start, длиной days."""
    if schedule_start is None:
        schedule_start = start
    current = next_workday(start, work_schedule=work_schedule, schedule_start=schedule_start)
    yielded = 0
    while yielded < days:
        if is_workday(current, work_schedule=work_schedule, schedule_start=schedule_start):
            yield current
            yielded += 1
        current += datetime.timedelta(days=1)


def add_workdays(
    start: datetime.date,
    days: int,
    work_schedule: Optional[str] = None,
    schedule_start: Optional[datetime.date] = None
) -> datetime.date:
    """Возвращает дату через days рабочих дней от start (включая start)."""
    last = None
    for last in iter_workdays(start, days, work_schedule=work_schedule, schedule_start=schedule_start):
        pass
    return last or start


def get_weekly_hours(training_type_code: Optional[str]) -> Optional[List[int]]:
    """Получить недельные часы для типа обучения (case-insensitive)."""
    if not training_type_code:
        return None
    normalized = str(training_type_code).strip().lower()
    weeks = WEEKLY_HOURS_BY_TYPE.get(normalized)
    if weeks:
        return weeks
    if 'переподготов' in normalized or 'retraining' in normalized:
        return WEEKLY_HOURS_BY_TYPE.get('retraining')
    if 'подготов' in normalized or 'preparation' in normalized:
        return WEEKLY_HOURS_BY_TYPE.get('preparation')
    return None


def build_workday_schedule(
    start_date: datetime.date,
    weekly_hours: List[int],
    work_schedule: Optional[str] = None,
    schedule_start: Optional[datetime.date] = None
) -> List[Tuple[datetime.date, int]]:
    """
    Построить список (дата, часы) по рабочим дням для заданного недельного плана.
    Каждая неделя режется на 8-часовые дни, остаток в конце недели тоже 8 (документы требуют ровных дней).
    """
    schedule: List[Tuple[datetime.date, int]] = []
    if schedule_start is None:
        schedule_start = start_date
    current_date = next_workday(start_date, work_schedule=work_schedule, schedule_start=schedule_start)
    for week_hours in weekly_hours:
        days_in_week = week_hours // DEFAULT_DAY_HOURS
        for _ in range(days_in_week):
            # Пропускаем выходные
            current_date = next_workday(current_date, work_schedule=work_schedule, schedule_start=schedule_start)
            schedule.append((current_date, DEFAULT_DAY_HOURS))
            current_date += datetime.timedelta(days=1)
    return schedule


def compute_end_date(
    start_date: datetime.date,
    weekly_hours: List[int],
    work_schedule: Optional[str] = None,
    schedule_start: Optional[datetime.date] = None
) -> datetime.date:
    """Дата окончания = последняя рабочая дата расписания."""
    schedule = build_workday_schedule(
        start_date,
        weekly_hours,
        work_schedule=work_schedule,
        schedule_start=schedule_start,
    )
    return schedule[-1][0] if schedule else start_date


def compute_protocol_date(practical_date: Optional[datetime.date]) -> Optional[datetime.date]:
    """В Excel: протокол = пробная работа + 1 день."""
    if not practical_date:
        return None
    return practical_date + datetime.timedelta(days=1)


def compute_exam_date(end_date: Optional[datetime.date]) -> Optional[datetime.date]:
    """
    Дата экзамена = дата окончания обучения.
    Экзамен проводится в последний день обучения.
    """
    return end_date


def subtract_workdays(
    start: datetime.date,
    days: int,
    work_schedule: Optional[str] = None,
    schedule_start: Optional[datetime.date] = None
) -> datetime.date:
    """Вычитает days рабочих дней от start (не включая start)."""
    if days <= 0:
        return start
    current = start - datetime.timedelta(days=1)
    subtracted = 0
    while subtracted < days:
        if is_workday(current, work_schedule=work_schedule, schedule_start=schedule_start):
            subtracted += 1
            if subtracted == days:
                return current
        current -= datetime.timedelta(days=1)
    return current


def compute_practical_date(
    exam_date: Optional[datetime.date],
    work_schedule: Optional[str] = None,
    schedule_start: Optional[datetime.date] = None
) -> Optional[datetime.date]:
    """
    Дата пробной работы = дата экзамена - 1 рабочий день.
    Пробная работа проводится за день до экзамена.
    """
    if not exam_date:
        return None
    return subtract_workdays(
        exam_date,
        1,
        work_schedule=work_schedule,
        schedule_start=schedule_start,
    )


def compute_all_dates(
    start_date: datetime.date,
    weekly_hours: Optional[List[int]],
    work_schedule: Optional[str] = None,
    schedule_start: Optional[datetime.date] = None
) -> Dict[str, Optional[datetime.date]]:
    """
    Рассчитать все даты обучения по дате начала.

    Возвращает словарь:
    - end_date: дата окончания обучения
    - exam_date: дата экзамена (= end_date)
    - practical_date: дата пробной работы (= exam_date - 1 рабочий день)
    - protocol_date: дата протокола (= practical_date + 1 день = exam_date)
    """
    result: Dict[str, Optional[datetime.date]] = {
        'end_date': None,
        'exam_date': None,
        'practical_date': None,
        'protocol_date': None,
    }

    if not start_date or not weekly_hours:
        return result
    if schedule_start is None:
        schedule_start = start_date

    # 1. Дата окончания по недельному плану
    end_date = compute_end_date(
        start_date,
        weekly_hours,
        work_schedule=work_schedule,
        schedule_start=schedule_start,
    )
    result['end_date'] = end_date

    # 2. Дата экзамена = дата окончания
    exam_date = compute_exam_date(end_date)
    result['exam_date'] = exam_date

    # 3. Дата пробной работы = экзамен - 1 рабочий день
    practical_date = compute_practical_date(
        exam_date,
        work_schedule=work_schedule,
        schedule_start=schedule_start,
    )
    result['practical_date'] = practical_date

    # 4. Дата протокола = пробная работа + 1 день (= exam_date)
    protocol_date = compute_protocol_date(practical_date)
    result['protocol_date'] = protocol_date

    return result


def compute_theory_dates(
    start_date: datetime.date,
    work_schedule: Optional[str] = None,
    schedule_start: Optional[datetime.date] = None
) -> List[datetime.date]:
    """
    Карточка теории в Excel ставит 2 случайных рабочих дня (2–4 и 8–10).
    Делаем детерминированно: +3 и +9 рабочих дней от старта.
    """
    first = add_workdays(start_date, 3, work_schedule=work_schedule, schedule_start=schedule_start)
    second = add_workdays(start_date, 9, work_schedule=work_schedule, schedule_start=schedule_start)
    return [first, second]


def attach_program_topics(schedule: List[Tuple[datetime.date, int]], program_content: Optional[dict]) -> List[Dict]:
    """
    Привязать темы из программы к датам: равномерно расходуем часы из content['sections'][].entries[].hours.
    Если программа пустая, темы будут пустыми.
    """
    topics: List[Tuple[str, float]] = []
    if program_content:
        for section in program_content.get('sections', []):
            for entry in section.get('entries', []):
                topics.append((entry.get('topic') or '', float(entry.get('hours', 0) or 0)))

    result: List[Dict] = []
    topic_idx = 0
    topic_remaining = topics[topic_idx][1] if topics else 0

    for day_date, day_hours in schedule:
        topic_text = topics[topic_idx][0] if topics else ''
        result.append({
            'date': day_date,
            'hours': day_hours,
            'topic': topic_text,
        })

        topic_remaining -= day_hours
        while topic_remaining <= 0 and topics and topic_idx + 1 < len(topics):
            topic_idx += 1
            topic_remaining = topics[topic_idx][1]

    return result


def build_diary_entries(
    start_date: datetime.date,
    training_type_code: Optional[str],
    program_content: Optional[dict] = None,
    weekly_hours_override: Optional[List[int]] = None,
    work_schedule: Optional[str] = None,
    schedule_start: Optional[datetime.date] = None,
) -> List[Dict]:
    """
    Сформировать записи дневника с датами и часами:
    - Берем недельные часы из плана.
    - Строим рабочие даты (8 ч/день).
    - Прикрепляем темы из программы по порядку.
    """
    weekly_hours = weekly_hours_override or get_weekly_hours(training_type_code)
    if not weekly_hours:
        return []
    schedule = build_workday_schedule(
        start_date,
        weekly_hours,
        work_schedule=work_schedule,
        schedule_start=schedule_start,
    )
    return attach_program_topics(schedule, program_content)
