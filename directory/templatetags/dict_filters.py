"""
Дополнительные фильтры для работы со словарями в шаблонах
"""
from django import template

register = template.Library()


@register.filter
def get_item(dictionary, key):
    """
    Получить значение из словаря по ключу

    Использование в шаблоне:
    {{ my_dict|get_item:"key_name" }}
    """
    if dictionary is None:
        return None
    return dictionary.get(key)


@register.filter
def get_instructions(employee):
    """
    Получить объединенные номера инструкций для сотрудника

    Использование в шаблоне:
    {{ employee|get_instructions }}
    """
    from directory.utils.vehicle_utils import combine_instructions

    if employee is None:
        return ''

    return combine_instructions(employee)
