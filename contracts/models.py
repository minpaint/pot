# -*- coding: utf-8 -*-
from django.db import models


class Client(models.Model):
    org_name = models.CharField("Полное название организации", max_length=300)
    org_name_short = models.CharField("Краткое название", max_length=100)
    director_name = models.CharField("ФИО подписанта (родит. падеж)", max_length=200,
                                     help_text="Например: Фаттахова Ильгиза Ринатовича")
    director_initials = models.CharField("Инициалы подписанта", max_length=50,
                                         help_text="Например: И.Р. Фаттахов")
    director_position = models.CharField("Должность подписанта (родит. падеж)", max_length=100,
                                         default="директора",
                                         help_text="Родительный падеж: директора, председателя, генерального директора")
    director_basis = models.CharField("Действует на основании", max_length=200,
                                      default="Устава")
    unp = models.CharField("УНП", max_length=20)
    okpo = models.CharField("ОКПО", max_length=30, blank=True, default="")
    address = models.CharField("Юридический адрес", max_length=300)
    account = models.CharField("Расчётный счёт (IBAN)", max_length=60)
    bank = models.CharField("Название банка", max_length=200)
    bank_branch = models.CharField("Отделение банка", max_length=100, blank=True, default="",
                                   help_text="Например: ЦБУ №109")
    bic = models.CharField("БИК", max_length=20)
    bank_city = models.CharField("Город банка", max_length=50, default="г. Минск")
    phone = models.CharField("Телефон/факс", max_length=100)
    email = models.EmailField("E-mail", blank=True, default="")
    print_envelope = models.BooleanField("Печать шильдиков", default=True,
                                         help_text="Снять, если акты доставляются нарочным")

    class Meta:
        verbose_name = "Клиент"
        verbose_name_plural = "Клиенты"
        ordering = ["org_name_short"]

    def __str__(self):
        return f"{self.org_name_short} (УНП {self.unp})"

    def to_dict(self):
        return {
            "org_name": self.org_name,
            "org_name_short": self.org_name_short,
            "director_name": self.director_name,
            "director_initials": self.director_initials,
            "director_position": self.director_position,
            "director_basis": self.director_basis,
            "unp": self.unp,
            "okpo": self.okpo,
            "address": self.address,
            "account": self.account,
            "bank": self.bank,
            "bank_branch": self.bank_branch,
            "bic": self.bic,
            "bank_city": self.bank_city,
            "phone": self.phone,
            "email": self.email,
        }


SERVICE_DEFAULT = "консультации (методическую помощь) по вопросам охраны труда"


class Contract(models.Model):
    CURRENCY_BYN = "BYN"
    CURRENCY_USD = "USD"
    CURRENCY_EUR = "EUR"
    CURRENCY_CHOICES = [
        (CURRENCY_BYN, "BYN (бел. руб.)"),
        (CURRENCY_USD, "USD (доллар США)"),
        (CURRENCY_EUR, "EUR (евро)"),
    ]

    number = models.CharField("Номер договора", max_length=50, blank=True, editable=False)
    date = models.DateField("Дата договора")
    client = models.ForeignKey(Client, on_delete=models.PROTECT,
                                verbose_name="Клиент", related_name="contracts")
    monthly_amount = models.DecimalField("Ежемесячная стоимость",
                                         max_digits=10, decimal_places=2, default=400)
    currency = models.CharField("Валюта", max_length=3,
                                choices=CURRENCY_CHOICES, default=CURRENCY_BYN)
    service_desc = models.TextField("Описание услуг", default=SERVICE_DEFAULT)

    def save(self, *args, **kwargs):
        self.number = f"{self.date.day:02d}/{self.date.month:02d}/{self.date.year}"
        super().save(*args, **kwargs)

    class Meta:
        verbose_name = "Договор"
        verbose_name_plural = "Договоры"
        ordering = ["-date"]

    def __str__(self):
        return f"Договор №{self.number} от {self.date:%d.%m.%Y} — {self.client.org_name_short}"


class Act(models.Model):
    contract = models.ForeignKey(Contract, on_delete=models.CASCADE,
                                  verbose_name="Договор", related_name="acts")
    act_date = models.DateField("Дата акта")
    amount = models.DecimalField("Сумма (руб.)", max_digits=10, decimal_places=2)
    is_paid = models.BooleanField("Оплачен", default=False)
    paid_date = models.DateField("Дата оплаты", null=True, blank=True)

    class Meta:
        verbose_name = "Акт"
        verbose_name_plural = "Акты"
        ordering = ["act_date"]

    def __str__(self):
        status = "✓" if self.is_paid else "✗"
        return (
            f"[{status}] Акт {self.act_date:%d.%m.%Y} — "
            f"{self.contract.client.org_name_short} ({self.amount} руб.)"
        )
