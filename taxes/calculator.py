from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP


MONEY_QUANT = Decimal("0.01")
ZERO = Decimal("0.00")


def money(value) -> Decimal:
    return Decimal(value or 0).quantize(MONEY_QUANT, rounding=ROUND_HALF_UP)


def normalize_rate(rate) -> Decimal:
    value = Decimal(rate or 0)
    if value > 1:
        value = value / Decimal("100")
    return value


MONTH_NAMES = (
    "Январь", "Февраль", "Март", "Апрель", "Май", "Июнь",
    "Июль", "Август", "Сентябрь", "Октябрь", "Ноябрь", "Декабрь",
)


@dataclass(frozen=True)
class MonthCalculation:
    month: int
    income_m: Decimal
    income_cum: Decimal
    expense_cum: Decimal
    base_cum: Decimal
    tax_cum: Decimal
    tax_due_m: Decimal
    fszn_due_m: Decimal
    total_due_m: Decimal
    tax_paid_cum: Decimal = ZERO
    tax_balance: Decimal = ZERO
    fszn_cum: Decimal = ZERO
    fszn_paid_cum: Decimal = ZERO
    fszn_balance: Decimal = ZERO

    @property
    def month_name(self):
        return MONTH_NAMES[self.month - 1]


@dataclass(frozen=True)
class QuarterCalculation:
    quarter: int
    income_q: Decimal
    income_cum: Decimal
    expense_cum: Decimal
    base_cum: Decimal
    tax_cum: Decimal
    tax_due_q: Decimal
    fszn_due_q: Decimal
    total_due_q: Decimal
    tax_paid_cum: Decimal = ZERO
    tax_balance: Decimal = ZERO
    fszn_paid_cum: Decimal = ZERO
    fszn_balance: Decimal = ZERO


@dataclass(frozen=True)
class YearCalculation:
    months: list[MonthCalculation]
    quarters: list[QuarterCalculation]
    total_income: Decimal
    total_expense: Decimal
    total_base: Decimal
    total_tax: Decimal
    total_fszn: Decimal
    total_due: Decimal
    total_tax_paid: Decimal = ZERO
    total_fszn_paid: Decimal = ZERO
    tax_balance: Decimal = ZERO
    fszn_balance: Decimal = ZERO
    balance: Decimal = ZERO


def allocate_payments(payments, dues):
    """Раскладывает платежи по месяцам.

    Платёж за один месяц целиком относится к нему. Платёж за диапазон
    (period_from..period_month) закрывает по очереди самые старые долги месяцев
    диапазона, остаток относится на последний месяц диапазона.
    """
    paid = {"tax": {}, "fszn": {}}
    # сортировка устойчивая: внутри месяца сохраняется порядок по дате
    ordered = sorted(payments, key=lambda p: p.period_month)
    for pay in ordered:
        bucket = paid[pay.kind]
        end = pay.period_month
        start = getattr(pay, "period_from", None) or end
        left = money(pay.amount)
        if start < end:
            for month in range(start, end):
                need = max(money(dues[pay.kind][month] - bucket.get(month, 0)), ZERO)
                part = min(left, need)
                if part > 0:
                    bucket[month] = money(bucket.get(month, 0) + part)
                    left = money(left - part)
        bucket[end] = money(bucket.get(end, 0) + left)
    return paid


def calculate_year(expense_rate, tax_rate, month_inputs, payments=()) -> YearCalculation:
    """Расчёт нарастающим итогом по месяцам; кварталы агрегируются из месяцев.

    payments — платежи с атрибутами kind ("tax"/"fszn"), period_month, amount.
    Остаток за месяц = начислено нарастающим − уплачено нарастающим (по периодам до этого месяца).
    """
    expense_rate = normalize_rate(expense_rate)
    tax_rate = normalize_rate(tax_rate)
    items_by_month = {item.month: item for item in month_inputs}

    dues = {"tax": {}, "fszn": {}}
    cum = ZERO
    prev = ZERO
    for month in range(1, 13):
        item = items_by_month.get(month)
        cum = money(cum + money(getattr(item, "income_amount", 0)))
        tax_cum_pre = money(money(cum - money(cum * expense_rate)) * tax_rate)
        dues["tax"][month] = money(tax_cum_pre - prev)
        dues["fszn"][month] = money(getattr(item, "fszn_amount", 0))
        prev = tax_cum_pre
    paid = allocate_payments(payments, dues)

    months = []
    fszn_cum = ZERO
    tax_paid_cum = ZERO
    fszn_paid_cum = ZERO
    income_cum = ZERO
    prev_tax_cum = ZERO
    total_fszn = ZERO

    for month in range(1, 13):
        item = items_by_month.get(month)
        income_m = money(getattr(item, "income_amount", 0))
        fszn_due_m = money(getattr(item, "fszn_amount", 0))

        income_cum = money(income_cum + income_m)
        expense_cum = money(income_cum * expense_rate)
        base_cum = money(income_cum - expense_cum)
        tax_cum = money(base_cum * tax_rate)
        tax_due_m = money(tax_cum - prev_tax_cum)
        fszn_cum = money(fszn_cum + fszn_due_m)
        tax_paid_cum = money(tax_paid_cum + paid["tax"].get(month, 0))
        fszn_paid_cum = money(fszn_paid_cum + paid["fszn"].get(month, 0))

        months.append(
            MonthCalculation(
                month=month,
                income_m=income_m,
                income_cum=income_cum,
                expense_cum=expense_cum,
                base_cum=base_cum,
                tax_cum=tax_cum,
                tax_due_m=tax_due_m,
                fszn_due_m=fszn_due_m,
                total_due_m=money(tax_due_m + fszn_due_m),
                tax_paid_cum=tax_paid_cum,
                tax_balance=money(tax_cum - tax_paid_cum),
                fszn_cum=fszn_cum,
                fszn_paid_cum=fszn_paid_cum,
                fszn_balance=money(fszn_cum - fszn_paid_cum),
            )
        )

        prev_tax_cum = tax_cum
        total_fszn = money(total_fszn + fszn_due_m)

    quarters = []
    for quarter in range(1, 5):
        chunk = months[(quarter - 1) * 3:quarter * 3]
        last = chunk[-1]
        tax_due_q = money(sum(m.tax_due_m for m in chunk))
        fszn_due_q = money(sum(m.fszn_due_m for m in chunk))
        quarters.append(
            QuarterCalculation(
                quarter=quarter,
                income_q=money(sum(m.income_m for m in chunk)),
                income_cum=last.income_cum,
                expense_cum=last.expense_cum,
                base_cum=last.base_cum,
                tax_cum=last.tax_cum,
                tax_due_q=tax_due_q,
                fszn_due_q=fszn_due_q,
                total_due_q=money(tax_due_q + fszn_due_q),
                tax_paid_cum=last.tax_paid_cum,
                tax_balance=last.tax_balance,
                fszn_paid_cum=last.fszn_paid_cum,
                fszn_balance=last.fszn_balance,
            )
        )

    last = months[-1]
    return YearCalculation(
        months=months,
        quarters=quarters,
        total_income=last.income_cum,
        total_expense=last.expense_cum,
        total_base=last.base_cum,
        total_tax=last.tax_cum,
        total_fszn=total_fszn,
        total_due=money(last.tax_cum + total_fszn),
        total_tax_paid=last.tax_paid_cum,
        total_fszn_paid=last.fszn_paid_cum,
        tax_balance=last.tax_balance,
        fszn_balance=last.fszn_balance,
        balance=money(last.tax_balance + last.fszn_balance),
    )
