from decimal import Decimal
from types import SimpleNamespace

from django.test import TestCase

from .calculator import calculate_year
from .models import TaxYear


class TaxCalculatorTests(TestCase):
    def test_calculate_year_uses_cumulative_totals(self):
        quarters = [
            SimpleNamespace(quarter=1, income_amount=Decimal("9199.07"), fszn_amount=Decimal("762.30")),
            SimpleNamespace(quarter=2, income_amount=Decimal("15016.15"), fszn_amount=Decimal("762.30")),
            SimpleNamespace(quarter=3, income_amount=Decimal("12466.61"), fszn_amount=Decimal("762.30")),
            SimpleNamespace(quarter=4, income_amount=Decimal("16524.74"), fszn_amount=Decimal("762.30")),
        ]

        result = calculate_year(Decimal("20.00"), Decimal("20.00"), quarters)

        self.assertEqual(result.quarters[0].tax_due_q, Decimal("1471.85"))
        self.assertEqual(result.quarters[1].income_cum, Decimal("24215.22"))
        self.assertEqual(result.quarters[1].tax_cum, Decimal("3874.44"))
        self.assertEqual(result.quarters[1].tax_due_q, Decimal("2402.59"))
        self.assertEqual(result.quarters[3].tax_due_q, Decimal("2643.96"))
        self.assertEqual(result.total_tax, Decimal("8513.05"))
        self.assertEqual(result.total_fszn, Decimal("3049.20"))
        self.assertEqual(result.total_due, Decimal("11562.25"))

    def test_tax_year_creates_four_quarters(self):
        year = TaxYear.objects.create(year=2026)

        self.assertEqual(year.quarters.count(), 4)
        self.assertEqual(
            list(year.quarters.values_list("quarter", flat=True)),
            [1, 2, 3, 4],
        )
