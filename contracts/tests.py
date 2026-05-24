from datetime import date
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from .models import Act, Client, Contract


class ActAdminTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_superuser(
            username="admin",
            email="admin@example.com",
            password="password123",
        )
        self.client.force_login(self.user)

        self.client_obj = Client.objects.create(
            org_name="Общество с ограниченной ответственностью Тест",
            org_name_short="ООО Тест",
            director_name="Иванова Ивана Ивановича",
            director_initials="И.И. Иванов",
            director_basis="Устава",
            unp="123456789",
            okpo="12345678",
            address="г. Минск, ул. Тестовая, 1",
            account="BY00TEST00000000000000000000",
            bank="Тест Банк",
            bank_branch="ЦБУ №1",
            bic="TESTBY2X",
            bank_city="г. Минск",
            phone="+375291112233",
            email="client@example.com",
        )
        self.contract = Contract.objects.create(
            date=date(2026, 1, 15),
            client=self.client_obj,
            monthly_amount=Decimal("400.00"),
            currency=Contract.CURRENCY_USD,
            service_desc="Тестовые услуги",
        )
        self.act = Act.objects.create(
            contract=self.contract,
            act_date=date(2026, 1, 31),
            amount=Decimal("400.00"),
            is_paid=False,
        )

    def test_regenerate_selected_action_updates_amount(self):
        changelist_url = reverse("admin:contracts_act_changelist")

        with patch("contracts.admin.convert_to_byn", return_value=Decimal("512.34")):
            response = self.client.post(
                changelist_url,
                {
                    "action": "regenerate_selected",
                    "_selected_action": [self.act.pk],
                    "index": 0,
                },
                follow=True,
            )

        self.assertEqual(response.status_code, 200)
        self.act.refresh_from_db()
        self.assertEqual(self.act.amount, Decimal("512.34"))
        messages = list(response.context["messages"])
        self.assertTrue(any("Перегенерировано актов: 1." in str(message) for message in messages))

    def test_act_changelist_shows_bulk_checkbox_and_regenerate_link(self):
        response = self.client.get(reverse("admin:contracts_act_changelist"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'name="_selected_action"')
        self.assertContains(response, reverse("admin:act_regenerate", args=[self.act.pk]), html=False)
