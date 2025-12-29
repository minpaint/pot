# directory/utils/vehicle_utils.py
"""
🚗 Утилиты для работы с функционалом управления служебным автомобилем

Этот модуль содержит централизованные функции для проверки и обработки
мероприятий по охране труда для сотрудников, управляющих служебным транспортом.
"""

from typing import Optional
from directory.models import Employee


def needs_vehicle_training(employee: Employee) -> bool:
    """
    Проверяет, нужны ли сотруднику мероприятия по управлению служебным автомобилем.

    Args:
        employee: Объект сотрудника

    Returns:
        bool: True если сотрудник управляет служебным автомобилем
    """
    return (
        employee.position is not None and
        employee.position.drives_company_vehicle
    )


def get_vehicle_position_name() -> str:
    """
    Возвращает стандартное название виртуальной должности для управления авто.

    Returns:
        str: Название должности "Управление служебным автомобилем"
    """
    return "Управление служебным автомобилем"


def get_vehicle_internship_days() -> int:
    """
    Возвращает фиксированный срок стажировки для управления служебным автомобилем.

    Returns:
        int: Срок стажировки в днях (5 рабочих дней)
    """
    return 5


def get_vehicle_instructions(employee: Employee) -> str:
    """
    Возвращает номера инструкций по охране труда для управления автомобилем.

    Args:
        employee: Объект сотрудника

    Returns:
        str: Номера инструкций из поля company_vehicle_instructions или пустая строка
    """
    if (
        employee.position and
        employee.position.company_vehicle_instructions
    ):
        return employee.position.company_vehicle_instructions
    return ""


def combine_instructions(employee: Employee) -> str:
    """
    Объединяет инструкции по основной должности и управлению служебным автомобилем.

    Args:
        employee: Объект сотрудника

    Returns:
        str: Объединенный список номеров инструкций через запятую
    """
    instructions = []

    if employee.position:
        # Добавляем инструкции основной должности
        if employee.position.safety_instructions_numbers:
            instructions.append(employee.position.safety_instructions_numbers)

        # Добавляем инструкции по управлению автомобилем (если есть)
        if (
            employee.position.drives_company_vehicle and
            employee.position.company_vehicle_instructions
        ):
            instructions.append(employee.position.company_vehicle_instructions)

    return ", ".join(filter(None, instructions))


def needs_main_position_internship(employee: Employee) -> bool:
    """
    Проверяет, нужна ли сотруднику стажировка по основной должности.

    Args:
        employee: Объект сотрудника

    Returns:
        bool: True если для должности установлен срок стажировки > 0
    """
    return (
        employee.position is not None and
        employee.position.internship_period_days > 0
    )
