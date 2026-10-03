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


def calculate_year(expense_rate, tax_rate, month_inputs) -> YearCalculation:
    """Расчёт нарастающим итогом по месяцам; кварталы агрегируются из месяцев."""
    expense_rate = normalize_rate(expense_rate)
    tax_rate = normalize_rate(tax_rate)
    items_by_month = {item.month: item for item in month_inputs}

    months = []
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
    )
