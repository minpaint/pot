from django.contrib import admin
from django.template.loader import render_to_string
from django.utils.safestring import mark_safe

from .calculator import normalize_rate
from .models import TaxQuarter, TaxYear


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


class TaxQuarterInline(admin.TabularInline):
    model = TaxQuarter
    extra = 0
    can_delete = False
    fields = ("quarter_label", "income_amount", "fszn_amount", "note")
    readonly_fields = ("quarter_label",)

    def quarter_label(self, obj):
        return obj.get_quarter_display()
    quarter_label.short_description = "Квартал"

    def has_add_permission(self, request, obj=None):
        return False


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
        "quarters_summary",
    )
    readonly_fields = ("calculation_preview",)
    inlines = [TaxQuarterInline]
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
        return super().get_queryset(request).prefetch_related("quarters")

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        obj.ensure_quarters()

    def calculation_preview(self, obj):
        if not obj.pk:
            return "Сохраните год, после этого появятся 4 квартала и расчет."

        obj.ensure_quarters()
        calculation = obj.calculation()
        html = render_to_string(
            "taxes/calculation_preview.html",
            {
                "calc": calculation,
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

    class Media:
        css = {"all": ("taxes/admin.css",)}
