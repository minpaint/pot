import random
import re

from directory.models.employee import Employee


def _choice_start(value):
    match = re.search(r'\d+', value)
    return int(match.group(0)) if match else None


def _pick_choice(choices, min_start=None, max_start=None):
    filtered = []
    for value, _label in choices:
        start = _choice_start(value)
        if start is None:
            continue
        if min_start is not None and start < min_start:
            continue
        if max_start is not None and start > max_start:
            continue
        filtered.append(value)

    if not filtered:
        filtered = [value for value, _label in choices]

    return random.choice(filtered) if filtered else ""


def get_employee_sizes(employee, gender):
    gender_value = (gender or "").strip().lower()
    is_female = gender_value.startswith("жен")

    height = employee.height or _pick_choice(
        Employee.HEIGHT_CHOICES,
        max_start=170 if is_female else None,
        min_start=None if is_female else 170,
    )
    clothing_size = employee.clothing_size or _pick_choice(
        Employee.CLOTHING_SIZE_CHOICES,
        max_start=52 if is_female else None,
        min_start=None if is_female else 48,
    )
    shoe_size = employee.shoe_size or _pick_choice(
        Employee.SHOE_SIZE_CHOICES,
        max_start=41 if is_female else None,
        min_start=None if is_female else 40,
    )

    return {
        "height": height,
        "clothing_size": clothing_size,
        "shoe_size": shoe_size,
    }
