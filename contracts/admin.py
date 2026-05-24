# -*- coding: utf-8 -*-
import io
import zipfile
from datetime import date

from django.contrib import admin, messages
from django.contrib.admin import helpers
from django.db.models import Sum, Count, Q
from django.http import HttpResponse
from django.utils.html import format_html

from .models import Client, Contract, Act
from .docx_builder import build_contract, build_act, build_acts_combined, build_envelopes, last_day_of_month
from .rates import convert_to_byn


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


# ─── Inline: акты внутри договора ────────────────────────────────────────────

class ActInline(admin.TabularInline):
    model = Act
    extra = 1
    fields = ("act_date", "amount", "is_paid", "paid_date", "download_button")
    readonly_fields = ("download_button",)

    def download_button(self, obj):
        if obj.pk:
            url = f"/admin/contracts/act/{obj.pk}/download/"
            return format_html('<a class="button" href="{}">Скачать .docx</a>', url)
        return "—"
    download_button.short_description = "Файл"


# ─── Клиент ───────────────────────────────────────────────────────────────────

@admin.register(Client)
class ClientAdmin(SuperuserOnlyMixin, admin.ModelAdmin):
    change_list_template = "contracts/client_changelist.html"
    list_display = ("org_name_short", "unp", "director_initials", "phone", "email",
                    "print_envelope", "debt_summary")
    list_editable = ("print_envelope",)
    search_fields = ("org_name", "org_name_short", "unp")

    def get_urls(self):
        from django.urls import path
        urls = super().get_urls()
        custom = [
            path("envelopes/",
                 self.admin_site.admin_view(self.download_envelopes),
                 name="client_envelopes"),
        ]
        return custom + urls

    def download_envelopes(self, request):
        clients = Client.objects.filter(print_envelope=True).order_by("org_name_short")
        clients_data = [c.to_dict() for c in clients]
        buf, filename = build_envelopes(clients_data, to_file=False)
        response = HttpResponse(buf.read(), content_type=(
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        ))
        response["Content-Disposition"] = (
            f'attachment; filename="{filename.encode("utf-8").decode("latin-1", errors="replace")}"'
        )
        return response

    fieldsets = (
        ("Организация", {
            "fields": ("org_name", "org_name_short", "unp", "okpo", "address",
                       "phone", "email")
        }),
        ("Подписант", {
            "fields": ("director_position", "director_name", "director_initials", "director_basis")
        }),
        ("Банковские реквизиты", {
            "fields": ("account", "bank", "bank_branch", "bic", "bank_city")
        }),
    )

    def debt_summary(self, obj):
        unpaid = Act.objects.filter(
            contract__client=obj, is_paid=False
        ).aggregate(total=Sum("amount"), cnt=Count("id"))
        total = unpaid["total"] or 0
        cnt = unpaid["cnt"] or 0
        if cnt == 0:
            return format_html('<span style="color:green">Долгов нет</span>')
        return format_html(
            '<span style="color:red">Долг: {} руб. ({} акт.)</span>', total, cnt
        )
    debt_summary.short_description = "Задолженность"


# ─── Договор ─────────────────────────────────────────────────────────────────

@admin.register(Contract)
class ContractAdmin(SuperuserOnlyMixin, admin.ModelAdmin):
    change_list_template = "contracts/contract_changelist.html"
    list_display = ("contract_number", "date", "client", "monthly_amount",
                    "acts_count", "paid_count", "unpaid_amount",
                    "download_contract_link", "generate_acts_link")
    list_filter = ("client",)
    search_fields = ("client__org_name_short",)
    date_hierarchy = "date"
    inlines = [ActInline]

    fieldsets = (
        (None, {
            "fields": ("date", "client", "monthly_amount", "currency", "service_desc")
        }),
    )

    def contract_number(self, obj):
        return f"№{obj.number}"
    contract_number.short_description = "Номер"

    def acts_count(self, obj):
        return obj.acts.count()
    acts_count.short_description = "Актов"

    def paid_count(self, obj):
        paid = obj.acts.filter(is_paid=True).count()
        total = obj.acts.count()
        color = "green" if paid == total and total > 0 else "orange"
        return format_html('<span style="color:{}">{}/{}</span>', color, paid, total)
    paid_count.short_description = "Оплачено"

    def unpaid_amount(self, obj):
        total = obj.acts.filter(is_paid=False).aggregate(s=Sum("amount"))["s"] or 0
        if total == 0:
            return format_html('<span style="color:green">—</span>')
        return format_html('<span style="color:red">{} руб.</span>', total)
    unpaid_amount.short_description = "Долг"

    def download_contract_link(self, obj):
        url = f"/admin/contracts/contract/{obj.pk}/download/"
        return format_html('<a class="button" href="{}">Договор .docx</a>', url)
    download_contract_link.short_description = "Скачать"

    def generate_acts_link(self, obj):
        url = f"/admin/contracts/contract/{obj.pk}/generate_acts/"
        return format_html('<a class="button" href="{}">Создать акты</a>', url)
    generate_acts_link.short_description = "Акты"

    def get_urls(self):
        from django.urls import path
        urls = super().get_urls()
        custom = [
            path("<int:pk>/download/",
                 self.admin_site.admin_view(self.download_contract),
                 name="contract_download"),
            path("<int:pk>/generate_acts/",
                 self.admin_site.admin_view(self.generate_acts_view),
                 name="contract_generate_acts"),
            path("download_month/",
                 self.admin_site.admin_view(self.download_month_view),
                 name="contract_download_month"),
        ]
        return custom + urls

    def download_contract(self, request, pk):
        contract = Contract.objects.select_related("client").get(pk=pk)
        buf, filename = build_contract(
            contract.number, contract.date, contract.client.to_dict(),
            float(contract.monthly_amount), contract.service_desc, to_file=False,
        )
        response = HttpResponse(buf.read(), content_type=(
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        ))
        response["Content-Disposition"] = (
            f'attachment; filename="{filename.encode("utf-8").decode("latin-1", errors="replace")}"'
        )
        return response

    def generate_acts_view(self, request, pk):
        from django.shortcuts import redirect
        contract = Contract.objects.select_related("client").get(pk=pk)
        created = 0
        errors = []
        for i in range(12):
            m = ((contract.date.month - 1 + i) % 12) + 1
            y = contract.date.year + ((contract.date.month - 1 + i) // 12)
            act_date = last_day_of_month(y, m)
            if not contract.acts.filter(act_date=act_date).exists():
                try:
                    amount = convert_to_byn(contract.monthly_amount, contract.currency, act_date)
                except Exception as e:
                    errors.append(f"{act_date}: {e}")
                    amount = contract.monthly_amount
                Act.objects.create(contract=contract, act_date=act_date, amount=amount, is_paid=False)
                created += 1
        if errors:
            messages.warning(request, "Курс не получен для: " + "; ".join(errors))
        if created:
            messages.success(request, f"Создано {created} актов на 12 месяцев.")
        else:
            messages.info(request, "Все акты уже существуют.")
        return redirect(f"/admin/contracts/contract/{pk}/change/")

    def download_month_view(self, request):
        import calendar
        from django.shortcuts import render, redirect
        today = date.today()

        if request.method == "POST":
            year = int(request.POST["year"])
            month = int(request.POST["month"])
            fmt = request.POST.get("fmt", "zip")  # "zip" или "combined"
            last_day = date(year, month, calendar.monthrange(year, month)[1])
            existing_contract_ids = set(
                Act.objects.filter(
                    act_date__year=year, act_date__month=month
                ).values_list("contract_id", flat=True).distinct()
            )
            to_create = []
            for contract in Contract.objects.select_related("client").all():
                if contract.id in existing_contract_ids:
                    continue
                try:
                    amount = convert_to_byn(contract.monthly_amount, contract.currency, last_day)
                except Exception:
                    amount = contract.monthly_amount
                to_create.append(Act(
                    contract=contract,
                    act_date=last_day,
                    amount=amount,
                    is_paid=False,
                ))
            if to_create:
                Act.objects.bulk_create(to_create)
                messages.success(request, f"Создано актов: {len(to_create)}.")
            else:
                messages.info(request, "Все акты за выбранный месяц уже существуют.")

            acts = Act.objects.filter(
                act_date__year=year, act_date__month=month
            ).select_related("contract__client").order_by("contract__client__org_name_short")
            if not acts.exists():
                messages.warning(request, f"Актов за {month:02d}.{year} не найдено.")
                return redirect("../")

            acts_params = []
            for act in acts:
                acts_params.append({
                    'contract_num':  act.contract.number,
                    'contract_date': act.contract.date,
                    'act_date':      act.act_date,
                    'client_dict':   act.contract.client.to_dict(),
                    'amount':        float(act.amount),
                    'service_desc':  act.contract.service_desc,
                })

            if fmt == "combined":
                combined_name = f"Акты_{month:02d}_{year}.docx"
                buf, _ = build_acts_combined(acts_params, combined_name, to_file=False)
                response = HttpResponse(
                    buf.read(),
                    content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                )
                response["Content-Disposition"] = (
                    f'attachment; filename="{combined_name.encode("utf-8").decode("latin-1", errors="replace")}"'
                )
                return response

            buf = io.BytesIO()
            with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
                for p in acts_params:
                    docx_buf, filename = build_act(
                        p['contract_num'], p['contract_date'], p['act_date'],
                        p['client_dict'], p['amount'], p['service_desc'],
                        to_file=False,
                    )
                    zf.writestr(filename, docx_buf.read())
            buf.seek(0)
            zip_name = f"Акты_{month:02d}_{year}.zip"
            response = HttpResponse(buf.read(), content_type="application/zip")
            response["Content-Disposition"] = (
                f'attachment; filename="{zip_name.encode("utf-8").decode("latin-1", errors="replace")}"'
            )
            return response

        month_names = [
            "Январь", "Февраль", "Март", "Апрель", "Май", "Июнь",
            "Июль", "Август", "Сентябрь", "Октябрь", "Ноябрь", "Декабрь",
        ]
        months = [(i, month_names[i - 1]) for i in range(1, 13)]
        years = list(range(today.year - 2, today.year + 2))
        context = dict(
            self.admin_site.each_context(request),
            title="Скачать акты за месяц",
            months=months,
            years=years,
            current_month=today.month,
            current_year=today.year,
        )
        return render(request, "contracts/download_month.html", context)


# ─── Акт ─────────────────────────────────────────────────────────────────────

class PaidFilter(admin.SimpleListFilter):
    title = "Статус оплаты"
    parameter_name = "paid"

    def lookups(self, request, model_admin):
        return [("yes", "Оплачен"), ("no", "Не оплачен")]

    def queryset(self, qs, value):  # noqa: signature order
        # Django передаёт (request, queryset), но SimpleListFilter.queryset — (self, request, queryset)
        return qs

    def queryset(self, request, queryset):
        if self.value() == "yes":
            return queryset.filter(is_paid=True)
        if self.value() == "no":
            return queryset.filter(is_paid=False)
        return queryset


MONTH_NAMES_RU = [
    "Январь", "Февраль", "Март", "Апрель", "Май", "Июнь",
    "Июль", "Август", "Сентябрь", "Октябрь", "Ноябрь", "Декабрь",
]


@admin.register(Act)
class ActAdmin(SuperuserOnlyMixin, admin.ModelAdmin):
    change_list_template = "contracts/act_changelist.html"

    list_display = ("act_date", "contract_link", "client_name", "amount",
                    "paid_status", "paid_date", "download_act_link")
    list_filter = (PaidFilter, "contract__client", "act_date")
    search_fields = ("contract__client__org_name_short",)
    date_hierarchy = "act_date"
    list_per_page = 500
    actions = ["download_zip", "regenerate_selected", "mark_paid", "mark_unpaid"]

    def contract_link(self, obj):
        url = f"/admin/contracts/contract/{obj.contract.pk}/change/"
        return format_html('<a href="{}">№{}</a>', url, obj.contract.number)
    contract_link.short_description = "Договор"

    def client_name(self, obj):
        return obj.contract.client.org_name_short
    client_name.short_description = "Клиент"
    client_name.admin_order_field = "contract__client__org_name_short"

    def paid_status(self, obj):
        if obj.is_paid:
            label = f"Оплачен {obj.paid_date:%d.%m.%Y}" if obj.paid_date else "Оплачен"
            return format_html('<span style="color:green;font-weight:bold">{}</span>', label)
        return format_html('<span style="color:red">Не оплачен</span>')
    paid_status.short_description = "Статус"

    def download_act_link(self, obj):
        url = f"/admin/contracts/act/{obj.pk}/download/"
        return format_html('<a class="button" href="{}">Скачать .docx</a>', url)
    download_act_link.short_description = "Файл"

    def _calculate_act_amount(self, act):
        try:
            amount = convert_to_byn(
                act.contract.monthly_amount,
                act.contract.currency,
                act.act_date,
            )
            return amount, None
        except Exception as exc:
            return act.contract.monthly_amount, exc

    def _regenerate_acts(self, request, queryset):
        updated = 0
        errors = []

        for act in queryset.select_related("contract__client"):
            amount, error = self._calculate_act_amount(act)
            changed_fields = []

            if act.amount != amount:
                act.amount = amount
                changed_fields.append("amount")

            if changed_fields:
                act.save(update_fields=changed_fields)
            updated += 1

            if error is not None:
                errors.append(f"{act.contract.client.org_name_short} ({act.act_date:%d.%m.%Y}): {error}")

        if updated:
            messages.success(request, f"Перегенерировано актов: {updated}.")
        if errors:
            messages.warning(
                request,
                "Для части актов курс не получен, оставлена сумма договора: " + "; ".join(errors),
            )

    # ─── Действия ─────────────────────────────────────────────────────────────

    @admin.action(description="Скачать выбранные акты (.zip)")
    def download_zip(self, request, queryset):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            for act in queryset.select_related("contract__client"):
                docx_buf, filename = build_act(
                    act.contract.number, act.contract.date, act.act_date,
                    act.contract.client.to_dict(), float(act.amount),
                    act.contract.service_desc, to_file=False,
                )
                zf.writestr(filename, docx_buf.read())
        buf.seek(0)
        response = HttpResponse(buf.read(), content_type="application/zip")
        response["Content-Disposition"] = 'attachment; filename="acts.zip"'
        return response

    @admin.action(description="Перегенерировать выбранные акты")
    def regenerate_selected(self, request, queryset):
        self._regenerate_acts(request, queryset)

    @admin.action(description="Отметить оплаченными (сегодня)")
    def mark_paid(self, request, queryset):
        updated = queryset.filter(is_paid=False).update(
            is_paid=True, paid_date=date.today()
        )
        messages.success(request, f"Отмечено оплаченными: {updated} акт(ов).")

    @admin.action(description="Снять отметку об оплате")
    def mark_unpaid(self, request, queryset):
        updated = queryset.update(is_paid=False, paid_date=None)
        messages.success(request, f"Снята отметка об оплате: {updated} акт(ов).")

    # ─── Группировка месяц → клиент ──────────────────────────────────────────

    def _build_grouped_acts(self, qs):
        from decimal import Decimal
        acts = list(
            qs.select_related("contract__client")
            .order_by("-act_date", "contract__client__org_name_short")
        )
        groups = []
        current_key = None
        current_group = None
        for act in acts:
            key = (act.act_date.year, act.act_date.month)
            if key != current_key:
                if current_group is not None:
                    groups.append(current_group)
                current_group = {
                    "month_label": f"{MONTH_NAMES_RU[act.act_date.month - 1]} {act.act_date.year}",
                    "year": act.act_date.year,
                    "month": act.act_date.month,
                    "total_sum": Decimal("0"),
                    "unpaid_sum": Decimal("0"),
                    "total_cnt": 0,
                    "paid_cnt": 0,
                    "acts": [],
                }
                current_key = key
            current_group["acts"].append({
                "id": act.pk,
                "client": act.contract.client.org_name_short,
                "act_date": act.act_date,
                "amount": act.amount,
                "is_paid": act.is_paid,
                "paid_date": act.paid_date,
                "contract_pk": act.contract.pk,
                "contract_number": act.contract.number,
                "toggle_url": f"/admin/contracts/act/{act.pk}/toggle_paid/",
                "download_url": f"/admin/contracts/act/{act.pk}/download/",
                "regenerate_url": f"/admin/contracts/act/{act.pk}/regenerate/",
                "edit_url": f"/admin/contracts/act/{act.pk}/change/",
            })
            current_group["total_sum"] += act.amount
            current_group["total_cnt"] += 1
            if act.is_paid:
                current_group["paid_cnt"] += 1
            else:
                current_group["unpaid_sum"] += act.amount
        if current_group is not None:
            groups.append(current_group)
        for g in groups:
            g["all_paid"] = g["total_cnt"] > 0 and g["paid_cnt"] == g["total_cnt"]
            g["mark_month_paid_url"] = (
                f"/admin/contracts/act/mark_month_paid/"
                f"?year={g['year']}&month={g['month']}"
            )
            g["create_acts_url"] = (
                f"/admin/contracts/act/create_month_acts/"
                f"?year={g['year']}&month={g['month']}"
            )
            g["download_month_url"] = (
                f"/admin/contracts/act/download_month_acts/"
                f"?year={g['year']}&month={g['month']}"
            )
        return groups

    # ─── Итоги внизу списка ───────────────────────────────────────────────────

    def changelist_view(self, request, extra_context=None):
        response = super().changelist_view(request, extra_context)
        try:
            qs = response.context_data["cl"].queryset
        except (AttributeError, KeyError):
            return response

        totals = qs.aggregate(
            total_sum=Sum("amount"),
            paid_sum=Sum("amount", filter=Q(is_paid=True)),
            unpaid_sum=Sum("amount", filter=Q(is_paid=False)),
            total_cnt=Count("id"),
            paid_cnt=Count("id", filter=Q(is_paid=True)),
            unpaid_cnt=Count("id", filter=Q(is_paid=False)),
        )
        response.context_data["totals"] = totals
        response.context_data["grouped_acts"] = self._build_grouped_acts(qs)
        response.context_data["action_checkbox_name"] = helpers.ACTION_CHECKBOX_NAME
        return response

    class Media:
        css = {"all": ("contracts/admin_totals.css",)}

    def get_urls(self):
        from django.urls import path
        urls = super().get_urls()
        custom = [
            path("<int:pk>/download/",
                 self.admin_site.admin_view(self.download_act),
                 name="act_download"),
            path("<int:pk>/regenerate/",
                 self.admin_site.admin_view(self.regenerate_act),
                 name="act_regenerate"),
            path("<int:pk>/toggle_paid/",
                 self.admin_site.admin_view(self.toggle_paid),
                 name="act_toggle_paid"),
            path("mark_month_paid/",
                 self.admin_site.admin_view(self.mark_month_paid),
                 name="act_mark_month_paid"),
            path("create_month_acts/",
                 self.admin_site.admin_view(self.create_month_acts),
                 name="act_create_month_acts"),
            path("download_month_acts/",
                 self.admin_site.admin_view(self.download_month_acts),
                 name="act_download_month_acts"),
            path("create_month_form/",
                 self.admin_site.admin_view(self.create_month_form),
                 name="act_create_month_form"),
        ]
        return custom + urls

    def toggle_paid(self, request, pk):
        from django.shortcuts import redirect
        act = Act.objects.get(pk=pk)
        if act.is_paid:
            act.is_paid = False
            act.paid_date = None
        else:
            act.is_paid = True
            act.paid_date = date.today()
        act.save()
        return redirect(request.META.get("HTTP_REFERER", "/admin/contracts/act/"))

    def regenerate_act(self, request, pk):
        from django.shortcuts import redirect

        self._regenerate_acts(request, Act.objects.filter(pk=pk))
        return redirect(request.META.get("HTTP_REFERER", "/admin/contracts/act/"))

    def mark_month_paid(self, request):
        from django.shortcuts import redirect
        year = int(request.GET["year"])
        month = int(request.GET["month"])
        updated = Act.objects.filter(
            act_date__year=year, act_date__month=month, is_paid=False
        ).update(is_paid=True, paid_date=date.today())
        messages.success(request, f"Отмечено оплаченными: {updated} акт(ов).")
        return redirect(request.META.get("HTTP_REFERER", "/admin/contracts/act/"))

    def create_month_acts(self, request):
        from django.shortcuts import redirect
        import calendar
        year = int(request.GET["year"])
        month = int(request.GET["month"])
        last_day = date(year, month, calendar.monthrange(year, month)[1])
        existing = set(
            Act.objects.filter(act_date__year=year, act_date__month=month)
            .values_list("contract_id", flat=True)
        )
        to_create = []
        for contract in Contract.objects.select_related("client").all():
            if contract.id in existing:
                continue
            try:
                amount = convert_to_byn(contract.monthly_amount, contract.currency, last_day)
            except Exception:
                amount = contract.monthly_amount
            to_create.append(Act(contract=contract, act_date=last_day, amount=amount, is_paid=False))
        if to_create:
            Act.objects.bulk_create(to_create)
            messages.success(request, f"Создано актов за {month:02d}.{year}: {len(to_create)}.")
        else:
            messages.info(request, f"Все акты за {month:02d}.{year} уже существуют.")
        return redirect(request.META.get("HTTP_REFERER", "/admin/contracts/act/"))

    def create_month_form(self, request):
        from django.shortcuts import render, redirect
        import calendar
        today = date.today()

        if request.method == "POST":
            year = int(request.POST["year"])
            month = int(request.POST["month"])
            last_day = date(year, month, calendar.monthrange(year, month)[1])
            existing = set(
                Act.objects.filter(act_date__year=year, act_date__month=month)
                .values_list("contract_id", flat=True)
            )
            to_create = []
            for contract in Contract.objects.select_related("client").all():
                if contract.id in existing:
                    continue
                try:
                    amount = convert_to_byn(contract.monthly_amount, contract.currency, last_day)
                except Exception:
                    amount = contract.monthly_amount
                to_create.append(Act(contract=contract, act_date=last_day, amount=amount, is_paid=False))
            if to_create:
                Act.objects.bulk_create(to_create)
                messages.success(request, f"Создано актов за {month:02d}.{year}: {len(to_create)}.")
            else:
                messages.info(request, f"Все акты за {month:02d}.{year} уже существуют.")
            return redirect("/admin/contracts/act/")

        month_names = [
            "Январь", "Февраль", "Март", "Апрель", "Май", "Июнь",
            "Июль", "Август", "Сентябрь", "Октябрь", "Ноябрь", "Декабрь",
        ]
        context = dict(
            self.admin_site.each_context(request),
            title="Сформировать акты за месяц",
            months=[(i, month_names[i - 1]) for i in range(1, 13)],
            years=list(range(today.year - 1, today.year + 2)),
            current_month=today.month,
            current_year=today.year,
        )
        return render(request, "contracts/create_month_form.html", context)

    def download_month_acts(self, request):
        from django.shortcuts import redirect
        year = int(request.GET["year"])
        month = int(request.GET["month"])
        acts = Act.objects.filter(
            act_date__year=year, act_date__month=month
        ).select_related("contract__client").order_by("contract__client__org_name_short")
        if not acts.exists():
            messages.warning(request, f"Актов за {month:02d}.{year} нет.")
            return redirect(request.META.get("HTTP_REFERER", "/admin/contracts/act/"))
        acts_params = [{
            "contract_num":  a.contract.number,
            "contract_date": a.contract.date,
            "act_date":      a.act_date,
            "client_dict":   a.contract.client.to_dict(),
            "amount":        float(a.amount),
            "service_desc":  a.contract.service_desc,
        } for a in acts]
        filename = f"Акты_{month:02d}_{year}.docx"
        buf, _ = build_acts_combined(acts_params, filename, to_file=False)
        response = HttpResponse(buf.read(), content_type=(
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        ))
        response["Content-Disposition"] = (
            f'attachment; filename="{filename.encode("utf-8").decode("latin-1", errors="replace")}"'
        )
        return response

    def download_act(self, request, pk):
        act = Act.objects.select_related("contract__client").get(pk=pk)
        buf, filename = build_act(
            act.contract.number, act.contract.date, act.act_date,
            act.contract.client.to_dict(), float(act.amount),
            act.contract.service_desc, to_file=False,
        )
        response = HttpResponse(buf.read(), content_type=(
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        ))
        response["Content-Disposition"] = (
            f'attachment; filename="{filename.encode("utf-8").decode("latin-1", errors="replace")}"'
        )
        return response
