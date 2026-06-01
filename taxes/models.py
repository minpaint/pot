from decimal import Decimal

from django.db import models

from .calculator import calculate_year


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
        self.ensure_quarters()

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
            quarter_inputs=self.quarters.all(),
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
