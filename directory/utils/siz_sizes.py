import random

from directory.models.employee import Employee

# ---------------------------------------------------------------------------
# Взвешенные распределения антропометрических данных
#
# Веса отражают реальное распределение по данным Беларуси/России:
# пик — наиболее распространённые размеры, края — редкие.
# ---------------------------------------------------------------------------

# Рост мужчин: диапазоны ≥ 170 см. Пик — 176-188, очень высокие редки.
_MALE_HEIGHT_WEIGHTS = {
    "170-176 см": 10,
    "176-182 см": 30,
    "182-188 см": 35,
    "188-194 см": 18,
    "194-200 см": 7,
}

# Рост женщин: диапазоны ≤ 176 см. Пик — 164-170.
_FEMALE_HEIGHT_WEIGHTS = {
    "158-164 см": 20,
    "164-170 см": 50,
    "170-176 см": 30,
}

# Размер одежды мужчин (48–66): пик на 52-54, крупные редки.
_MALE_CLOTHING_WEIGHTS = {
    "48-50": 25,
    "52-54": 40,
    "56-58": 22,
    "60-62": 9,
    "64-66": 4,
}

# Размер одежды женщин (44–54): пик на 44-50.
_FEMALE_CLOTHING_WEIGHTS = {
    "44-46": 35,
    "48-50": 40,
    "52-54": 25,
}

# Размер обуви мужчин (40–48): пик на 42-44.
_MALE_SHOE_WEIGHTS = {
    "40": 2,
    "41": 5,
    "42": 18,
    "43": 25,
    "44": 25,
    "45": 14,
    "46": 7,
    "47": 3,
    "48": 1,
}

# Размер обуви женщин (36–41): пик на 38-39.
_FEMALE_SHOE_WEIGHTS = {
    "36": 5,
    "37": 15,
    "38": 30,
    "39": 30,
    "40": 15,
    "41": 5,
}


def _weighted_choice(weights: dict) -> str:
    """Выбирает ключ из словаря {значение: вес} с учётом весов."""
    values = list(weights.keys())
    wts = list(weights.values())
    return random.choices(values, weights=wts, k=1)[0]


def get_employee_sizes(employee, gender):
    """
    Возвращает антропометрические данные сотрудника.

    Если поле заполнено в БД — используется реальное значение.
    Если поле пустое — генерируется реалистичное случайное значение
    с учётом пола (взвешенное распределение, не равновероятное).
    """
    is_female = (gender or "").strip().lower().startswith("жен")

    if is_female:
        height = employee.height or _weighted_choice(_FEMALE_HEIGHT_WEIGHTS)
        clothing_size = employee.clothing_size or _weighted_choice(_FEMALE_CLOTHING_WEIGHTS)
        shoe_size = employee.shoe_size or _weighted_choice(_FEMALE_SHOE_WEIGHTS)
    else:
        height = employee.height or _weighted_choice(_MALE_HEIGHT_WEIGHTS)
        clothing_size = employee.clothing_size or _weighted_choice(_MALE_CLOTHING_WEIGHTS)
        shoe_size = employee.shoe_size or _weighted_choice(_MALE_SHOE_WEIGHTS)

    return {
        "height": height,
        "clothing_size": clothing_size,
        "shoe_size": shoe_size,
    }
