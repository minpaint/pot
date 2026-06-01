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
    quarters: list[QuarterCalculation]
    total_income: Decimal
    total_expense: Decimal
    total_base: Decimal
    total_tax: Decimal
    total_fszn: Decimal
    total_due: Decimal


def calculate_year(expense_rate, tax_rate, quarter_inputs) -> YearCalculation:
    expense_rate = normalize_rate(expense_rate)
    tax_rate = normalize_rate(tax_rate)
    items_by_quarter = {item.quarter: item for item in quarter_inputs}

    quarters = []
    income_cum = ZERO
    prev_tax_cum = ZERO
    total_fszn = ZERO

    for quarter in range(1, 5):
        item = items_by_quarter.get(quarter)
        income_q = money(getattr(item, "income_amount", 0))
        fszn_due_q = money(getattr(item, "fszn_amount", 0))

        income_cum = money(income_cum + income_q)
        expense_cum = money(income_cum * expense_rate)
        base_cum = money(income_cum - expense_cum)
        tax_cum = money(base_cum * tax_rate)
        tax_due_q = money(tax_cum - prev_tax_cum)
        total_due_q = money(tax_due_q + fszn_due_q)

        quarters.append(
            QuarterCalculation(
                quarter=quarter,
                income_q=income_q,
                income_cum=income_cum,
                expense_cum=expense_cum,
                base_cum=base_cum,
                tax_cum=tax_cum,
                tax_due_q=tax_due_q,
                fszn_due_q=fszn_due_q,
                total_due_q=total_due_q,
            )
        )

        prev_tax_cum = tax_cum
        total_fszn = money(total_fszn + fszn_due_q)

    total_income = quarters[-1].income_cum if quarters else ZERO
    total_expense = quarters[-1].expense_cum if quarters else ZERO
    total_base = quarters[-1].base_cum if quarters else ZERO
    total_tax = quarters[-1].tax_cum if quarters else ZERO
    total_due = money(total_tax + total_fszn)

    return YearCalculation(
        quarters=quarters,
        total_income=total_income,
        total_expense=total_expense,
        total_base=total_base,
        total_tax=total_tax,
        total_fszn=total_fszn,
        total_due=total_due,
    )
