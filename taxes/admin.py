from django import forms
from django.contrib import admin
from django.template.loader import render_to_string
from django.utils.html import format_html
from django.utils.safestring import mark_safe

from .calculator import normalize_rate
from .models import TaxMonth, TaxPayment, TaxYear


class SuperuserOnlyMixin:
    """Доступ только для суперпользователя."""
    def has_view_permission(self, request, obj=None):
        return request.user.is_superuser

    def has_add_permission(self, request):
        return request.user.is_superuser

    def has_change_permission(self, request, obj=None):
        return request.user.is_superuser

    def has_delete_permission(self, request, obj=None):
        return request.user.is_superuser


class TaxMonthInline(admin.TabularInline):
    model = TaxMonth
    extra = 0
    can_delete = False
    fields = ("month_label", "income_amount", "fszn_amount", "note")
    readonly_fields = ("month_label",)

    def month_label(self, obj):
        return obj.get_month_display()
    month_label.short_description = "Месяц"

    def has_add_permission(self, request, obj=None):
        return False


class TaxPaymentForm(forms.ModelForm):
    """Проведённый (сохранённый) платёж доступен только для просмотра."""

    class Meta:
        model = TaxPayment
        fields = "__all__"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk:
            for field in self.fields.values():
                field.disabled = True


class TaxPaymentInline(admin.TabularInline):
    model = TaxPayment
    form = TaxPaymentForm
    extra = 1
    fields = ("kind", "period_from", "period_month", "paid_date", "amount", "note")


@admin.register(TaxYear)
class TaxYearAdmin(SuperuserOnlyMixin, admin.ModelAdmin):
    list_display = (
        "year",
        "oked_list",
        "expense_rate_display",
        "tax_rate_display",
        "total_income_display",
        "total_tax_display",
        "total_fszn_display",
        "total_due_display",
        "balance_display",
        "quarters_summary",
    )
    readonly_fields = ("calculation_preview",)
    inlines = [TaxMonthInline, TaxPaymentInline]
    fieldsets = (
        (None, {
            "fields": ("year", "expense_rate", "tax_rate", "note")
        }),
        ("Справочно", {
            "fields": ("oked_1", "oked_2")
        }),
        ("Расчет", {
            "fields": ("calculation_preview",)
        }),
    )

    def get_queryset(self, request):
        return super().get_queryset(request).prefetch_related("months", "payments")

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        obj.ensure_months()

    def calculation_preview(self, obj):
        if not obj.pk:
            return "Сохраните год, после этого появятся 4 квартала и расчет."

        obj.ensure_months()
        calculation = obj.calculation()
        html = render_to_string(
            "taxes/calculation_preview.html",
            {
                "calc": calculation,
                "balances": {
                    str(m.month): {
                        "tax": str(m.tax_balance),
                        "fszn": str(m.fszn_balance),
                    }
                    for m in calculation.months
                },
            },
        )
        return mark_safe(html)
    calculation_preview.short_description = ""

    def expense_rate_display(self, obj):
        return f"{normalize_rate(obj.expense_rate) * 100:.2f}%"
    expense_rate_display.short_description = "Расходы"

    def quarters_summary(self, obj):
        calc = obj.calculation()
        filled = [q for q in calc.quarters if q.income_q or q.fszn_due_q]
        if not filled:
            return mark_safe('<span style="color:#999">нет данных</span>')
        parts = []
        for q in filled:
            parts.append(
                f'<span class="qs-block">'
                f'<b>Q{q.quarter}</b> '
                f'налог&nbsp;{q.tax_due_q:.2f} '
                f'+ ФСЗН&nbsp;{q.fszn_due_q:.2f} '
                f'= <b>{q.total_due_q:.2f}</b>'
                f'</span>'
            )
        return mark_safe('<span class="qs-wrap">' + ''.join(parts) + '</span>')
    quarters_summary.short_description = "Кварталы (к уплате)"
    quarters_summary.allow_tags = True

    def oked_list(self, obj):
        return f"{obj.oked_1}, {obj.oked_2}"
    oked_list.short_description = "ОКЭД"

    def tax_rate_display(self, obj):
        return f"{normalize_rate(obj.tax_rate) * 100:.2f}%"
    tax_rate_display.short_description = "Налог"

    def total_income_display(self, obj):
        return obj.calculation().total_income
    total_income_display.short_description = "Доход за год"

    def total_tax_display(self, obj):
        return obj.calculation().total_tax
    total_tax_display.short_description = "Налог за год"

    def total_fszn_display(self, obj):
        return obj.calculation().total_fszn
    total_fszn_display.short_description = "ФСЗН за год"

    def total_due_display(self, obj):
        return obj.calculation().total_due
    total_due_display.short_description = "Всего к уплате"

    def balance_display(self, obj):
        calc = obj.calculation()
        color = "#c0392b" if calc.balance > 0 else "#1e7e34"
        return format_html(
            '<b style="color:{}">{}</b><br><span style="color:#999;font-size:11px">налог {} / ФСЗН {}</span>',
            color, f"{calc.balance:.2f}", f"{calc.tax_balance:.2f}", f"{calc.fszn_balance:.2f}",
        )
    balance_display.short_description = "Остаток к уплате"

    class Media:
        css = {"all": ("taxes/admin.css",)}
        js = ("taxes/payment_autofill.js",)
