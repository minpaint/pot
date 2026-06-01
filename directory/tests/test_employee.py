from django.test import TestCase
from django.urls import reverse
from django.contrib.auth.models import User
from unittest.mock import patch, sentinel

from directory.document_generators.familiarization_generator import (
    generate_familiarization_document,
)
from directory.forms.position import PositionForm
from directory.models import Organization, Employee, Position, Document


class EmployeeTests(TestCase):
    def setUp(self):
        # Создаем тестового пользователя
        self.user = User.objects.create_user(
            username='testuser',
            password='testpass123'
        )

        # Создаем тестовую организацию
        self.org = Organization.objects.create(
            full_name_ru="Тестовая организация",
            short_name_ru="ТестОрг",
            full_name_by="Тэставая арганізацыя",
            short_name_by="ТэстАрг"
        )

        # Создаем тестовую должность
        self.position = Position.objects.create(
            position_name="Тестовая должность",
            organization=self.org
        )

        self.user.profile.organizations.add(self.org)
        self.client.login(username='testuser', password='testpass123')

    def test_employee_list_view(self):
        """Тест списка сотрудников"""
        response = self.client.get(reverse('directory:employee_list'))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'directory/employees/list.html')

    def test_employee_create_view(self):
        """Тест создания сотрудника"""
        form_data = {
            'full_name_nominative': 'Иванов Иван Иванович',
            'full_name_dative': 'Иванову Ивану Ивановичу',
            'date_of_birth': '1990-01-01',
            'organization': self.org.id,
            'position': self.position.id,
            'place_of_residence': 'г. Минск'
        }

        response = self.client.post(
            reverse('directory:employee_create'),
            form_data
        )

        self.assertRedirects(
            response,
            reverse('directory:employee_list'),
            status_code=302
        )

    def test_employee_update_view(self):
        """Тест обновления сотрудника"""
        employee = Employee.objects.create(
            full_name_nominative='Тест Тестович',
            full_name_dative='Тесту Тестовичу',
            date_of_birth='1990-01-01',
            organization=self.org,
            position=self.position,
            place_of_residence='г. Минск'
        )

        form_data = {
            'full_name_nominative': 'Новый Тест Тестович',
            'full_name_dative': 'Новому Тесту Тестовичу',
            'date_of_birth': '1990-01-01',
            'organization': self.org.id,
            'position': self.position.id,
            'place_of_residence': 'г. Минск'
        }

        response = self.client.post(
            reverse('directory:employee_update', kwargs={'pk': employee.pk}),
            form_data
        )

        self.assertRedirects(
            response,
            reverse('directory:employee_list'),
            status_code=302
        )


class EmployeeDeleteViewTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='delete-user',
            password='testpass123'
        )
        self.organization = Organization.objects.create(
            full_name_ru="Тестовая организация",
            short_name_ru="ТестОрг",
            full_name_by="Тэставая арганізацыя",
            short_name_by="ТэстАрг"
        )
        self.position = Position.objects.create(
            position_name="Тестовая должность",
            organization=self.organization
        )
        self.employee = Employee.objects.create(
            full_name_nominative="Иванов Иван Иванович",
            organization=self.organization,
            position=self.position
        )

        self.user.profile.organizations.add(self.organization)
        self.client.login(username='delete-user', password='testpass123')

    def test_employee_delete_page_renders(self):
        response = self.client.get(
            reverse(
                'directory:employees:employee_delete',
                kwargs={'pk': self.employee.pk}
            )
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            reverse('directory:employees:employee_list')
        )

    def test_employee_delete_post_marks_employee_for_deletion(self):
        response = self.client.post(
            reverse(
                'directory:employees:employee_delete',
                kwargs={'pk': self.employee.pk}
            )
        )

        self.assertRedirects(
            response,
            reverse('directory:employees:employee_list')
        )

        self.employee.refresh_from_db()
        self.assertTrue(Employee.objects.filter(pk=self.employee.pk).exists())
        self.assertTrue(self.employee.marked_for_deletion)
        self.assertIsNotNone(self.employee.marked_for_deletion_at)

        list_response = self.client.get(reverse('directory:employees:employee_list'))
        self.assertNotContains(list_response, self.employee.full_name_nominative)

        profile_response = self.client.get(
            reverse(
                'directory:employees:employee_profile',
                kwargs={'pk': self.employee.pk}
            )
        )
        self.assertEqual(profile_response.status_code, 404)


class FamiliarizationGeneratorTests(TestCase):
    def setUp(self):
        self.organization = Organization.objects.create(
            full_name_ru="Тестовая организация",
            short_name_ru="ТестОрг",
            full_name_by="Тэставая арганізацыя",
            short_name_by="ТэстАрг"
        )
        self.position = Position.objects.create(
            position_name="Тестовая должность",
            organization=self.organization
        )
        self.employee = Employee.objects.create(
            full_name_nominative="Иванов Иван Иванович",
            organization=self.organization,
            position=self.position
        )

    @patch(
        "directory.document_generators.familiarization_generator.get_document_template",
        return_value=sentinel.template,
    )
    @patch(
        "directory.document_generators.familiarization_generator.prepare_employee_context",
        return_value={"current_date": "15.03.2026"},
    )
    @patch(
        "directory.document_generators.familiarization_generator.generate_docx_from_template"
    )
    @patch(
        "directory.views.documents.utils.get_employee_documents",
        return_value=(None, False),
    )
    def test_familiarization_document_not_generated_without_documents(
        self,
        mock_get_employee_documents,
        mock_generate_docx_from_template,
        mock_prepare_employee_context,
        mock_get_document_template,
    ):
        result = generate_familiarization_document(self.employee)

        self.assertIsNone(result)
        mock_get_document_template.assert_called_once_with(
            "doc_familiarization",
            self.employee,
        )
        mock_prepare_employee_context.assert_called_once_with(self.employee)
        mock_get_employee_documents.assert_called_once_with(self.employee)
        mock_generate_docx_from_template.assert_not_called()

    @patch(
        "directory.document_generators.familiarization_generator.get_document_template",
        return_value=sentinel.template,
    )
    @patch(
        "directory.document_generators.familiarization_generator.prepare_employee_context",
        return_value={"current_date": "15.03.2026"},
    )
    @patch(
        "directory.document_generators.familiarization_generator.generate_docx_from_template",
        return_value={"content": b"test", "filename": "familiarization.docx"},
    )
    @patch(
        "directory.views.documents.utils.get_employee_documents",
        return_value=(["ПВТР", "Инструкция по ОТ"], True),
    )
    def test_familiarization_document_uses_employee_documents(
        self,
        mock_get_employee_documents,
        mock_generate_docx_from_template,
        mock_prepare_employee_context,
        mock_get_document_template,
    ):
        result = generate_familiarization_document(self.employee)

        self.assertEqual(
            result,
            {"content": b"test", "filename": "familiarization.docx"},
        )
        mock_get_document_template.assert_called_once_with(
            "doc_familiarization",
            self.employee,
        )
        mock_prepare_employee_context.assert_called_once_with(self.employee)
        mock_get_employee_documents.assert_called_once_with(self.employee)
        mock_generate_docx_from_template.assert_called_once()

        args, kwargs = mock_generate_docx_from_template.call_args
        self.assertIs(args[0], sentinel.template)
        self.assertEqual(
            args[1]["all_documents"],
            ["ПВТР", "Инструкция по ОТ"],
        )
        self.assertEqual(args[1]["documents_list"], "DOCMARKER_START")
        self.assertEqual(args[1]["familiarization_date"], "15.03.2026")
        self.assertIs(args[2], self.employee)
        self.assertIsNone(args[3])
        self.assertEqual(kwargs["post_processor"].__name__, "process_table_rows")


class PositionFormDocumentTests(TestCase):
    def setUp(self):
        self.organization = Organization.objects.create(
            full_name_ru="Тестовая организация",
            short_name_ru="ТестОрг",
            full_name_by="Тэставая арганізацыя",
            short_name_by="ТэстАрг"
        )
        self.position = Position.objects.create(
            position_name="Тестовая должность",
            organization=self.organization
        )
        self.general_document = Document.objects.create(
            name="Общий документ организации",
            organization=self.organization
        )

    def test_position_form_shows_all_organization_documents(self):
        form = PositionForm(instance=self.position)

        self.assertIn(
            self.general_document,
            form.fields["documents"].queryset,
        )
