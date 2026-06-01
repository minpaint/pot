from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from deadline_control.models import Equipment, EquipmentType
from directory.document_generators.equipment_journal_generator import _build_equipment_records
from directory.models import Organization


class EquipmentJournalGeneratorTests(TestCase):
    def setUp(self):
        self.organization = Organization.objects.create(
            full_name_ru="Тестовая организация",
            short_name_ru="ТестОрг",
            full_name_by="Тэставая арганізацыя",
            short_name_by="ТэстАрг",
        )
        self.cart_type, _ = EquipmentType.objects.get_or_create(
            name="Грузовая тележка",
            defaults={"default_maintenance_period_months": 12},
        )

    def test_cart_journal_uses_equipment_name_in_type_column(self):
        equipment = Equipment.objects.create(
            equipment_name="Тележка гидравлическая TOR JC 2000",
            inventory_number="TG-001",
            equipment_type=self.cart_type,
            organization=self.organization,
        )

        records = _build_equipment_records([equipment])

        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["type"], "Тележка гидравлическая TOR JC 2000")

    def test_non_cart_journal_keeps_equipment_type_name(self):
        ladder_type, _ = EquipmentType.objects.get_or_create(
            name="Погрузчик",
            defaults={"default_maintenance_period_months": 12},
        )
        equipment = Equipment.objects.create(
            equipment_name="Погрузчик STILL RX20",
            inventory_number="PG-001",
            equipment_type=ladder_type,
            organization=self.organization,
        )

        records = _build_equipment_records([equipment])

        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["type"], "Погрузчик")


class EquipmentJournalDownloadViewTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="equipment-user",
            password="testpass123",
        )
        self.organization = Organization.objects.create(
            full_name_ru="Тестовая организация",
            short_name_ru="ТестОрг",
            full_name_by="Тэставая арганізацыя",
            short_name_by="ТэстАрг",
        )
        self.user.profile.organizations.add(self.organization)
        self.client.login(username="equipment-user", password="testpass123")
        session = self.client.session
        session["selected_org_id"] = self.organization.id
        session.save()

    @patch("directory.document_generators.equipment_journal_generator.generate_equipment_journal")
    def test_download_cart_journal_returns_attachment(self, mock_generate_equipment_journal):
        EquipmentType.objects.get_or_create(
            name="Грузовая тележка",
            defaults={"default_maintenance_period_months": 12},
        )
        mock_generate_equipment_journal.return_value = {
            "content": b"test-docx",
            "filename": "journal.docx",
        }

        response = self.client.get(
            reverse("deadline_control:equipment:download_cart_journal"),
            {"inspection_date": "2026-04-02"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response["Content-Type"],
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        )
        self.assertIn('attachment; filename="journal.docx"', response["Content-Disposition"])
        mock_generate_equipment_journal.assert_called_once()
