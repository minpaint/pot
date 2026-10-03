from decimal import Decimal
from types import SimpleNamespace

from django.test import TestCase

from .calculator import calculate_year
from .models import TaxYear


class TaxCalculatorTests(TestCase):
    def test_quarters_aggregate_months(self):
        # 3 месяца по трети квартальных сумм: итоги кварталов совпадают с прежним квартальным расчётом
        q_income = ["9199.07", "15016.15", "12466.61", "16524.74"]
        months = []
        for qi, amount in enumerate(q_income):
            for k in range(3):
                m = qi * 3 + k + 1
                months.append(SimpleNamespace(
                    month=m,
                    income_amount=Decimal(amount) if k == 2 else Decimal("0"),
                    fszn_amount=Decimal("254.10"),
                ))

        result = calculate_year(Decimal("20.00"), Decimal("20.00"), months)

        self.assertEqual(len(result.months), 12)
        self.assertEqual(result.quarters[0].tax_due_q, Decimal("1471.85"))
        self.assertEqual(result.quarters[1].income_cum, Decimal("24215.22"))
        self.assertEqual(result.quarters[1].tax_due_q, Decimal("2402.59"))
        self.assertEqual(result.quarters[3].tax_due_q, Decimal("2643.96"))
        self.assertEqual(result.total_tax, Decimal("8513.05"))
        self.assertEqual(result.total_fszn, Decimal("3049.20"))
        self.assertEqual(result.total_due, Decimal("11562.25"))

    def test_monthly_tax_is_cumulative_difference(self):
        months = [
            SimpleNamespace(month=1, income_amount=Decimal("1000"), fszn_amount=Decimal("0")),
            SimpleNamespace(month=2, income_amount=Decimal("500"), fszn_amount=Decimal("0")),
        ]
        result = calculate_year(Decimal("20"), Decimal("20"), months)

        self.assertEqual(result.months[0].tax_due_m, Decimal("160.00"))
        self.assertEqual(result.months[1].tax_cum, Decimal("240.00"))
        self.assertEqual(result.months[1].tax_due_m, Decimal("80.00"))
        self.assertEqual(result.months[11].tax_cum, Decimal("240.00"))

    def test_tax_year_creates_twelve_months(self):
        year = TaxYear.objects.create(year=2026)

        self.assertEqual(
            list(year.months.values_list("month", flat=True)),
            list(range(1, 13)),
        )

    def test_payments_reduce_balance_cumulatively(self):
        months = [
            SimpleNamespace(month=1, income_amount=Decimal("1000"), fszn_amount=Decimal("100")),
            SimpleNamespace(month=2, income_amount=Decimal("500"), fszn_amount=Decimal("100")),
        ]
        payments = [
            SimpleNamespace(kind="tax", period_month=1, amount=Decimal("160")),
            SimpleNamespace(kind="fszn", period_month=2, amount=Decimal("250")),
        ]
        result = calculate_year(Decimal("20"), Decimal("20"), months, payments)

        self.assertEqual(result.months[0].tax_balance, Decimal("0.00"))
        self.assertEqual(result.months[1].tax_balance, Decimal("80.00"))
        self.assertEqual(result.months[0].fszn_balance, Decimal("100.00"))
        self.assertEqual(result.months[1].fszn_balance, Decimal("-50.00"))
        self.assertEqual(result.quarters[0].tax_balance, Decimal("80.00"))
        self.assertEqual(result.tax_balance, Decimal("80.00"))
        self.assertEqual(result.fszn_balance, Decimal("-50.00"))
        self.assertEqual(result.balance, Decimal("30.00"))
