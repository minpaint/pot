from django.db import migrations


def quarters_to_months(apps, schema_editor):
    """Данные квартала переносятся в последний месяц квартала."""
    TaxYear = apps.get_model("taxes", "TaxYear")
    TaxQuarter = apps.get_model("taxes", "TaxQuarter")
    TaxMonth = apps.get_model("taxes", "TaxMonth")

    for year in TaxYear.objects.all():
        for month in range(1, 13):
            TaxMonth.objects.get_or_create(tax_year=year, month=month)
        for q in TaxQuarter.objects.filter(tax_year=year):
            if not (q.income_amount or q.fszn_amount or q.note):
                continue
            TaxMonth.objects.filter(tax_year=year, month=q.quarter * 3).update(
                income_amount=q.income_amount,
                fszn_amount=q.fszn_amount,
                note=q.note,
            )


class Migration(migrations.Migration):

    dependencies = [
        ("taxes", "0003_add_tax_month"),
    ]

    operations = [
        migrations.RunPython(quarters_to_months, migrations.RunPython.noop),
    ]
