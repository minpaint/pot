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

    def test_multi_month_payment_closes_oldest_months_first(self):
        months = [
            SimpleNamespace(month=1, income_amount=Decimal("1000"), fszn_amount=Decimal("0")),
            SimpleNamespace(month=2, income_amount=Decimal("500"), fszn_amount=Decimal("0")),
        ]
        # налог: янв 160, фев 80; платёж 240 за январь–февраль
        payments = [SimpleNamespace(kind="tax", period_from=1, period_month=2, amount=Decimal("240"))]
        result = calculate_year(Decimal("20"), Decimal("20"), months, payments)

        self.assertEqual(result.months[0].tax_balance, Decimal("0.00"))
        self.assertEqual(result.months[1].tax_balance, Decimal("0.00"))

        # частичный платёж 200: январь закрыт полностью, на февраль 40
        payments = [SimpleNamespace(kind="tax", period_from=1, period_month=2, amount=Decimal("200"))]
        result = calculate_year(Decimal("20"), Decimal("20"), months, payments)

        self.assertEqual(result.months[0].tax_balance, Decimal("0.00"))
        self.assertEqual(result.months[1].tax_balance, Decimal("40.00"))


class TaxPaymentFormTests(TestCase):
    def test_saved_payment_fields_are_disabled(self):
        from datetime import date

        from .admin import TaxPaymentForm
        from .models import TaxPayment

        year = TaxYear.objects.create(year=2026)
        saved = TaxPayment.objects.create(
            tax_year=year, kind="tax", period_month=3,
            paid_date=date(2026, 3, 31), amount=Decimal("100"),
        )

        self.assertTrue(all(f.disabled for f in TaxPaymentForm(instance=saved).fields.values()))
        self.assertFalse(any(f.disabled for f in TaxPaymentForm().fields.values()))

        form = TaxPaymentForm(
            data={"kind": "fszn", "period_month": 5, "amount": "999"}, instance=saved
        )
        self.assertTrue(form.is_valid())
        self.assertEqual(form.cleaned_data["amount"], Decimal("100.00"))


class DeclarationDataTests(TestCase):
    def test_declaration_lines_use_previous_cumulative_tax(self):
        months = [
            SimpleNamespace(month=3, income_amount=Decimal("13289.98"), fszn_amount=Decimal("0")),
            SimpleNamespace(month=6, income_amount=Decimal("16309.57"), fszn_amount=Decimal("0")),
            SimpleNamespace(month=9, income_amount=Decimal("21263.98"), fszn_amount=Decimal("0")),
        ]
        result = calculate_year(Decimal("20"), Decimal("20"), months)
        q3 = result.quarters[2]

        self.assertEqual(q3.income_cum, Decimal("50863.53"))
        self.assertEqual(q3.tax_cum, Decimal("8138.16"))
        self.assertEqual(q3.tax_prev_cum, Decimal("4735.93"))
        self.assertEqual(q3.tax_due_q, Decimal("3402.23"))
        self.assertEqual(result.quarters[0].tax_prev_cum, Decimal("0.00"))
