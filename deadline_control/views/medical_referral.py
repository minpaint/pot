"""
Views для системы выдачи направлений на медицинский осмотр.
"""
import json
import os
from datetime import datetime
from django.http import JsonResponse, FileResponse
from django.views import View
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import get_object_or_404, redirect
from django.core.exceptions import PermissionDenied
from django.conf import settings
from django.core.files.base import ContentFile
from django.utils import timezone
from django.contrib import messages

from directory.models import Employee
from directory.utils.permissions import AccessControlHelper
from deadline_control.models import (
    MedicalReferral,
    PositionMedicalFactor,
    MedicalExaminationNorm,
    HarmfulFactor,
)

try:
    from docxtpl import DocxTemplate
    DOCXTPL_AVAILABLE = True
except ImportError:
    DOCXTPL_AVAILABLE = False


def get_harmful_factors_for_employee(employee):
    """
    Получает вредные факторы для сотрудника с учётом переопределений.

    Приоритет:
    1. Переопределённые факторы для должности в организации (PositionMedicalFactor)
    2. Эталонные факторы по названию должности (MedicalExaminationNorm)
    """
    position = employee.position

    # 1. Проверяем переопределения для конкретной должности
    overridden_factors = PositionMedicalFactor.objects.filter(
        position=position,
        is_disabled=False  # Только активные факторы
    ).select_related('harmful_factor')

    if overridden_factors.exists():
        # Используем переопределённые факторы
        return [pf.harmful_factor for pf in overridden_factors]

    # 2. Если переопределений нет - берём эталонные нормы по названию должности
    reference_norms = MedicalExaminationNorm.objects.filter(
        position_name=position.position_name
    ).select_related('harmful_factor')

    return [norm.harmful_factor for norm in reference_norms]


def get_medical_referral_template(organization):
    """
    Получает шаблон направления на медосмотр для организации.

    Приоритет:
    1. Шаблон организации (DocumentTemplate с document_type.code='medical' и organization=org)
    2. Эталонный шаблон (DocumentTemplate с document_type.code='medical' и is_default=True)

    Возвращает путь к файлу шаблона или None.
    """
    from directory.models import DocumentTemplate, DocumentTemplateType

    try:
        medical_type = DocumentTemplateType.objects.get(code='medical')
    except DocumentTemplateType.DoesNotExist:
        return None

    # 1. Ищем шаблон для конкретной организации
    org_template = DocumentTemplate.objects.filter(
        document_type=medical_type,
        organization=organization,
        is_active=True
    ).first()

    if org_template and org_template.template_file:
        return org_template.template_file.path

    # 2. Ищем эталонный шаблон
    default_template = DocumentTemplate.objects.filter(
        document_type=medical_type,
        is_default=True,
        is_active=True
    ).first()

    if default_template and default_template.template_file:
        return default_template.template_file.path

    return None


def get_accessible_referral_organizations(request):
    return AccessControlHelper.get_accessible_organizations(request.user, request).order_by('short_name_ru', 'full_name_ru')


def get_selected_referral_organization_id(request, organizations, posted_organization_id=None):
    for candidate_id in [posted_organization_id, request.GET.get('organization_id'), request.session.get('selected_org_id')]:
        if candidate_id and organizations.filter(id=candidate_id).exists():
            return int(candidate_id)
    if organizations.count() == 1:
        return organizations.first().id
    return None


def get_referral_position_options(organizations):
    from directory.models import Position
    return list(Position.objects.filter(organization__in=organizations).values('organization_id', 'position_name').distinct().order_by('organization_id', 'position_name'))


def build_new_employee_referral_context(request, organizations, errors=None, form_data=None, selected_organization_id=None):
    form_data = form_data or {}
    if selected_organization_id is None:
        selected_organization_id = get_selected_referral_organization_id(request, organizations, form_data.get('organization_id'))
    return {
        'organizations': organizations,
        'position_options': get_referral_position_options(organizations),
        'selected_organization_id': selected_organization_id,
        'errors': errors or [],
        'form_data': form_data,
    }


def generate_referral_document(referral):
    """
    Генерирует DOCX документ направления на медосмотр.
    Возвращает путь к сгенерированному файлу.
    """
    if not DOCXTPL_AVAILABLE:
        return None

    # Получаем сотрудника из направления
    employee = referral.employee
    organization = employee.organization

    # Получаем путь к шаблону через систему DocumentTemplate
    template_path = get_medical_referral_template(organization)

    if not template_path or not os.path.exists(template_path):
        raise FileNotFoundError(f"Шаблон направления на медосмотр не найден. Создайте эталонный шаблон типа 'medical'.")

    # Загружаем шаблон
    doc = DocxTemplate(template_path)

    # Разбиваем ФИО на части
    name_parts = employee.full_name_nominative.split()
    last_name = name_parts[0] if len(name_parts) > 0 else ''
    first_name = ' '.join(name_parts[1:]) if len(name_parts) > 1 else ''

    # Формируем список вредных факторов (только полное наименование)
    factors_list = []
    for factor in referral.harmful_factors.all():
        factors_list.append(factor.full_name)
    harmful_factors_text = '\n'.join(factors_list) if factors_list else 'Не определены'

    # Контекст для шаблона
    context = {
        'organization_name': organization.full_name_ru,
        'organization_name_by': getattr(organization, 'full_name_by', organization.full_name_ru),
        'requisites_ru': getattr(organization, 'requisites_ru', ''),
        'requisites_by': getattr(organization, 'requisites_by', ''),
        'last_name': last_name,
        'first_name': first_name,
        'full_name': employee.full_name_nominative,
        'date_of_birth': referral.employee_birth_date.strftime('%d.%m.%Y'),
        'address': referral.employee_address,
        'position_name': employee.position.position_name,
        'harmful_factors': harmful_factors_text,
        'issue_date': referral.issue_date.strftime('%d.%m.%Y'),
    }

    # Заполняем шаблон
    doc.render(context)

    # Создаём директорию для сохранения
    save_dir = os.path.join(
        settings.MEDIA_ROOT,
        'medical_referrals',
        str(timezone.now().year),
        str(timezone.now().month).zfill(2)
    )
    os.makedirs(save_dir, exist_ok=True)

    # Имя файла
    filename = f"referral_{referral.id}_{employee.full_name_nominative.replace(' ', '_')}.docx"
    filepath = os.path.join(save_dir, filename)

    # Сохраняем документ
    doc.save(filepath)

    # Сохраняем путь в модели (относительный путь от MEDIA_ROOT)
    relative_path = os.path.relpath(filepath, settings.MEDIA_ROOT)
    referral.document.name = relative_path
    referral.save()

    return filepath


class EmployeeReferralDataView(LoginRequiredMixin, View):
    """
    API endpoint для получения данных сотрудника для формы направления.
    GET /deadline-control/medical/referral/employee/{id}/
    """

    def get(self, request, employee_id):
        # Получаем сотрудника
        employee = get_object_or_404(Employee.objects.active_for_operations(), pk=employee_id)

        # Проверяем права доступа через AccessControlHelper (поддерживает иерархию)
        if not AccessControlHelper.can_access_object(request.user, employee):
            raise PermissionDenied("У вас нет доступа к данному сотруднику")

        # Получаем вредные факторы с учётом приоритета переопределений
        harmful_factors = get_harmful_factors_for_employee(employee)

        # Формируем ответ
        data = {
            'id': employee.id,
            'full_name': employee.full_name_nominative,
            'position': employee.position.position_name,
            'organization': employee.organization.short_name_ru,
            'birth_date': employee.date_of_birth.strftime('%Y-%m-%d') if employee.date_of_birth else '',
            'address': employee.place_of_residence or '',
            'harmful_factors': [
                {
                    'id': factor.id,
                    'short_name': factor.short_name,
                    'full_name': factor.full_name
                }
                for factor in harmful_factors
            ]
        }

        return JsonResponse(data)


@method_decorator(csrf_exempt, name='dispatch')
class GenerateReferralView(LoginRequiredMixin, View):
    """
    API endpoint для генерации направления на медосмотр.
    POST /deadline-control/medical/referral/generate/
    """

    def post(self, request):
        try:
            # Парсим JSON данные
            data = json.loads(request.body)
            employee_id = data.get('employee_id')
            full_name = data.get('full_name', '').strip()
            birth_date_str = data.get('birth_date')
            address = data.get('address', '').strip()

            if not employee_id or not full_name or not birth_date_str or not address:
                return JsonResponse({
                    'success': False,
                    'error': 'Не все обязательные поля заполнены'
                }, status=400)

            # Получаем сотрудника
            employee = get_object_or_404(Employee.objects.active_for_operations(), pk=employee_id)

            # Проверяем права доступа через AccessControlHelper (поддерживает иерархию)
            if not AccessControlHelper.can_access_object(request.user, employee):
                raise PermissionDenied("У вас нет доступа к данному сотруднику")

            # Парсим дату рождения
            birth_date = datetime.strptime(birth_date_str, '%Y-%m-%d').date()

            # Обновляем данные сотрудника, если они изменились
            updated = False
            if employee.full_name_nominative != full_name:
                employee.full_name_nominative = full_name
                updated = True
            if employee.date_of_birth != birth_date:
                employee.date_of_birth = birth_date
                updated = True
            if employee.place_of_residence != address:
                employee.place_of_residence = address
                updated = True
            if updated:
                employee.save()

            # Получаем вредные факторы
            harmful_factors = get_harmful_factors_for_employee(employee)

            # Создаём запись направления
            referral = MedicalReferral.objects.create(
                employee=employee,
                employee_birth_date=birth_date,
                employee_address=address,
                issued_by=request.user
            )

            # Добавляем вредные факторы
            referral.harmful_factors.set(harmful_factors)

            # Генерируем DOCX документ
            document_url = None
            if DOCXTPL_AVAILABLE:
                filepath = generate_referral_document(referral)
                if filepath and referral.document:
                    # Используем URL для скачивания через специальный endpoint
                    from django.urls import reverse
                    document_url = reverse('deadline_control:medical:referral_download', args=[referral.id])

            return JsonResponse({
                'success': True,
                'referral_id': referral.id,
                'message': 'Направление успешно создано',
                'document_url': document_url
            })

        except json.JSONDecodeError:
            return JsonResponse({
                'success': False,
                'error': 'Неверный формат данных'
            }, status=400)
        except Exception as e:
            return JsonResponse({
                'success': False,
                'error': str(e)
            }, status=500)


class DownloadReferralView(LoginRequiredMixin, View):
    """
    Скачивание сгенерированного направления на медосмотр.
    GET /deadline-control/medical/referral/download/{id}/
    """

    def get(self, request, referral_id):
        from urllib.parse import quote

        # Получаем направление
        referral = get_object_or_404(MedicalReferral, pk=referral_id)

        # Проверяем права доступа
        if not AccessControlHelper.can_access_object(request.user, referral.employee):
            raise PermissionDenied("У вас нет доступа к этому направлению")

        # Проверяем, что документ существует
        if not referral.document:
            return JsonResponse({
                'success': False,
                'error': 'Документ не найден'
            }, status=404)

        # Формируем имя файла для скачивания
        employee_name = referral.employee.full_name_nominative.replace(' ', '_')
        filename = f"Направление_на_МО_{employee_name}.docx"

        # Возвращаем файл на скачивание
        response = FileResponse(
            referral.document.open('rb'),
            as_attachment=True,
            content_type='application/vnd.openxmlformats-officedocument.wordprocessingml.document'
        )
        # Для корректной работы с русскими именами файлов
        encoded_filename = quote(filename)
        response['Content-Disposition'] = f"attachment; filename*=UTF-8''{encoded_filename}"
        return response


class ExistingEmployeeReferralView(LoginRequiredMixin, View):
    """
    Форма для выдачи направления на медосмотр существующему сотруднику.
    """

    def get(self, request, employee_id):
        from django.shortcuts import render, get_object_or_404
        from directory.models import Employee

        # Получаем сотрудника
        employee = get_object_or_404(Employee.objects.active_for_operations(), pk=employee_id)

        # Проверяем права доступа через AccessControlHelper (поддерживает иерархию)
        if not AccessControlHelper.can_access_object(request.user, employee):
            messages.error(request, 'У вас нет доступа к этому сотруднику')
            return redirect('deadline_control:medical:list')

        # Получаем вредные факторы для сотрудника
        harmful_factors = get_harmful_factors_for_employee(employee)

        context = {
            'employee': employee,
            'harmful_factors': harmful_factors,
        }
        return render(request, 'deadline_control/existing_employee_referral.html', context)


class NewEmployeeReferralView(LoginRequiredMixin, View):
    """
    Форма для выдачи направления на медосмотр новому сотруднику (до приёма на работу).
    GET: Показать форму
    POST: Генерировать направление
    """

    def get(self, request):
        from django.shortcuts import render

        organizations = get_accessible_referral_organizations(request)
        context = build_new_employee_referral_context(request, organizations)
        return render(request, 'deadline_control/new_employee_referral.html', context)

    def post(self, request):
        from django.shortcuts import render
        from directory.models import Position, Organization

        # Получаем данные из формы
        full_name = request.POST.get('full_name', '').strip()
        birth_date_str = request.POST.get('birth_date', '')
        address = request.POST.get('address', '').strip()
        position_name = request.POST.get('position_name', '')
        organization_id = request.POST.get('organization_id', '')

        errors = []

        # Валидация
        if not full_name:
            errors.append('ФИО обязательно для заполнения')
        if not birth_date_str:
            errors.append('Дата рождения обязательна')
        if not address:
            errors.append('Адрес обязателен')
        if not position_name:
            errors.append('Профессия обязательна')
        if not organization_id:
            errors.append('Организация обязательна')

        organizations = get_accessible_referral_organizations(request)
        form_data = {
            'full_name': full_name,
            'birth_date': birth_date_str,
            'address': address,
            'position_name': position_name,
            'organization_id': organization_id,
        }

        if errors:
            context = build_new_employee_referral_context(
                request,
                organizations,
                errors=errors,
                form_data=form_data,
            )
            return render(request, 'deadline_control/new_employee_referral.html', context)

        try:
            # Парсим дату
            birth_date = datetime.strptime(birth_date_str, '%Y-%m-%d').date()

            # Получаем организацию с учетом прав пользователя
            organization = organizations.get(pk=organization_id)

            # Профессия должна принадлежать выбранной организации, а не любому справочнику
            if not Position.objects.filter(
                organization=organization,
                position_name=position_name,
            ).exists():
                errors.append('Выбранная профессия не принадлежит выбранной организации')
                context = build_new_employee_referral_context(
                    request,
                    organizations,
                    errors=errors,
                    form_data=form_data,
                )
                return render(request, 'deadline_control/new_employee_referral.html', context)

            # Получаем вредные факторы по названию профессии
            harmful_factors = []
            reference_norms = MedicalExaminationNorm.objects.filter(
                position_name=position_name
            ).select_related('harmful_factor')

            for norm in reference_norms:
                harmful_factors.append(norm.harmful_factor)

            if not harmful_factors:
                errors.append(f'Для профессии "{position_name}" не найдены вредные факторы')
                context = build_new_employee_referral_context(
                    request,
                    organizations,
                    errors=errors,
                    form_data=form_data,
                )
                return render(request, 'deadline_control/new_employee_referral.html', context)

            # Создаём направление (без привязки к сотруднику - employee=None)
            # Но модель требует employee, поэтому создадим специальную запись
            # Альтернативно - генерируем документ без сохранения в БД

            # Генерируем DOCX документ напрямую
            if not DOCXTPL_AVAILABLE:
                errors.append('Библиотека docxtpl не установлена')
                context = build_new_employee_referral_context(
                    request,
                    organizations,
                    errors=errors,
                    form_data=form_data,
                )
                return render(request, 'deadline_control/new_employee_referral.html', context)

            # Получаем шаблон через систему DocumentTemplate
            template_path = get_medical_referral_template(organization)

            if not template_path or not os.path.exists(template_path):
                errors.append('Шаблон направления на медосмотр не найден. Создайте эталонный шаблон типа "medical".')
                context = build_new_employee_referral_context(
                    request,
                    organizations,
                    errors=errors,
                    form_data=form_data,
                )
                return render(request, 'deadline_control/new_employee_referral.html', context)

            # Загружаем шаблон
            doc = DocxTemplate(template_path)

            # Разбиваем ФИО на части
            name_parts = full_name.split()
            last_name = name_parts[0] if len(name_parts) > 0 else ''
            first_name = ' '.join(name_parts[1:]) if len(name_parts) > 1 else ''

            # Формируем список вредных факторов
            factors_list = [factor.full_name for factor in harmful_factors]
            harmful_factors_text = '\n'.join(factors_list) if factors_list else 'Не определены'

            # Контекст для шаблона
            context_doc = {
                'organization_name': organization.full_name_ru,
                'organization_name_by': getattr(organization, 'full_name_by', organization.full_name_ru),
                'requisites_ru': getattr(organization, 'requisites_ru', ''),
                'requisites_by': getattr(organization, 'requisites_by', ''),
                'last_name': last_name,
                'first_name': first_name,
                'full_name': full_name,
                'date_of_birth': birth_date.strftime('%d.%m.%Y'),
                'address': address,
                'position_name': position_name,
                'harmful_factors': harmful_factors_text,
                'issue_date': timezone.now().date().strftime('%d.%m.%Y'),
            }

            # Заполняем шаблон
            doc.render(context_doc)

            # Создаём директорию для сохранения
            save_dir = os.path.join(
                settings.MEDIA_ROOT,
                'medical_referrals',
                'new_employees',
                str(timezone.now().year),
                str(timezone.now().month).zfill(2)
            )
            os.makedirs(save_dir, exist_ok=True)

            # Имя файла
            safe_name = full_name.replace(' ', '_').replace('"', '').replace("'", '')
            filename = f"Направление_на_МО_{safe_name}.docx"
            filepath = os.path.join(save_dir, filename)

            # Сохраняем документ
            doc.save(filepath)

            # Возвращаем файл на скачивание
            from urllib.parse import quote
            response = FileResponse(
                open(filepath, 'rb'),
                as_attachment=True,
                filename=filename,
                content_type='application/vnd.openxmlformats-officedocument.wordprocessingml.document'
            )
            # Для корректной работы с русскими именами файлов
            encoded_filename = quote(filename)
            response['Content-Disposition'] = f"attachment; filename*=UTF-8''{encoded_filename}"
            return response

        except Organization.DoesNotExist:
            errors.append('Организация не найдена')
        except Exception as e:
            import traceback
            errors.append(f'Ошибка: {str(e)}')
            # Логируем полную трассировку для отладки
            print(f"Error in NewEmployeeReferralView: {traceback.format_exc()}")

        context = build_new_employee_referral_context(
            request,
            organizations,
            errors=errors,
            form_data=form_data,
        )
        return render(request, 'deadline_control/new_employee_referral.html', context)


class BatchReferralDownloadView(LoginRequiredMixin, View):
    """
    Пакетная генерация направлений на медосмотр для выбранных сотрудников.
    POST: employee_ids[] → валидация → ZIP с DOCX-направлениями или JSON с ошибками.
    """

    def post(self, request):
        import zipfile
        from io import BytesIO
        from urllib.parse import quote
        from django.http import HttpResponse

        employee_ids = request.POST.getlist('employee_ids')
        if not employee_ids:
            return JsonResponse({'success': False, 'error': 'Не выбраны сотрудники'}, status=400)

        employees = list(
            Employee.objects.active_for_operations()
            .filter(id__in=employee_ids)
            .select_related('organization', 'position')
        )

        # Фильтрация по правам
        employees = [e for e in employees if AccessControlHelper.can_access_object(request.user, e)]

        if not employees:
            return JsonResponse({'success': False, 'error': 'Нет доступных сотрудников'}, status=403)

        # Проверяем наличие шаблонов по организациям (кэшируем)
        template_cache = {}
        def get_template(org):
            if org.id not in template_cache:
                template_cache[org.id] = get_medical_referral_template(org)
            return template_cache[org.id]

        # Валидация
        errors = []
        for emp in employees:
            emp_errors = []
            if not emp.date_of_birth:
                emp_errors.append('не указана дата рождения')
            if not emp.place_of_residence or not emp.place_of_residence.strip():
                emp_errors.append('не указан адрес проживания')
            factors = get_harmful_factors_for_employee(emp)
            if not factors:
                emp_errors.append('нет вредных факторов для должности')
            tpl = get_template(emp.organization)
            if not tpl or not os.path.exists(tpl):
                emp_errors.append('не найден шаблон направления для организации')
            if emp_errors:
                errors.append({'name': emp.full_name_nominative, 'issues': emp_errors})

        if errors:
            return JsonResponse({'success': False, 'errors': errors})

        # Генерация ZIP
        zip_buffer = BytesIO()
        with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zf:
            for emp in employees:
                harmful_factors = get_harmful_factors_for_employee(emp)
                template_path = get_template(emp.organization)

                referral = MedicalReferral.objects.create(
                    employee=emp,
                    employee_birth_date=emp.date_of_birth,
                    employee_address=emp.place_of_residence,
                    issued_by=request.user,
                )
                referral.harmful_factors.set(harmful_factors)

                doc = DocxTemplate(template_path)
                name_parts = emp.full_name_nominative.split()
                last_name = name_parts[0] if name_parts else ''
                first_name = ' '.join(name_parts[1:]) if len(name_parts) > 1 else ''
                factors_text = '\n'.join(f.full_name for f in harmful_factors) or 'Не определены'

                doc.render({
                    'organization_name': emp.organization.full_name_ru,
                    'organization_name_by': getattr(emp.organization, 'full_name_by', emp.organization.full_name_ru),
                    'requisites_ru': getattr(emp.organization, 'requisites_ru', ''),
                    'requisites_by': getattr(emp.organization, 'requisites_by', ''),
                    'last_name': last_name,
                    'first_name': first_name,
                    'full_name': emp.full_name_nominative,
                    'date_of_birth': emp.date_of_birth.strftime('%d.%m.%Y'),
                    'address': emp.place_of_residence,
                    'position_name': emp.position.position_name,
                    'harmful_factors': factors_text,
                    'issue_date': timezone.now().date().strftime('%d.%m.%Y'),
                })

                doc_buffer = BytesIO()
                doc.save(doc_buffer)
                doc_bytes = doc_buffer.getvalue()

                # Сохраняем файл направления
                from django.core.files.base import ContentFile
                safe_name = emp.full_name_nominative.replace(' ', '_')
                rel_path = f'medical_referrals/{timezone.now().year}/{timezone.now().month:02d}/referral_{referral.id}_{safe_name}.docx'
                referral.document.save(rel_path, ContentFile(doc_bytes), save=True)

                arcname = f'Направление_{safe_name}.docx'
                zf.writestr(arcname, doc_bytes)

        zip_buffer.seek(0)
        zip_filename = f'Направления_на_МО_{timezone.now().strftime("%d.%m.%Y")}.zip'
        response = HttpResponse(zip_buffer.read(), content_type='application/zip')
        response['Content-Disposition'] = f"attachment; filename*=UTF-8''{quote(zip_filename)}"
        return response
