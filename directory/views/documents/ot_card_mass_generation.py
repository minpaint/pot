# directory/views/documents/ot_card_mass_generation.py
"""
📋 Массовая генерация личных карточек по охране труда
"""
import io
import re
import zipfile
import logging
from datetime import datetime, date

from django.views.generic import ListView
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST
from django.http import HttpResponse
from django.db.models import Q, Count, Value, IntegerField, OuterRef, Subquery
from django.db.models.functions import Coalesce

from directory.models import Employee, Organization, StructuralSubdivision
from directory.utils.permissions import AccessControlHelper
from directory.document_generators.ot_card_generator import generate_personal_ot_card

logger = logging.getLogger(__name__)

# Виды инструктажей (без вводного - он проводится всегда при приёме)
INSTRUCTION_TYPE_CHOICES = [
    ('Повторный', 'Повторный'),
    ('Внеплановый', 'Внеплановый'),
    ('Целевой', 'Целевой'),
]


def _get_employees_without_subdivision(accessible_orgs):
    """
    Возвращает организации, у которых есть активные сотрудники с должностью,
    но не привязанные ни к одному структурному подразделению.
    Результат — список словарей с данными организации и количеством таких сотрудников.
    """
    # Сотрудники без подразделения: subdivision=None, position не привязана к подразделению
    employees_qs = Employee.objects.filter(
        status='active',
        position__isnull=False,
        organization__in=accessible_orgs,
        subdivision__isnull=True,
        position__subdivision__isnull=True,
        position__department__isnull=True,
    )

    # Группируем по организации
    org_counts = (
        employees_qs
        .values('organization_id')
        .annotate(employees_count=Count('id'))
        .filter(employees_count__gt=0)
    )

    org_ids = [item['organization_id'] for item in org_counts]
    counts_map = {item['organization_id']: item['employees_count'] for item in org_counts}

    orgs = Organization.objects.filter(id__in=org_ids).order_by('full_name_ru')

    result = []
    for org in orgs:
        result.append({
            'organization': org,
            'employees_count': counts_map[org.id],
        })
    return result


class OTCardMassGenerationView(LoginRequiredMixin, ListView):
    """
    📋 Личные карточки по ОТ - массовая генерация по структурным подразделениям
    """
    model = StructuralSubdivision
    template_name = 'directory/ot_card/mass_generation.html'
    context_object_name = 'subdivisions'

    def get_queryset(self):
        """Получаем подразделения с активными сотрудниками"""
        accessible_orgs = AccessControlHelper.get_accessible_organizations(
            self.request.user, self.request
        )

        # Subquery для подсчёта активных сотрудников с должностью
        employees_count = Employee.objects.filter(
            status='active',
            position__isnull=False,
        ).filter(
            Q(position__department__subdivision=OuterRef('pk')) |
            Q(position__subdivision=OuterRef('pk')) |
            Q(subdivision=OuterRef('pk'))
        ).order_by().values(
            dummy=Value(1)
        ).annotate(
            count=Count('id', distinct=True)
        ).values('count')

        queryset = StructuralSubdivision.objects.filter(
            organization__in=accessible_orgs
        ).annotate(
            employees_count=Coalesce(
                Subquery(employees_count, output_field=IntegerField()),
                0
            )
        ).filter(
            employees_count__gt=0
        ).select_related('organization').order_by('organization__full_name_ru', 'name')

        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['title'] = 'Личные карточки по охране труда'
        context['instruction_types'] = INSTRUCTION_TYPE_CHOICES
        context['default_date'] = date.today().strftime('%Y-%m-%d')

        # Организации с сотрудниками без подразделений
        accessible_orgs = AccessControlHelper.get_accessible_organizations(
            self.request.user, self.request
        )
        context['orgs_no_subdivision'] = _get_employees_without_subdivision(accessible_orgs)

        # Собираем все организации для dropdown (из подразделений + без подразделений)
        all_org_ids = set()
        for sub in context['subdivisions']:
            all_org_ids.add(sub.organization_id)
        for item in context['orgs_no_subdivision']:
            all_org_ids.add(item['organization'].id)
        context['all_organizations'] = Organization.objects.filter(
            id__in=all_org_ids
        ).order_by('full_name_ru')

        return context


@login_required
@require_POST
def generate_ot_cards_bulk(request):
    """
    📋 Генерация ZIP-архива с личными карточками по ОТ для выбранных подразделений и организаций
    """
    subdivision_ids = request.POST.getlist('subdivision_ids')
    organization_ids = request.POST.getlist('organization_ids')
    instruction_date = (
        request.POST.get('date_povtorny')
        or request.POST.get('instruction_date')
        or ''
    )
    instruction_type = request.POST.get('instruction_type') or 'Повторный'
    instruction_reason = request.POST.get('instruction_reason') or ''

    if not subdivision_ids and not organization_ids:
        return HttpResponse("Не выбрано ни одного подразделения", status=400)

    # Форматируем дату
    instruction_date_display = ''
    if instruction_date:
        try:
            instruction_date_display = datetime.strptime(instruction_date, '%Y-%m-%d').strftime('%d.%m.%Y')
        except ValueError:
            instruction_date_display = instruction_date

    # Контекст для шаблона DOCX
    custom_context = {
        'instruction_date': instruction_date_display,
        'instruction_type': instruction_type,
        'instruction_reason': instruction_reason,
    }

    # Создаём ZIP-архив в памяти
    zip_buffer = io.BytesIO()

    with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
        generated_count = 0
        errors = []

        for subdivision_id in subdivision_ids:
            try:
                subdivision = StructuralSubdivision.objects.get(pk=subdivision_id)

                # Получаем всех активных сотрудников подразделения с должностью
                employees = Employee.objects.filter(
                    status='active',
                    position__isnull=False,
                ).filter(
                    Q(position__department__subdivision=subdivision) |
                    Q(position__subdivision=subdivision) |
                    Q(subdivision=subdivision)
                ).select_related(
                    'position',
                    'organization',
                    'subdivision',
                    'department',
                ).distinct()

                for employee in employees:
                    # Генерируем карточку
                    try:
                        result = generate_personal_ot_card(
                            employee,
                            user=request.user,
                            custom_context=custom_context,
                        )
                    except Exception as e:
                        errors.append(f"Ошибка генерации для {employee.full_name_nominative}: {e}")
                        logger.error(f"Ошибка генерации карточки ОТ для {employee.full_name_nominative}: {e}")
                        continue

                    if result and 'content' in result:
                        # Формируем безопасное имя файла
                        safe_subdivision = re.sub(r'[<>:"/\\|?*]', '_', subdivision.name)
                        safe_employee = re.sub(r'[<>:"/\\|?*]', '_', employee.full_name_nominative)

                        # Добавляем файл в архив
                        file_path = f"{safe_subdivision}/{safe_employee}_личная_карточка_ОТ.docx"
                        zip_file.writestr(file_path, result['content'])
                        generated_count += 1

                        logger.info(f"Добавлена карточка ОТ: {file_path}")
                    else:
                        errors.append(f"Ошибка генерации для {employee.full_name_nominative}: результат пустой")

            except StructuralSubdivision.DoesNotExist:
                errors.append(f"Подразделение ID={subdivision_id} не найдено")
            except Exception as e:
                logger.error(f"Ошибка при обработке подразделения {subdivision_id}: {e}")
                errors.append(f"Ошибка подразделения ID={subdivision_id}: {str(e)}")

        # Генерация для организаций без подразделений
        for org_id in organization_ids:
            try:
                org = Organization.objects.get(pk=org_id)

                employees = Employee.objects.filter(
                    status='active',
                    position__isnull=False,
                    organization=org,
                    subdivision__isnull=True,
                    position__subdivision__isnull=True,
                    position__department__isnull=True,
                ).select_related(
                    'position',
                    'organization',
                ).distinct()

                safe_org = re.sub(r'[<>:"/\\|?*]', '_', org.short_name_ru or org.full_name_ru)
                folder_name = f"{safe_org} (без подразделения)"

                for employee in employees:
                    try:
                        result = generate_personal_ot_card(
                            employee,
                            user=request.user,
                            custom_context=custom_context,
                        )
                    except Exception as e:
                        errors.append(f"Ошибка генерации для {employee.full_name_nominative}: {e}")
                        logger.error(f"Ошибка генерации карточки ОТ для {employee.full_name_nominative}: {e}")
                        continue

                    if result and 'content' in result:
                        safe_employee = re.sub(r'[<>:"/\\|?*]', '_', employee.full_name_nominative)
                        file_path = f"{folder_name}/{safe_employee}_личная_карточка_ОТ.docx"
                        zip_file.writestr(file_path, result['content'])
                        generated_count += 1
                        logger.info(f"Добавлена карточка ОТ: {file_path}")
                    else:
                        errors.append(f"Ошибка генерации для {employee.full_name_nominative}: результат пустой")

            except Organization.DoesNotExist:
                errors.append(f"Организация ID={org_id} не найдена")
            except Exception as e:
                logger.error(f"Ошибка при обработке организации {org_id}: {e}")
                errors.append(f"Ошибка организации ID={org_id}: {str(e)}")

        # Добавляем файл со сводкой
        summary = f"""Массовая генерация личных карточек по охране труда
Дата генерации: {datetime.now().strftime('%d.%m.%Y %H:%M')}
Вид инструктажа: {instruction_type}
Дата инструктажа: {instruction_date_display or 'не указана'}
{f'Причина: {instruction_reason}' if instruction_reason else ''}
Сгенерировано карточек: {generated_count}

"""
        if errors:
            summary += "Ошибки:\n" + "\n".join(errors)

        zip_file.writestr("_summary.txt", summary.encode('utf-8'))

    # Отправляем архив пользователю
    zip_buffer.seek(0)
    response = HttpResponse(zip_buffer.read(), content_type='application/zip')

    # Формируем имя файла
    filename = f"Личные_карточки_ОТ_{datetime.now().strftime('%Y%m%d_%H%M%S')}.zip"
    response['Content-Disposition'] = f'attachment; filename="{filename}"'

    logger.info(f"Массовая генерация карточек ОТ завершена. Создано файлов: {generated_count}")

    return response
