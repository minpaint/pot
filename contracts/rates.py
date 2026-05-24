# -*- coding: utf-8 -*-
"""
Получение курсов валют с API Национального банка РБ.
Документация: https://www.nbrb.by/apihelp/exrates
"""
import urllib.request
import json
from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP

# Числовые коды валют НБРБ (API не принимает аббревиатуры)
NBRB_CURRENCY_IDS = {
    "USD": 431,
    "EUR": 451,
    "RUB": 456,
}

NBRB_API = "https://api.nbrb.by/exrates/rates/{cur_id}?ondate={date}&periodicity=0"


def get_rate(currency: str, on_date: date, _retries: int = 7) -> Decimal:
    """
    Возвращает курс валюты к BYN на указанную дату.
    Если на эту дату курс не опубликован (выходные/праздники),
    пробует предыдущие дни — до _retries раз.

    Пример: get_rate("USD", date(2026, 1, 31)) -> Decimal("2.8496")
    """
    if currency == "BYN":
        return Decimal("1")

    cur_id = NBRB_CURRENCY_IDS.get(currency.upper())
    if cur_id is None:
        raise ValueError(f"Неизвестная валюта: {currency}")

    attempt_date = on_date
    for _ in range(_retries):
        url = NBRB_API.format(
            cur_id=cur_id,
            date=attempt_date.strftime("%Y-%m-%d"),
        )
        try:
            with urllib.request.urlopen(url, timeout=5) as resp:
                data = json.loads(resp.read().decode())
                rate = Decimal(str(data["Cur_OfficialRate"]))
                scale = Decimal(str(data.get("Cur_Scale", 1)))
                return (rate / scale).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)
        except Exception:
            attempt_date -= timedelta(days=1)

    raise RuntimeError(
        f"Не удалось получить курс {currency} на {on_date} (проверьте интернет)"
    )


def convert_to_byn(amount: Decimal, currency: str, on_date: date) -> Decimal:
    """
    Конвертирует сумму в указанной валюте в BYN по курсу НБРБ на дату.
    Возвращает значение с точностью до копеек (2 знака).
    """
    if currency == "BYN":
        return amount
    rate = get_rate(currency, on_date)
    return (amount * rate).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
