from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import models

from .calculator import MONTH_NAMES, calculate_year


class TaxYear(models.Model):
    year = models.PositiveSmallIntegerField("Год", unique=True)
    oked_1 = models.CharField(
        "ОКЭД 1",
        max_length=20,
        default="74909",
        help_text="Справочно. В расчет не входит.",
    )
    oked_2 = models.CharField(
        "ОКЭД 2",
        max_length=20,
        default="73120",
        help_text="Справочно. В расчет не входит.",
    )
    expense_rate = models.DecimalField(
        "Ставка расходов",
        max_digits=5,
        decimal_places=2,
        default=Decimal("20.00"),
        help_text="Можно вводить как 20 или 0.20 для 20%.",
    )
    tax_rate = models.DecimalField(
        "Ставка налога",
        max_digits=5,
        decimal_places=2,
        default=Decimal("20.00"),
        help_text="Можно вводить как 20 или 0.20 для 20%.",
    )
    note = models.TextField("Примечание", blank=True, default="")

    class Meta:
        verbose_name = "Налоговый год"
        verbose_name_plural = "Налоговые годы"
        ordering = ["-year"]

    def __str__(self):
        return str(self.year)

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        self.ensure_months()

    def ensure_months(self):
        if not self.pk:
            return
        existing = set(self.months.values_list("month", flat=True))
        missing = [
            TaxMonth(tax_year=self, month=month)
            for month in range(1, 13)
            if month not in existing
        ]
        if missing:
            TaxMonth.objects.bulk_create(missing)

    def ensure_quarters(self):
        if not self.pk:
            return
        existing = set(self.quarters.values_list("quarter", flat=True))
        missing = [
            TaxQuarter(tax_year=self, quarter=quarter)
            for quarter in range(1, 5)
            if quarter not in existing
        ]
        if missing:
            TaxQuarter.objects.bulk_create(missing)

    def calculation(self):
        return calculate_year(
            expense_rate=self.expense_rate,
            tax_rate=self.tax_rate,
            month_inputs=self.months.all(),
            payments=self.payments.all(),
        )


class TaxQuarter(models.Model):
    QUARTER_CHOICES = (
        (1, "1 квартал"),
        (2, "2 квартал"),
        (3, "3 квартал"),
        (4, "4 квартал"),
    )

    tax_year = models.ForeignKey(
        TaxYear,
        on_delete=models.CASCADE,
        related_name="quarters",
        verbose_name="Налоговый год",
    )
    quarter = models.PositiveSmallIntegerField("Квартал", choices=QUARTER_CHOICES)
    income_amount = models.DecimalField(
        "Сумма за квартал",
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
    )
    fszn_amount = models.DecimalField(
        "ФСЗН за квартал",
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
    )
    note = models.CharField("Примечание", max_length=255, blank=True, default="")

    class Meta:
        verbose_name = "Налоговый квартал"
        verbose_name_plural = "Налоговые кварталы"
        ordering = ["quarter"]
        constraints = [
            models.UniqueConstraint(
                fields=["tax_year", "quarter"],
                name="unique_tax_quarter_per_year",
            )
        ]

    def __str__(self):
        return f"{self.tax_year.year} / {self.get_quarter_display()}"


class TaxMonth(models.Model):
    MONTH_CHOICES = tuple((i, name) for i, name in enumerate(MONTH_NAMES, start=1))

    tax_year = models.ForeignKey(
        TaxYear,
        on_delete=models.CASCADE,
        related_name="months",
        verbose_name="Налоговый год",
    )
    month = models.PositiveSmallIntegerField("Месяц", choices=MONTH_CHOICES)
    income_amount = models.DecimalField(
        "Сумма за месяц",
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
    )
    fszn_amount = models.DecimalField(
        "ФСЗН за месяц",
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
    )
    note = models.CharField("Примечание", max_length=255, blank=True, default="")

    class Meta:
        verbose_name = "Налоговый месяц"
        verbose_name_plural = "Налоговые месяцы"
        ordering = ["month"]
        constraints = [
            models.UniqueConstraint(
                fields=["tax_year", "month"],
                name="unique_tax_month_per_year",
            )
        ]

    def __str__(self):
        return f"{self.tax_year.year} / {self.get_month_display()}"


class TaxPayment(models.Model):
    KIND_TAX = "tax"
    KIND_FSZN = "fszn"
    KIND_CHOICES = (
        (KIND_TAX, "Налог"),
        (KIND_FSZN, "ФСЗН"),
    )

    tax_year = models.ForeignKey(
        TaxYear,
        on_delete=models.CASCADE,
        related_name="payments",
        verbose_name="Налоговый год",
    )
    kind = models.CharField("Вид", max_length=8, choices=KIND_CHOICES, default=KIND_TAX)
    period_from = models.PositiveSmallIntegerField(
        "С месяца",
        choices=TaxMonth.MONTH_CHOICES,
        null=True,
        blank=True,
        help_text="Только для платежа за несколько месяцев; иначе оставьте пустым.",
    )
    period_month = models.PositiveSmallIntegerField(
        "За месяц (по месяц)",
        choices=TaxMonth.MONTH_CHOICES,
        help_text="Месяц, за который уплачено (для диапазона — последний). Остаток считается нарастающим итогом.",
    )
    paid_date = models.DateField("Дата платежа", null=True, blank=True)
    amount = models.DecimalField("Сумма", max_digits=12, decimal_places=2)
    note = models.CharField("Примечание", max_length=255, blank=True, default="")

    class Meta:
        verbose_name = "Платёж"
        verbose_name_plural = "Платежи"
        ordering = ["period_month", "paid_date", "id"]

    def clean(self):
        super().clean()
        if self.period_from and self.period_month and self.period_from > self.period_month:
            raise ValidationError({"period_from": "«С месяца» не может быть позже «по месяц»."})

    def __str__(self):
        period = self.get_period_month_display()
        if self.period_from and self.period_from < self.period_month:
            period = f"{self.get_period_from_display()}–{period}"
        return f"{self.tax_year.year} / {self.get_kind_display()} / {period}: {self.amount}"
