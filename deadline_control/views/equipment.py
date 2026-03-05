# deadline_control/views/equipment.py
from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import ListView, CreateView, UpdateView, DeleteView, DetailView, TemplateView
from django.urls import reverse_lazy
from django.shortcuts import get_object_or_404, redirect, render
from django.contrib import messages
from django.http import JsonResponse, HttpResponse
from django.utils.dateparse import parse_date
from django.views.decorators.http import require_POST
from django.contrib.auth.decorators import login_required
from collections import defaultdict
from datetime import date

from deadline_control.models import Equipment
from deadline_control.forms import EquipmentForm
from directory.mixins import AccessControlMixin, AccessControlObjectMixin
from directory.utils.permissions import AccessControlHelper
from directory.models import Organization


class EquipmentListView(LoginRequiredMixin, AccessControlMixin, ListView):
    """Табличное представление списка оборудования, сгруппированного по организациям"""
    model = Equipment
    template_name = 'deadline_control/equipment/list.html'
    context_object_name = 'equipment_list'

    def get_queryset(self):
        # AccessControlMixin автоматически фильтрует по правам доступа
        qs = super().get_queryset()
        selected_org_id = self.request.session.get('selected_org_id')
        if selected_org_id:
            qs = qs.filter(organization_id=selected_org_id)
        return qs.select_related('organization', 'subdivision', 'department', 'equipment_type').order_by('organization__short_name_ru', 'equipment_name')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        # Группируем оборудование по организациям
        equipment_by_org = defaultdict(list)
        for equipment in context['equipment_list']:
            equipment_by_org[equipment.organization].append(equipment)

        # Преобразуем в отсортированный список кортежей (организация, список оборудования)
        context['equipment_by_organization'] = sorted(
            equipment_by_org.items(),
            key=lambda x: x[0].short_name_ru or x[0].full_name_ru
        )

        return context


class EquipmentTreeView(LoginRequiredMixin, AccessControlMixin, ListView):
    """
    🌳 Древовидное представление оборудования по организационной структуре
    Иерархия: Организация → Подразделение → Отдел → Оборудование
    """
    model = Equipment
    template_name = 'deadline_control/equipment/tree_view.html'
    context_object_name = 'equipment_list'

    def get_queryset(self):
        # AccessControlMixin автоматически фильтрует по правам доступа
        qs = super().get_queryset()
        selected_org_id = self.request.session.get('selected_org_id')
        if selected_org_id:
            qs = qs.filter(organization_id=selected_org_id)
        return qs.select_related('organization', 'subdivision', 'department', 'equipment_type').order_by(
            'organization__short_name_ru',
            'subdivision__name',
            'department__name',
            'equipment_name'
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['title'] = 'ТО оборудования'

        # Получаем доступные организации
        allowed_orgs = AccessControlHelper.get_accessible_organizations(
            self.request.user, self.request
        )

        # Строим древовидную структуру
        tree_data = self._build_tree_structure(context['equipment_list'], allowed_orgs)
        context['tree_data'] = tree_data

        return context

    def _build_tree_structure(self, equipment_list, allowed_orgs):
        """
        Построение древовидной структуры:
        {
            organization_id: {
                'org': Organization,
                'subdivisions': {
                    subdivision_id: {
                        'sub': Subdivision,
                        'departments': {
                            department_id: {
                                'dept': Department,
                                'equipment': [Equipment, ...]
                            }
                        },
                        'equipment': [Equipment без отдела, ...]
                    }
                },
                'equipment': [Equipment без подразделения, ...]
            }
        }
        """
        tree = {}

        for org in allowed_orgs:
            tree[org.id] = {
                'org': org,
                'subdivisions': {},
                'equipment': []
            }

        for equipment in equipment_list:
            org_id = equipment.organization.id
            if org_id not in tree:
                continue

            # Оборудование без подразделения
            if not equipment.subdivision:
                tree[org_id]['equipment'].append(equipment)
                continue

            sub_id = equipment.subdivision.id
            if sub_id not in tree[org_id]['subdivisions']:
                tree[org_id]['subdivisions'][sub_id] = {
                    'sub': equipment.subdivision,
                    'departments': {},
                    'equipment': []
                }

            # Оборудование без отдела
            if not equipment.department:
                tree[org_id]['subdivisions'][sub_id]['equipment'].append(equipment)
                continue

            dept_id = equipment.department.id
            if dept_id not in tree[org_id]['subdivisions'][sub_id]['departments']:
                tree[org_id]['subdivisions'][sub_id]['departments'][dept_id] = {
                    'dept': equipment.department,
                    'equipment': []
                }

            tree[org_id]['subdivisions'][sub_id]['departments'][dept_id]['equipment'].append(equipment)

        return tree


class EquipmentCreateView(LoginRequiredMixin, CreateView):
    """Создание нового оборудования"""
    model = Equipment
    form_class = EquipmentForm
    template_name = 'deadline_control/equipment/form.html'
    success_url = reverse_lazy('deadline_control:equipment:list')

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['user'] = self.request.user
        return kwargs

    def form_valid(self, form):
        messages.success(self.request, f'Оборудование "{form.instance.equipment_name}" успешно создано')
        return super().form_valid(form)


class EquipmentUpdateView(LoginRequiredMixin, AccessControlObjectMixin, UpdateView):
    """Редактирование оборудования"""
    model = Equipment
    form_class = EquipmentForm
    template_name = 'deadline_control/equipment/form.html'
    success_url = reverse_lazy('deadline_control:equipment:list')

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['user'] = self.request.user
        return kwargs

    def form_valid(self, form):
        messages.success(self.request, f'Оборудование "{form.instance.equipment_name}" успешно обновлено')
        return super().form_valid(form)


class EquipmentDetailView(LoginRequiredMixin, AccessControlObjectMixin, DetailView):
    """Детальная информация об оборудовании"""
    model = Equipment
    template_name = 'deadline_control/equipment/detail.html'
    context_object_name = 'equipment'


class EquipmentDeleteView(LoginRequiredMixin, AccessControlObjectMixin, DeleteView):
    """Удаление оборудования"""
    model = Equipment
    template_name = 'deadline_control/equipment/confirm_delete.html'
    success_url = reverse_lazy('deadline_control:equipment:list')

    def delete(self, request, *args, **kwargs):
        equipment = self.get_object()
        messages.success(request, f'Оборудование "{equipment.equipment_name}" успешно удалено')
        return super().delete(request, *args, **kwargs)


@login_required
@require_POST
def perform_maintenance(request, pk):
    """Проведение ТО для оборудования"""
    equipment = get_object_or_404(Equipment, pk=pk)

    # Проверка прав доступа через AccessControlHelper
    if not AccessControlHelper.can_access_object(request.user, equipment):
        messages.error(request, 'У вас нет прав для выполнения этой операции')
        return redirect('deadline_control:equipment:list')

    date_str = request.POST.get('maintenance_date')
    comment = request.POST.get('comment', '')

    new_date = parse_date(date_str) if date_str else None
    equipment.update_maintenance(new_date=new_date, comment=comment)

    messages.success(request, f'ТО для "{equipment.equipment_name}" успешно проведено')

    # Если запрос AJAX, возвращаем JSON
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return JsonResponse({
            'success': True,
            'next_date': equipment.next_maintenance_date.isoformat() if equipment.next_maintenance_date else None,
            'days_until': equipment.days_until_maintenance()
        })

    return redirect('deadline_control:equipment:list')


@login_required
def equipment_type_api(request, type_id):
    """
    API endpoint для получения данных о типе оборудования
    Возвращает периодичность ТО для автоподстановки в форме
    """
    from deadline_control.models import EquipmentType
    try:
        equipment_type = EquipmentType.objects.get(pk=type_id, is_active=True)
        return JsonResponse({
            'success': True,
            'default_maintenance_period_months': equipment_type.default_maintenance_period_months,
            'name': equipment_type.name
        })
    except EquipmentType.DoesNotExist:
        return JsonResponse({
            'success': False,
            'error': 'Тип оборудования не найден'
        }, status=404)


class EquipmentJournalView(LoginRequiredMixin, TemplateView):
    """
    Формирование журнала осмотра оборудования с древовидным представлением.
    Иерархия: Организация -> Подразделение -> Отдел -> Оборудование.
    """
    template_name = 'deadline_control/equipment/journal_tree.html'

    @staticmethod
    def _get_allowed_equipment_type_ids():
        from deadline_control.models import EquipmentType
        return list(
            EquipmentType.objects.filter(
                is_active=True,
                name__in=['Лестница', 'Грузовая тележка']
            ).values_list('id', flat=True)
        )

    def get_base_queryset(self, equipment_type=None):
        qs = Equipment.objects.select_related(
            'organization', 'subdivision', 'department', 'equipment_type'
        )
        qs = AccessControlHelper.filter_queryset(qs, self.request.user, self.request)
        if equipment_type:
            qs = qs.filter(equipment_type=equipment_type)
        return qs.order_by(
            'organization__short_name_ru',
            'subdivision__name',
            'department__name',
            'equipment_name'
        )

    def build_tree_structure(self, equipment_list, allowed_orgs):
        tree = {}
        for org in allowed_orgs:
            tree[org.id] = {
                'org': org,
                'equipment_count': 0,
                'subdivisions': {},
                'equipment': [],
            }

        for equipment in equipment_list:
            org = equipment.organization
            if not org or org.id not in tree:
                continue

            tree[org.id]['equipment_count'] += 1

            if not equipment.subdivision:
                tree[org.id]['equipment'].append(equipment)
                continue

            sub = equipment.subdivision
            sub_data = tree[org.id]['subdivisions'].setdefault(sub.id, {
                'sub': sub,
                'equipment_count': 0,
                'departments': {},
                'equipment': [],
            })
            sub_data['equipment_count'] += 1

            if not equipment.department:
                sub_data['equipment'].append(equipment)
                continue

            dept = equipment.department
            dept_data = sub_data['departments'].setdefault(dept.id, {
                'dept': dept,
                'equipment_count': 0,
                'equipment': [],
            })
            dept_data['equipment_count'] += 1
            dept_data['equipment'].append(equipment)

        tree_data = []
        for org in allowed_orgs:
            org_data = tree.get(org.id)
            if not org_data:
                continue
            if org_data['equipment_count'] == 0:
                continue

            subdivisions_list = []
            for _, sub_data in sorted(
                org_data['subdivisions'].items(),
                key=lambda item: (item[1]['sub'].name or '')
            ):
                departments_list = []
                for _, dept_data in sorted(
                    sub_data['departments'].items(),
                    key=lambda item: (item[1]['dept'].name or '')
                ):
                    departments_list.append(dept_data)

                sub_data['departments_list'] = departments_list
                subdivisions_list.append(sub_data)

            org_data['subdivisions_list'] = subdivisions_list
            tree_data.append(org_data)

        return tree_data

    def get_context_data(self, **kwargs):
        from deadline_control.models import EquipmentType

        context = super().get_context_data(**kwargs)
        allowed_type_ids = self._get_allowed_equipment_type_ids()
        equipment_types = EquipmentType.objects.filter(
            is_active=True,
            id__in=allowed_type_ids
        ).order_by('name')
        context['equipment_types'] = equipment_types

        selected_type = None
        selected_type_id = self.request.GET.get('equipment_type')
        if selected_type_id:
            try:
                selected_type = equipment_types.get(pk=selected_type_id)
            except EquipmentType.DoesNotExist:
                selected_type = None

        inspection_date = self.request.GET.get('inspection_date')
        inspection_date = inspection_date or date.today().isoformat()

        if selected_type:
            self.request.session['equipment_journal_params'] = {
                'equipment_type_id': selected_type.id,
                'inspection_date': inspection_date,
            }

        context['selected_equipment_type'] = selected_type
        context['inspection_date'] = inspection_date
        context['title'] = 'Журнал осмотра оборудования'

        if selected_type:
            allowed_orgs = AccessControlHelper.get_accessible_organizations(
                self.request.user, self.request
            )
            equipment_list = list(self.get_base_queryset(selected_type))
            context['tree_data'] = self.build_tree_structure(equipment_list, allowed_orgs)
        else:
            context['tree_data'] = []

        return context

    def post(self, request, *args, **kwargs):
        from deadline_control.models import EquipmentType

        equipment_type_id = request.POST.get('equipment_type')
        inspection_date = request.POST.get('inspection_date')

        if not equipment_type_id:
            messages.error(request, "Выберите тип оборудования для генерации журнала")
            return redirect(request.path)

        try:
            equipment_type = EquipmentType.objects.get(
                pk=equipment_type_id,
                is_active=True,
                id__in=self._get_allowed_equipment_type_ids()
            )
        except EquipmentType.DoesNotExist:
            messages.error(request, "Тип оборудования не найден")
            return redirect(request.path)

        inspection_date = parse_date(inspection_date) or date.today()

        equipment_list = list(self.get_base_queryset(equipment_type))
        if not equipment_list:
            messages.error(request, "Оборудование выбранного типа не найдено")
            return redirect(request.path)

        action = request.POST.get('action')
        if action == 'download_by_subdivision':
            return self._generate_by_subdivision(equipment_list, equipment_type, inspection_date)
        return self._generate_unified(equipment_list, equipment_type, inspection_date)

    def _generate_unified(self, equipment_list, equipment_type, inspection_date):
        from directory.document_generators.equipment_journal_generator import (
            generate_equipment_journal_for_subdivision
        )

        doc = generate_equipment_journal_for_subdivision(
            equipment=equipment_list,
            equipment_type=equipment_type,
            inspection_date=inspection_date,
            subdivision=None,
            subdivision_name="Все подразделения",
            use_two_level_location=True
        )

        if not doc:
            messages.error(self.request, "Ошибка при генерации журнала")
            return redirect(self.request.path)

        response = HttpResponse(
            doc['content'],
            content_type='application/vnd.openxmlformats-officedocument.wordprocessingml.document'
        )
        response['Content-Disposition'] = f'attachment; filename="{doc["filename"]}"'
        messages.success(self.request, f'Журнал "{doc["filename"]}" успешно сгенерирован')
        return response

    def _generate_by_subdivision(self, equipment_list, equipment_type, inspection_date):
        from io import BytesIO
        from zipfile import ZipFile
        from directory.document_generators.equipment_journal_generator import (
            generate_equipment_journal_for_subdivision
        )

        grouped = {}
        for equipment in equipment_list:
            if equipment.subdivision:
                key = equipment.subdivision
                label = equipment.subdivision.name
            else:
                key = None
                label = "Без подразделения"
            grouped.setdefault((key, label), []).append(equipment)

        buffer = BytesIO()
        files_generated = 0

        with ZipFile(buffer, 'w') as zip_buffer:
            for (subdivision, label), items in grouped.items():
                doc = generate_equipment_journal_for_subdivision(
                    equipment=items,
                    equipment_type=equipment_type,
                    inspection_date=inspection_date,
                    subdivision=subdivision,
                    subdivision_name=label
                )
                if not doc:
                    continue

                zip_buffer.writestr(doc['filename'], doc['content'])
                files_generated += 1

        if files_generated == 0:
            messages.error(self.request, "Не удалось сгенерировать ни одного документа")
            return redirect(self.request.path)

        buffer.seek(0)
        response = HttpResponse(buffer.getvalue(), content_type='application/zip')
        response['Content-Disposition'] = 'attachment; filename="Журналы_по_подразделениям.zip"'
        messages.success(self.request, f'Сгенерировано файлов: {files_generated}')
        return response


@login_required
def send_equipment_journal_sample(request, subdivision_id):
    """
    Отправляет образец журнала осмотра оборудования на email получателей подразделения.
    """
    from django.shortcuts import get_object_or_404
    from django.core.mail import EmailMultiAlternatives
    from django.utils import timezone
    from deadline_control.models import EquipmentType, EmailSettings, EquipmentJournalSendLog, EquipmentJournalSendDetail
    from directory.models import StructuralSubdivision
    from directory.utils.email_recipients import collect_recipients_for_subdivision
    from directory.document_generators.equipment_journal_generator import (
        generate_equipment_journal_for_subdivision
    )
    import json

    subdivision = get_object_or_404(StructuralSubdivision, pk=subdivision_id)
    organization = subdivision.organization

    if not AccessControlHelper.can_access_object(request.user, subdivision):
        messages.error(request, "У вас нет прав доступа к этому подразделению")
        return redirect('deadline_control:equipment:journal')

    params = request.session.get('equipment_journal_params', {})
    equipment_type_id = params.get('equipment_type_id')
    inspection_date_raw = params.get('inspection_date', date.today().isoformat())
    inspection_date = parse_date(inspection_date_raw) or date.today()
    inspection_date_str = inspection_date.strftime('%d.%m.%Y')

    if not equipment_type_id:
        messages.error(request, "Сначала выберите тип оборудования и дату осмотра")
        return redirect('deadline_control:equipment:journal')

    try:
        equipment_type = EquipmentType.objects.get(pk=equipment_type_id, is_active=True)
    except EquipmentType.DoesNotExist:
        messages.error(request, "Тип оборудования не найден")
        return redirect('deadline_control:equipment:journal')

    equipment_list = Equipment.objects.filter(
        subdivision=subdivision,
        equipment_type=equipment_type
    ).select_related('organization', 'subdivision', 'department', 'equipment_type')

    send_log = EquipmentJournalSendLog.objects.create(
        organization=organization,
        initiated_by=request.user,
        equipment_type=equipment_type,
        inspection_date=inspection_date,
        total_subdivisions=1,
        successful_count=0,
        failed_count=0,
        skipped_count=0,
        status='in_progress'
    )

    if not equipment_list.exists():
        EquipmentJournalSendDetail.objects.create(
            send_log=send_log,
            subdivision=subdivision,
            status='skipped',
            skip_reason='no_equipment',
            recipients='[]',
            recipients_count=0,
            equipment_count=0,
            email_subject='',
            error_message='Нет оборудования выбранного типа'
        )
        send_log.skipped_count = 1
        send_log.status = 'failed'
        send_log.save()
        messages.warning(request, "Нет оборудования выбранного типа для подразделения")
        return redirect('deadline_control:equipment:journal')

    recipients = collect_recipients_for_subdivision(
        subdivision=subdivision,
        organization=organization,
        notification_type='general'
    )

    if not recipients:
        EquipmentJournalSendDetail.objects.create(
            send_log=send_log,
            subdivision=subdivision,
            status='skipped',
            skip_reason='no_recipients',
            recipients='[]',
            recipients_count=0,
            equipment_count=equipment_list.count(),
            email_subject='',
            error_message='Не настроены получатели для подразделения'
        )
        send_log.skipped_count = 1
        send_log.status = 'failed'
        send_log.save()
        messages.warning(request, "Для подразделения не настроены получатели email")
        return redirect('deadline_control:equipment:journal')

    try:
        email_settings = EmailSettings.get_settings(organization)
    except Exception as exc:
        messages.error(request, f"Не удалось получить настройки email: {exc}")
        return redirect('deadline_control:equipment:journal')

    if not email_settings.is_active or not email_settings.email_host:
        messages.error(request, f"SMTP сервер не настроен для {organization.short_name_ru}")
        return redirect('deadline_control:equipment:journal')

    doc = generate_equipment_journal_for_subdivision(
        equipment=list(equipment_list),
        equipment_type=equipment_type,
        inspection_date=inspection_date,
        subdivision=subdivision
    )

    if not doc:
        EquipmentJournalSendDetail.objects.create(
            send_log=send_log,
            subdivision=subdivision,
            status='failed',
            skip_reason='doc_generation_failed',
            recipients=json.dumps(recipients),
            recipients_count=len(recipients),
            equipment_count=equipment_list.count(),
            email_subject='',
            error_message='Не удалось сгенерировать документ'
        )
        send_log.failed_count = 1
        send_log.status = 'failed'
        send_log.save()
        messages.error(request, "Ошибка при генерации журнала")
        return redirect('deadline_control:equipment:journal')

    departments = {eq.department.name for eq in equipment_list if eq.department}
    if len(departments) == 0:
        department_name = "Без отдела"
    elif len(departments) == 1:
        department_name = list(departments)[0]
    else:
        department_name = "Все отделы"

    template_vars = {
        'organization_name': organization.full_name_ru,
        'subdivision_name': subdivision.name,
        'department_name': department_name,
        'inspection_date': inspection_date_str,
        'equipment_type': equipment_type.name,
        'equipment_count': equipment_list.count(),
    }

    template_data = email_settings.get_email_template('equipment_journal')
    if not template_data:
        EquipmentJournalSendDetail.objects.create(
            send_log=send_log,
            subdivision=subdivision,
            status='failed',
            skip_reason='template_not_found',
            recipients=json.dumps(recipients),
            recipients_count=len(recipients),
            equipment_count=equipment_list.count(),
            email_subject='',
            error_message='Шаблон письма не настроен'
        )
        send_log.failed_count = 1
        send_log.status = 'failed'
        send_log.save()
        messages.error(request, "Шаблон письма не настроен")
        return redirect('deadline_control:equipment:journal')

    subject = template_data[0].format(**template_vars)
    html_message = template_data[1].format(**template_vars)

    from django.utils.html import strip_tags
    text_message = strip_tags(html_message)

    try:
        connection = email_settings.get_connection()
        from_email = email_settings.default_from_email or email_settings.email_host_user

        email = EmailMultiAlternatives(
            subject=subject,
            body=text_message,
            from_email=from_email,
            to=recipients,
            connection=connection
        )
        email.attach_alternative(html_message, "text/html")
        email.attach(
            doc['filename'],
            doc['content'],
            'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
        )
        email.send(fail_silently=False)

        EquipmentJournalSendDetail.objects.create(
            send_log=send_log,
            subdivision=subdivision,
            status='success',
            recipients=json.dumps(recipients),
            recipients_count=len(recipients),
            equipment_count=equipment_list.count(),
            email_subject=subject,
            sent_at=timezone.now()
        )

        send_log.successful_count = 1
        send_log.status = 'completed'
        send_log.save()
        messages.success(request, "Журнал успешно отправлен")
        return redirect('deadline_control:equipment:journal')

    except Exception as exc:
        EquipmentJournalSendDetail.objects.create(
            send_log=send_log,
            subdivision=subdivision,
            status='failed',
            skip_reason='email_send_failed',
            recipients=json.dumps(recipients),
            recipients_count=len(recipients),
            equipment_count=equipment_list.count(),
            email_subject=subject,
            error_message=str(exc)
        )
        send_log.failed_count = 1
        send_log.status = 'failed'
        send_log.save()
        messages.error(request, f"Ошибка отправки email: {exc}")
        return redirect('deadline_control:equipment:journal')


@login_required
def send_equipment_journals_for_organization(request, organization_id):
    """
    Массовая отправка журналов осмотра оборудования по подразделениям организации.
    """
    from django.shortcuts import get_object_or_404
    from django.core.mail import EmailMultiAlternatives
    from django.utils import timezone
    from django.utils.safestring import mark_safe
    from django.urls import reverse
    from deadline_control.models import EquipmentType, EmailSettings, EquipmentJournalSendLog, EquipmentJournalSendDetail
    from directory.models import Organization, StructuralSubdivision
    from directory.utils.email_recipients import collect_recipients_for_subdivision
    from directory.document_generators.equipment_journal_generator import (
        generate_equipment_journal_for_subdivision
    )
    import json

    organization = get_object_or_404(Organization, pk=organization_id)

    if not request.user.is_superuser and hasattr(request.user, 'profile'):
        if organization not in request.user.profile.organizations.all():
            messages.error(request, "У вас нет прав доступа к этой организации")
            return redirect('deadline_control:equipment:journal')

    params = request.session.get('equipment_journal_params', {})
    equipment_type_id = params.get('equipment_type_id')
    inspection_date_raw = params.get('inspection_date')

    if not equipment_type_id or not inspection_date_raw:
        messages.error(request, "Параметры журнала не найдены. Заполните фильтры на странице журналов.")
        return redirect('deadline_control:equipment:journal')

    inspection_date = parse_date(inspection_date_raw) or date.today()
    inspection_date_str = inspection_date.strftime('%d.%m.%Y')

    try:
        equipment_type = EquipmentType.objects.get(pk=equipment_type_id, is_active=True)
    except EquipmentType.DoesNotExist:
        messages.error(request, "Тип оборудования не найден")
        return redirect('deadline_control:equipment:journal')

    try:
        email_settings = EmailSettings.get_settings(organization)
    except Exception as exc:
        messages.error(request, f"Не удалось получить настройки email: {exc}")
        return redirect('deadline_control:equipment:journal')

    if not email_settings.is_active or not email_settings.email_host:
        messages.error(request, f"SMTP сервер не настроен для {organization.short_name_ru}")
        return redirect('deadline_control:equipment:journal')

    subdivisions = StructuralSubdivision.objects.filter(organization=organization)

    send_log = EquipmentJournalSendLog.objects.create(
        organization=organization,
        initiated_by=request.user,
        equipment_type=equipment_type,
        inspection_date=inspection_date,
        total_subdivisions=subdivisions.count(),
        successful_count=0,
        failed_count=0,
        skipped_count=0,
        status='in_progress'
    )

    successful_sent = 0
    failed_sent = 0
    skipped_count = 0
    total_recipients = set()

    for subdivision in subdivisions:
        equipment_list = Equipment.objects.filter(
            subdivision=subdivision,
            equipment_type=equipment_type
        ).select_related('organization', 'subdivision', 'department', 'equipment_type')

        if not equipment_list.exists():
            EquipmentJournalSendDetail.objects.create(
                send_log=send_log,
                subdivision=subdivision,
                status='skipped',
                skip_reason='no_equipment',
                recipients='[]',
                recipients_count=0,
                equipment_count=0,
                email_subject='',
                error_message='Нет оборудования выбранного типа'
            )
            skipped_count += 1
            continue

        recipients = collect_recipients_for_subdivision(
            subdivision=subdivision,
            organization=organization,
            notification_type='general'
        )

        if not recipients:
            EquipmentJournalSendDetail.objects.create(
                send_log=send_log,
                subdivision=subdivision,
                status='skipped',
                skip_reason='no_recipients',
                recipients='[]',
                recipients_count=0,
                equipment_count=equipment_list.count(),
                email_subject='',
                error_message='Не настроены получатели для подразделения'
            )
            skipped_count += 1
            continue

        total_recipients.update(recipients)

        doc = generate_equipment_journal_for_subdivision(
            equipment=list(equipment_list),
            equipment_type=equipment_type,
            inspection_date=inspection_date,
            subdivision=subdivision
        )

        if not doc:
            EquipmentJournalSendDetail.objects.create(
                send_log=send_log,
                subdivision=subdivision,
                status='failed',
                skip_reason='doc_generation_failed',
                recipients=json.dumps(recipients),
                recipients_count=len(recipients),
                equipment_count=equipment_list.count(),
                email_subject='',
                error_message='Не удалось сгенерировать документ'
            )
            failed_sent += 1
            continue

        departments = {eq.department.name for eq in equipment_list if eq.department}
        if len(departments) == 0:
            department_name = "Без отдела"
        elif len(departments) == 1:
            department_name = list(departments)[0]
        else:
            department_name = "Все отделы"

        template_vars = {
            'organization_name': organization.full_name_ru,
            'subdivision_name': subdivision.name,
            'department_name': department_name,
            'inspection_date': inspection_date_str,
            'equipment_type': equipment_type.name,
            'equipment_count': equipment_list.count(),
        }

        template_data = email_settings.get_email_template('equipment_journal')
        if not template_data:
            EquipmentJournalSendDetail.objects.create(
                send_log=send_log,
                subdivision=subdivision,
                status='failed',
                skip_reason='template_not_found',
                recipients=json.dumps(recipients),
                recipients_count=len(recipients),
                equipment_count=equipment_list.count(),
                email_subject='',
                error_message='Шаблон письма не настроен'
            )
            failed_sent += 1
            continue

        subject = template_data[0].format(**template_vars)
        html_message = template_data[1].format(**template_vars)

        from django.utils.html import strip_tags
        text_message = strip_tags(html_message)

        try:
            connection = email_settings.get_connection()
            from_email = email_settings.default_from_email or email_settings.email_host_user

            email = EmailMultiAlternatives(
                subject=subject,
                body=text_message,
                from_email=from_email,
                to=recipients,
                connection=connection
            )
            email.attach_alternative(html_message, "text/html")
            email.attach(
                doc['filename'],
                doc['content'],
                'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
            )
            email.send(fail_silently=False)

            EquipmentJournalSendDetail.objects.create(
                send_log=send_log,
                subdivision=subdivision,
                status='success',
                recipients=json.dumps(recipients),
                recipients_count=len(recipients),
                equipment_count=equipment_list.count(),
                email_subject=subject,
                sent_at=timezone.now()
            )
            successful_sent += 1
        except Exception as exc:
            EquipmentJournalSendDetail.objects.create(
                send_log=send_log,
                subdivision=subdivision,
                status='failed',
                skip_reason='email_send_failed',
                recipients=json.dumps(recipients),
                recipients_count=len(recipients),
                equipment_count=equipment_list.count(),
                email_subject=subject,
                error_message=str(exc)
            )
            failed_sent += 1

    send_log.successful_count = successful_sent
    send_log.failed_count = failed_sent
    send_log.skipped_count = skipped_count

    if successful_sent > 0 and failed_sent == 0 and skipped_count == 0:
        send_log.status = 'completed'
    elif successful_sent > 0:
        send_log.status = 'partial'
    else:
        send_log.status = 'failed'

    send_log.save()

    log_url = reverse('admin:deadline_control_equipmentjournalsendlog_change', args=[send_log.pk])
    if successful_sent > 0:
        messages.success(
            request,
            mark_safe(
                f"? Массовая отправка завершена!<br>"
                f"Отправлено: <strong>{successful_sent}</strong><br>"
                f"Ошибок: <strong>{failed_sent}</strong><br>"
                f"Пропущено: <strong>{skipped_count}</strong><br>"
                f"Уникальных получателей: <strong>{len(total_recipients)}</strong><br><br>"
                f"<a href='{log_url}' target='_blank' style='color:#fff;background:#2196f3;padding:8px 16px;border-radius:4px;text-decoration:none;'>?? Посмотреть отчет</a>"
            )
        )
    elif failed_sent > 0 or skipped_count > 0:
        messages.warning(
            request,
            mark_safe(
                f"?? Внимание: отправка завершена с ошибками.<br>"
                f"<a href='{log_url}' target='_blank'>?? Проверьте детали в отчете</a>"
            )
        )

    return redirect('deadline_control:equipment:journal')


@login_required
def preview_mass_send_equipment_journals(request, organization_id):
    """
    Предпросмотр массовой отправки журналов осмотра оборудования.
    """
    from directory.models import Organization, StructuralSubdivision
    from deadline_control.models import EquipmentType, EmailSettings
    from directory.utils.email_recipients import collect_recipients_for_subdivision

    try:
        organization = Organization.objects.get(id=organization_id)
    except Organization.DoesNotExist:
        messages.error(request, "Организация не найдена")
        return redirect('deadline_control:equipment:journal')

    if not request.user.is_superuser and hasattr(request.user, 'profile'):
        if organization not in request.user.profile.organizations.all():
            messages.error(request, "У вас нет доступа к этой организации")
            return redirect('deadline_control:equipment:journal')

    params = request.session.get('equipment_journal_params', {})
    equipment_type_id = params.get('equipment_type_id')
    inspection_date_raw = params.get('inspection_date', date.today().isoformat())
    inspection_date = parse_date(inspection_date_raw) or date.today()
    inspection_date_str = inspection_date.strftime('%d.%m.%Y')

    if not equipment_type_id:
        messages.error(request, "Сначала выберите тип оборудования")
        return redirect('deadline_control:equipment:journal')

    try:
        equipment_type = EquipmentType.objects.get(pk=equipment_type_id, is_active=True)
    except EquipmentType.DoesNotExist:
        messages.error(request, "Тип оборудования не найден")
        return redirect('deadline_control:equipment:journal')

    try:
        email_settings = EmailSettings.objects.get(organization=organization)
        if not email_settings.is_active:
            messages.warning(request, "Отправка email отключена для этой организации")
            return redirect('deadline_control:equipment:journal')
    except EmailSettings.DoesNotExist:
        messages.error(request, "Настройки email не найдены для организации")
        return redirect('deadline_control:equipment:journal')

    if request.method == 'POST' and 'send_emails' in request.POST:
        return send_equipment_journals_for_organization(request, organization_id)

    subdivisions = StructuralSubdivision.objects.filter(
        organization=organization
    ).order_by('name')

    tree_data = []
    total_recipients = set()
    has_any_recipients = False

    for subdivision in subdivisions:
        equipment_list = Equipment.objects.filter(
            organization=organization,
            subdivision=subdivision,
            equipment_type=equipment_type
        ).select_related('department')

        if not equipment_list.exists():
            continue

        recipients = collect_recipients_for_subdivision(
            subdivision,
            organization,
            notification_type='general'
        )

        departments = {eq.department.name for eq in equipment_list if eq.department}
        if len(departments) == 0:
            department_name = "Без отдела"
        elif len(departments) == 1:
            department_name = list(departments)[0]
        else:
            department_name = "Все отделы"

        total_recipients.update(recipients)
        has_recipients = len(recipients) > 0
        if has_recipients:
            has_any_recipients = True

        template_vars = {
            'organization_name': organization.full_name_ru,
            'subdivision_name': subdivision.name,
            'department_name': department_name,
            'inspection_date': inspection_date_str,
            'equipment_type': equipment_type.name,
            'equipment_count': equipment_list.count(),
        }

        template_data = email_settings.get_email_template('equipment_journal')
        if template_data:
            subject = template_data[0].format(**template_vars)
        else:
            subject = "Шаблон не настроен"

        tree_data.append({
            'subdivision': subdivision,
            'department_name': department_name,
            'equipment_count': equipment_list.count(),
            'recipients': recipients,
            'has_recipients': has_recipients,
            'email_subject': subject,
        })

    template_data = email_settings.get_email_template('equipment_journal')
    if tree_data and template_data:
        example_vars = {
            'organization_name': organization.full_name_ru,
            'subdivision_name': tree_data[0]['subdivision'].name,
            'department_name': tree_data[0]['department_name'],
            'inspection_date': inspection_date_str,
            'equipment_type': equipment_type.name,
            'equipment_count': tree_data[0]['equipment_count'],
        }
        email_body_preview = template_data[1].format(**example_vars)
    elif template_data:
        email_body_preview = template_data[1]
    else:
        email_body_preview = "Шаблон письма не настроен"

    context = {
        'organization': organization,
        'equipment_type': equipment_type,
        'inspection_date': inspection_date_str,
        'tree_data': tree_data,
        'total_recipients': total_recipients,
        'total_recipients_count': len(total_recipients),
        'email_body_preview': email_body_preview,
        'has_any_recipients': has_any_recipients,
    }

    return render(request, 'deadline_control/equipment/journal_preview.html', context)


@login_required
def generate_equipment_journal_view(request):
    """
    📄 View для генерации журнала периодического осмотра оборудования
    Период журнала автоматически устанавливается на текущий год
    """
    from django.http import HttpResponse
    from deadline_control.forms.equipment import EquipmentJournalGenerationForm
    from directory.document_generators.equipment_journal_generator import generate_equipment_journal
    import datetime

    if request.method == 'POST':
        form = EquipmentJournalGenerationForm(request.POST, user=request.user)
        if form.is_valid():
            organization = form.cleaned_data['organization']
            equipment_type = form.cleaned_data['equipment_type']

            # Автоматически используем текущий год для периода журнала
            current_year = datetime.datetime.now().year
            start_date = datetime.date(current_year, 1, 1)
            end_date = datetime.date(current_year, 12, 31)

            # Генерируем журнал
            result = generate_equipment_journal(
                organization=organization,
                equipment_type_name=equipment_type.name,
                start_date=start_date,
                end_date=end_date
            )

            if result:
                # Отдаем файл пользователю
                response = HttpResponse(
                    result['content'],
                    content_type='application/vnd.openxmlformats-officedocument.wordprocessingml.document'
                )
                response['Content-Disposition'] = f'attachment; filename="{result["filename"]}"'
                messages.success(request, f'Журнал "{result["filename"]}" успешно сгенерирован')
                return response
            else:
                messages.error(request, 'Ошибка при генерации журнала. Проверьте логи.')
    else:
        form = EquipmentJournalGenerationForm(user=request.user)

    return render(
        request,
        'deadline_control/equipment/generate_journal.html',
        {'form': form, 'title': 'Генерация журнала оборудования'}
    )
