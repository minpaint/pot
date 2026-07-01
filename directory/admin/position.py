# directory/admin/position.py
import logging

from django.contrib import admin
from django.contrib.admin.widgets import FilteredSelectMultiple
from django.utils.translation import gettext_lazy as _
from django.contrib import messages
from django.shortcuts import redirect, render
from django.urls import path, reverse
from django.utils.html import format_html
from django.db import DatabaseError
from django.db.models import Exists, OuterRef, Count, Q
from django.http import HttpResponse
from tablib import Dataset

from directory.models import Position
from directory.forms.position import PositionForm
from directory.admin.mixins.tree_view import TreeViewMixin
from directory.models.siz import SIZNorm, SIZ
from deadline_control.models.medical_norm import PositionMedicalFactor, MedicalExaminationNorm
from deadline_control.models.medical_examination import HarmfulFactor
from directory.models.commission import CommissionMember
from directory.utils.profession_icons import get_profession_icon
from directory.resources.organization_structure import OrganizationStructureResource

logger = logging.getLogger(__name__)


# Обновленный инлайн для СИЗ
class SIZNormInlineForPosition(admin.TabularInline):
    """📋 Встроенные нормы СИЗ для должности с отображением всех полей"""
    model = SIZNorm
    extra = 0  # Не показываем пустые строки по умолчанию
    fields = ('siz', 'classification', 'unit', 'quantity', 'wear_period', 'condition', 'order')
    readonly_fields = ('classification', 'unit', 'wear_period')
    verbose_name = "Переопределённая норма СИЗ"
    verbose_name_plural = "Переопределённые нормы СИЗ"

    # Восстанавливаем autocomplete_fields с добавлением формы
    autocomplete_fields = ['siz']

    # Не показываем пустые формы по умолчанию
    def get_extra(self, request, obj=None, **kwargs):
        """Возвращает 0 пустых строк (пользователь добавит через кнопку 'Добавить ещё')"""
        return 0

    # Улучшаем фильтрацию запросов
    def get_queryset(self, request):
        # Все нормы для должности, отсортированные по условию и порядку
        # Исключаем пустые нормы (без указанного СИЗ)
        return super().get_queryset(request).select_related('siz').filter(
            siz__isnull=False
        ).order_by('condition', 'order')

    def classification(self, obj):
        """📊 Отображение классификации СИЗ"""
        return obj.siz.classification if obj.siz else ""

    classification.short_description = "Классификация"

    def unit(self, obj):
        """📏 Отображение единицы измерения СИЗ"""
        return obj.siz.unit if obj.siz else ""

    unit.short_description = "Ед. изм."

    def wear_period(self, obj):
        """🔄 Отображение срока носки СИЗ"""
        if obj.siz:
            if obj.siz.wear_period == 0:
                return "До износа"
            return f"{obj.siz.wear_period} мес."
        return ""

    wear_period.short_description = "Срок носки"

    def formfield_for_dbfield(self, db_field, **kwargs):
        """Настройка полей формы"""
        form_field = super().formfield_for_dbfield(db_field, **kwargs)
        if db_field.name == 'quantity':
            form_field.widget.attrs['style'] = 'width: 80px;'
        if db_field.name == 'condition':
            form_field.widget.attrs['style'] = 'width: 200px;'
        if db_field.name == 'order':
            form_field.widget.attrs['style'] = 'width: 60px;'
        # Добавляем стили для виджета siz, если он уже настроен
        if db_field.name == 'siz' and hasattr(form_field.widget, 'attrs'):
            form_field.widget.attrs['style'] = 'min-width: 260px;'
            form_field.widget.attrs['class'] = 'select2-siz-field'
        return form_field


# Новый инлайн для вредных факторов медосмотров
class PositionMedicalFactorInline(admin.TabularInline):
    """🏥 Встроенные вредные факторы для должности"""
    model = PositionMedicalFactor
    extra = 0
    # Удалено поле notes из списка полей
    fields = ('harmful_factor', 'periodicity', 'periodicity_override', 'is_disabled')
    readonly_fields = ('periodicity',)
    verbose_name = "Вредный фактор медосмотра"
    verbose_name_plural = "Вредные факторы медосмотров"
    autocomplete_fields = ['harmful_factor']

    def get_extra(self, request, obj=None, **kwargs):
        """Возвращает 0 для существующих объектов, 1 для новых"""
        return 0 if obj else 1

    def get_queryset(self, request):
        """Оптимизированный запрос"""
        return super().get_queryset(request).select_related(
            'harmful_factor'
        ).filter(
            harmful_factor__isnull=False
        ).order_by('harmful_factor__short_name')

    def periodicity(self, obj):
        """🕐 Отображение базовой периодичности"""
        if obj.harmful_factor:
            return f"{obj.harmful_factor.periodicity} мес."
        return ""

    periodicity.short_description = "Базовая периодичность"

    def formfield_for_dbfield(self, db_field, **kwargs):
        """Настройка полей формы"""
        form_field = super().formfield_for_dbfield(db_field, **kwargs)
        if db_field.name == 'periodicity_override':
            form_field.widget.attrs['style'] = 'width: 80px;'
        return form_field


@admin.register(Position)
class PositionAdmin(TreeViewMixin, admin.ModelAdmin):
    """
    👔 Админ-класс для модели Position.

    Реализует древовидное представление должностей с индикаторами:
    - Наличия норм СИЗ (🛡️) - проверяет сначала переопределенные, затем эталонные
    - Наличия медосмотров (🏥) - проверяет сначала переопределенные, затем эталонные
    - Роли в комиссиях (определяется через связь с CommissionMember)
    - Прочих атрибутов должности (ответственный за ОТ, ЭБ и др.)
    """
    form = PositionForm
    actions = ['copy_instructions_from_template', 'copy_to_subdivision']
    # Путь к шаблону для древовидного отображения
    change_list_template = "admin/directory/position/change_list_tree.html"
    # 🔄 AJAX режим для постепенной загрузки узлов дерева
    # ВРЕМЕННО ОТКЛЮЧЕН: требуется другой подход для структур где все записи в подразделениях
    tree_ajax_mode = False
    # Шаблон формы для добавления кнопки подтягивания норм
    change_form_template = "admin/directory/position/change_form.html"

    # Определяем порядок полей в форме
    fieldsets = (
        ('Основная информация', {
            'fields': (
                'position_name',
                'organization',
                'subdivision',
                'department',
                'responsibility_types',
                'is_responsible_for_safety',
                'can_be_internship_leader',
                'can_sign_orders',
                'is_electrical_personnel',
                'drives_company_vehicle',
            )
        }),
        ('Документация', {
            'fields': (
                'contract_work_name',
                'safety_instructions_numbers',
                'contract_safety_instructions',
                'company_vehicle_instructions',
                'electrical_safety_group',
                'internship_period_days',
            )
        }),
        ('🪜 Работа на высоте', {
            'fields': ('height_group_1', 'height_group_2', 'height_group_3'),
            'description': 'Укажите группы для работы на высоте, присвоенные данной должности. Можно выбрать несколько групп.',
        }),
        ('🛡️ Переопределение норм СИЗ', {
            'fields': ('requires_siz', 'siz_norms_overridden'),
            'description': '''<strong>⚠️ Включите этот флаг, если:</strong><br>
• Для этой должности нормы СИЗ отличаются от эталонных (заполните таблицу ниже)<br>
• Или СИЗ вообще НЕ положены (оставьте таблицу пустой → будет красный индикатор 🔴)<br><br>
<strong>Если флаг выключен</strong> – используются эталонные нормы для профессии.''',
            'classes': ('siz-override-section',)
        }),
        ('🏥 Переопределение норм медосмотров', {
            'fields': ('medical_norms_overridden',),
            'description': '''<strong>⚠️ Включите этот флаг, если:</strong><br>
• Для этой должности нормы медосмотров отличаются от эталонных (заполните таблицу ниже)<br>
• Или медосмотры НЕ требуются (оставьте таблицу пустой → будет красный индикатор 🔴)<br><br>
<strong>Если флаг выключен</strong> – используются эталонные нормы для профессии.''',
            'classes': ('medical-override-section',)
        }),
        ('Связанные документы и оборудование', {
            'fields': ('documents', 'equipment'),
            'description': '📄 Выберите документы и оборудование, относящиеся к данной должности',
            'classes': ('collapse',)
        }),
    )

    # Фильтры отключены - используется компактный dropdown над деревом
    list_filter = []
    # Очищаем стандартное отображение столбцов
    list_display = []
    preserve_filters = True
    search_fields = [
        'position_name',
        'safety_instructions_numbers'
    ]

    # Улучшенная система иконок для иерархии и профессий
    tree_settings = {
        'icons': {
            'organization': '🏢',
            'subdivision': '🏭',
            'department': '📂',
            'position': '👔',  # Базовая иконка для должности (будет заменена на специфичную)
            'employee': '👤',
            'no_subdivision': '🏗️',
            'no_department': '📁'
        },
        'fields': {
            'name_field': 'position_name',
            'organization_field': 'organization',
            'subdivision_field': 'subdivision',
            'department_field': 'department'
        },
        'display_rules': {
            'hide_empty_branches': False,
            'hide_no_subdivision_no_department': False
        }
    }

    # Добавляем инлайны для СИЗ и вредных факторов медосмотров
    inlines = [
        SIZNormInlineForPosition,
        PositionMedicalFactorInline,  # Инлайн для вредных факторов
    ]

    # Удобный виджет выбора для ManyToMany полей
    filter_horizontal = ('documents', 'equipment', 'responsibility_types')

    class Media:
        css = {
            'all': ('admin/css/widgets.css', 'admin/css/tree_view.css')
        }
        js = [
            'admin/js/jquery.init.js',
            'admin/js/core.js',
            'admin/js/SelectBox.js',
            'admin/js/SelectFilter2.js',
        ]

    def change_view(self, request, object_id, form_url='', extra_context=None):
        """Добавляем в контекст информацию о наличии медицинских факторов"""
        extra_context = extra_context or {}
        obj = self.get_object(request, object_id)
        if obj:
            extra_context['has_medical_factors'] = obj.medical_factors.exists()
        return super().change_view(request, object_id, form_url, extra_context)

    def changelist_view(self, request, extra_context=None):
        """
        Переопределяем changelist_view для оптимизации:
        Создаём кэш эталонных норм СИЗ и медосмотров ОДИН РАЗ
        перед построением дерева, чтобы избежать N+1 запросов.
        """
        try:
            extra_context = extra_context or {}
            from directory.models import Organization, StructuralSubdivision, Department

            if request.user.is_superuser:
                accessible_orgs = Organization.objects.all()
            elif hasattr(request.user, 'profile'):
                accessible_orgs = request.user.profile.organizations.all()
            else:
                accessible_orgs = Organization.objects.none()

            # Организация берётся из сессии (selected_org_id)
            selected_org_id = None
            session_org_id = request.session.get('selected_org_id')
            if session_org_id and accessible_orgs.filter(id=session_org_id).exists():
                selected_org_id = session_org_id
            elif not session_org_id and accessible_orgs.count() == 1:
                # Авто-выбор единственной организации
                first_org = accessible_orgs.first()
                request.session['selected_org_id'] = first_org.id
                selected_org_id = first_org.id

            extra_context['selected_org_id'] = selected_org_id

            sub_param = request.GET.get('subdivision__id__exact')
            selected_sub_id = None
            if sub_param and sub_param.isdigit():
                selected_sub_id = int(sub_param)

            dept_param = request.GET.get('department__id__exact')
            selected_dept_id = None
            if dept_param and dept_param.isdigit():
                selected_dept_id = int(dept_param)

            subdivision_options = StructuralSubdivision.objects.none()
            department_options = Department.objects.none()

            if selected_org_id:
                subdivision_options = StructuralSubdivision.objects.filter(
                    organization__in=accessible_orgs,
                    organization_id=selected_org_id
                ).order_by('name')

                if selected_sub_id:
                    department_options = Department.objects.filter(
                        organization__in=accessible_orgs,
                        organization_id=selected_org_id,
                        subdivision_id=selected_sub_id
                    ).order_by('name')

            extra_context['subdivision_options'] = subdivision_options
            extra_context['selected_sub_id'] = selected_sub_id
            extra_context['department_options'] = department_options
            extra_context['selected_dept_id'] = selected_dept_id
            extra_context['no_instructions_selected'] = request.GET.get('no_instructions') == '1'

            # Получить queryset с фильтрами
            qs = self.get_queryset(request)

            # Собрать все уникальные названия должностей
            position_names = set(qs.values_list('position_name', flat=True))

            # ===== КЭШ ЭТАЛОННЫХ НОРМ СИЗ =====
            # Загрузить все эталонные нормы СИЗ из справочника профессий
            from directory.models.siz import ProfessionSIZNorm
            profession_names_with_siz = ProfessionSIZNorm.objects.filter(
                profession_name__in=position_names
            ).values_list('profession_name', flat=True).distinct()

            # Создать словарь для быстрого поиска
            self._reference_siz_cache = {name: True for name in profession_names_with_siz}

            # ===== КЭШ ЭТАЛОННЫХ НОРМ МЕДОСМОТРОВ =====
            # Загрузить все эталонные нормы медосмотров одним запросом
            medical_positions_with_norms = MedicalExaminationNorm.objects.filter(
                position_name__in=position_names
            ).values_list('position_name', flat=True).distinct()

            # Создать словарь для быстрого поиска
            self._reference_medical_cache = {name: True for name in medical_positions_with_norms}

            # Вызвать родительский метод (TreeViewMixin.changelist_view)
            return super().changelist_view(request, extra_context)
        except DatabaseError:
            logger.exception(
                "DatabaseError in PositionAdmin.changelist_view",
                extra={
                    'path': request.path,
                    'query_params': dict(request.GET),
                    'user': getattr(request.user, 'username', None),
                },
            )
            raise

    def get_urls(self):
        """🔗 Добавляем кастомные URL для подтягивания норм СИЗ и импорта/экспорта"""
        urls = super().get_urls()
        custom_urls = [
            path(
                '<path:object_id>/copy_reference_norms/',
                self.admin_site.admin_view(self.copy_reference_norms_view),
                name='position_copy_reference_norms',
            ),
            path('import/', self.admin_site.admin_view(self.import_view), name='directory_position_import'),
            path('export/', self.admin_site.admin_view(self.export_view), name='directory_position_export'),
        ]
        return custom_urls + urls

    def copy_reference_norms_view(self, request, object_id):
        """👥 View для копирования эталонных норм в текущую должность

        Копирует эталонные нормы из справочника профессий (ProfessionSIZNorm)
        в конкретную должность.
        """
        from directory.models.siz import ProfessionSIZNorm

        position = self.get_object(request, object_id)
        if not position:
            messages.error(request, "Должность не найдена.")
            return redirect('admin:directory_position_change', object_id)

        # Находим эталонные нормы для этой профессии из справочника
        reference_norms = ProfessionSIZNorm.objects.filter(
            profession_name=position.position_name
        ).select_related('siz')

        if not reference_norms.exists():
            messages.warning(request,
                             f"Эталонные нормы СИЗ для профессии '{position.position_name}' не найдены в справочнике. Проверьте раздел 'Эталонные нормы СИЗ профессий'.")
            return redirect('admin:directory_position_change', object_id)

        # Сначала удаляем все пустые нормы у этой должности
        SIZNorm.objects.filter(position=position, siz__isnull=True).delete()

        # Создаем набор для отслеживания уже добавленных норм
        added_norms = set()
        # Счетчики для статистики
        created_count = 0
        updated_count = 0
        errors_count = 0

        # Копируем нормы
        for norm in reference_norms:
            # Пропускаем нормы без указанного СИЗ
            if not norm.siz:
                continue

            # Создаем ключ на основе siz.id и condition
            norm_key = (norm.siz.id, norm.condition)

            # Проверяем, не добавляли ли уже такую норму
            if norm_key not in added_norms:
                try:
                    # Проверяем, существует ли уже такая норма
                    existing_norm = SIZNorm.objects.filter(
                        position=position,
                        siz=norm.siz,
                        condition=norm.condition
                    ).first()

                    if existing_norm:
                        # Обновляем существующую норму
                        existing_norm.quantity = norm.quantity
                        existing_norm.order = norm.order
                        existing_norm.save()
                        updated_count += 1
                    else:
                        # Создаем новую норму
                        SIZNorm.objects.create(
                            position=position,
                            siz=norm.siz,
                            quantity=norm.quantity,
                            condition=norm.condition,
                            order=norm.order
                        )
                        created_count += 1

                    # Добавляем ключ в набор добавленных норм
                    added_norms.add(norm_key)
                except Exception as e:
                    errors_count += 1
                    messages.error(
                        request,
                        f"Ошибка при копировании нормы для {norm.siz.name}: {str(e)}"
                    )

        # После копирования снова проверяем и удаляем все пустые нормы
        SIZNorm.objects.filter(position=position, siz__isnull=True).delete()

        if created_count > 0 or updated_count > 0:
            messages.success(
                request,
                f"Успешно применены эталонные нормы СИЗ: создано {created_count}, обновлено {updated_count}." +
                (f" Ошибок: {errors_count}." if errors_count > 0 else "")
            )
        else:
            messages.info(
                request,
                "Не было скопировано ни одной нормы СИЗ. Возможно, все нормы уже существуют или у этой должности уже есть все нормы." +
                (f" Ошибок: {errors_count}." if errors_count > 0 else "")
            )

        # После копирования и обработки всех норм, перенаправляем на страницу изменения должности
        return redirect('admin:directory_position_change', object_id)

    def formfield_for_manytomany(self, db_field, request, **kwargs):
        """
        Настройка виджетов для полей many-to-many с FilteredSelectMultiple
        """
        if db_field.name == "documents":
            kwargs["widget"] = FilteredSelectMultiple(
                verbose_name="ДОСТУПНЫЕ ДОКУМЕНТЫ",
                is_stacked=False
            )
        if db_field.name == "equipment":
            kwargs["widget"] = FilteredSelectMultiple(
                verbose_name="ДОСТУПНОЕ ОБОРУДОВАНИЕ",
                is_stacked=False
            )
        return super().formfield_for_manytomany(db_field, request, **kwargs)

    def get_queryset(self, request):
        """
        🔒 Ограничиваем должности по организациям, доступным пользователю.
        Оптимизируем запрос подгрузкой связанных объектов.
        """
        qs = super().get_queryset(request).select_related(
            'organization',
            'subdivision',
            'department'
        ).prefetch_related(
            'documents',
            'equipment',
            'siz_norms',  # Предзагрузка СИЗ для оптимизации
            'medical_factors'  # Предзагрузка вредных факторов
        )

        # Фильтрация по правам доступа (только для обычных пользователей, не admin/staff)
        if not (request.user.is_superuser or request.user.is_staff) and hasattr(request.user, 'profile'):
            allowed_orgs = request.user.profile.organizations.all()
            qs = qs.filter(organization__in=allowed_orgs)

        # Фильтрация по организации из глобального хэдера (сессия)
        session_org_id = request.session.get('selected_org_id')
        if session_org_id:
            qs = qs.filter(organization_id=session_org_id)

        sub_param = request.GET.get('subdivision__id__exact')
        if sub_param and sub_param.isdigit():
            qs = qs.filter(subdivision_id=int(sub_param))

        dept_param = request.GET.get('department__id__exact')
        if dept_param and dept_param.isdigit():
            qs = qs.filter(department_id=int(dept_param))

        return qs

    def get_tree_data(self, request):
        """
        📊 Формирует иерархическую структуру дерева с учетом фильтра по инструкциям.
        """
        qs = self.get_queryset(request)
        qs = self._optimize_queryset(qs)

        if self.tree_ajax_mode:
            fields = self.tree_settings['fields']
            sub_field = fields.get('subdivision_field')
            dept_field = fields.get('department_field')

            filter_kwargs = {}
            if sub_field:
                filter_kwargs[f'{sub_field}__isnull'] = True
            if dept_field:
                filter_kwargs[f'{dept_field}__isnull'] = True

            if filter_kwargs:
                qs = qs.filter(**filter_kwargs)

        no_instructions = request.GET.get('no_instructions') == '1'
        tree = {}
        fields = self.tree_settings['fields']
        org_field = fields.get('organization_field')
        sub_field = fields.get('subdivision_field')
        dept_field = fields.get('department_field')
        name_field = fields.get('name_field')

        for obj in qs:
            if no_instructions:
                instructions = (obj.safety_instructions_numbers or '').strip()
                if instructions or obj.is_responsible_for_safety:
                    continue

            org = getattr(obj, org_field) if org_field else None
            if not org:
                continue

            sub = getattr(obj, sub_field) if sub_field else None
            dept = getattr(obj, dept_field) if dept_field else None

            if hasattr(obj, 'tree_display_name'):
                item_name = obj.tree_display_name()
            else:
                item_name = getattr(obj, name_field, str(obj)) if name_field else str(obj)

            if hasattr(self, 'get_node_additional_data'):
                additional_data = self.get_node_additional_data(obj)
            else:
                additional_data = {}

            item_data = {
                'name': item_name,
                'object': obj,
                'pk': obj.pk,
                'additional_data': additional_data
            }

            if org not in tree:
                tree[org] = {
                    'name': getattr(org, 'short_name_ru', str(org)),
                    'items': [],
                    'subdivisions': {}
                }

            if not sub:
                tree[org]['items'].append(item_data)
                continue

            if sub not in tree[org]['subdivisions']:
                tree[org]['subdivisions'][sub] = {
                    'name': getattr(sub, 'name', str(sub)),
                    'items': [],
                    'departments': {}
                }

            if not dept:
                tree[org]['subdivisions'][sub]['items'].append(item_data)
                continue

            if dept not in tree[org]['subdivisions'][sub]['departments']:
                tree[org]['subdivisions'][sub]['departments'][dept] = {
                    'name': getattr(dept, 'name', str(dept)),
                    'items': []
                }

            tree[org]['subdivisions'][sub]['departments'][dept]['items'].append(item_data)

        return tree

    def get_form(self, request, obj=None, **kwargs):
        """
        🔑 Переопределяем get_form для:
        1) Передачи request.user в форму
        2) Фильтрации M2M-полей по организациям
        """
        Form = super().get_form(request, obj, **kwargs)

        class PositionFormWithUser(Form):
            def __init__(self, *args, **kwargs):
                kwargs['user'] = request.user
                if not obj and not kwargs.get('initial_org_id'):
                    _sid = request.session.get('selected_org_id')
                    if _sid:
                        try:
                            kwargs['initial_org_id'] = int(_sid)
                        except (ValueError, TypeError):
                            pass
                super().__init__(*args, **kwargs)
                # Настраиваем labels и help_text для полей
                self.fields['documents'].label = "ДОСТУПНЫЕ ДОКУМЕНТЫ"
                self.fields['equipment'].label = "ДОСТУПНОЕ ОБОРУДОВАНИЕ"
                self.fields[
                    'documents'].help_text = "Удерживайте 'Control' (или 'Command' на Mac), чтобы выбрать несколько значений."
                self.fields[
                    'equipment'].help_text = "Удерживайте 'Control' (или 'Command' на Mac), чтобы выбрать несколько значений."
                # Фильтруем документы и оборудование по организации
                from directory.models import Organization as _Org
                if request.user.is_superuser or request.user.is_staff:
                    # Для admin: используем организацию из хэдера (сессия)
                    session_org_id = request.session.get('selected_org_id')
                    if session_org_id:
                        try:
                            session_org = _Org.objects.get(pk=session_org_id)
                            docs_qs = self.fields['documents'].queryset.filter(organization=session_org)
                            equip_qs = self.fields['equipment'].queryset.filter(organization=session_org)
                        except _Org.DoesNotExist:
                            docs_qs = self.fields['documents'].queryset.none()
                            equip_qs = self.fields['equipment'].queryset.none()
                    elif obj and obj.organization:
                        # Нет org в сессии, но есть объект — показываем его org
                        docs_qs = self.fields['documents'].queryset.filter(organization=obj.organization)
                        equip_qs = self.fields['equipment'].queryset.filter(organization=obj.organization)
                    else:
                        docs_qs = self.fields['documents'].queryset.none()
                        equip_qs = self.fields['equipment'].queryset.none()
                elif hasattr(request.user, 'profile'):
                    allowed_orgs = request.user.profile.organizations.all()
                    docs_qs = self.fields['documents'].queryset.filter(organization__in=allowed_orgs)
                    equip_qs = self.fields['equipment'].queryset.filter(organization__in=allowed_orgs)
                    if obj and obj.organization:
                        docs_qs = docs_qs.filter(organization=obj.organization)
                        equip_qs = equip_qs.filter(organization=obj.organization)
                else:
                    docs_qs = self.fields['documents'].queryset.none()
                    equip_qs = self.fields['equipment'].queryset.none()
                self.fields['documents'].queryset = docs_qs.distinct().order_by('name')
                self.fields['equipment'].queryset = equip_qs.distinct().order_by('equipment_name')

        return PositionFormWithUser

    def get_node_additional_data(self, obj):
        """
        Дополнительные данные для каждого узла в древовидном представлении.

        Проверяет наличие:
        1. Индикаторы СИЗ и медосмотров (сначала переопределения, затем эталонные)
        2. Роли в комиссиях (из таблицы CommissionMember)
        3. Прочие атрибуты должности
        4. Инструкции по охране труда
        """
        # Базовая информация
        profession_icon = get_profession_icon(obj.position_name)

        # Проверяем наличие хотя бы одной инструкции
        instruction_parts = []
        if obj.safety_instructions_numbers and obj.safety_instructions_numbers.strip():
            instruction_parts.append(obj.safety_instructions_numbers.strip())
        if obj.contract_safety_instructions and obj.contract_safety_instructions.strip():
            instruction_parts.append(obj.contract_safety_instructions.strip())
        if obj.drives_company_vehicle and obj.company_vehicle_instructions and obj.company_vehicle_instructions.strip():
            instruction_parts.append(obj.company_vehicle_instructions.strip())

        has_any_instruction = bool(instruction_parts)
        instruction_numbers = ", ".join(instruction_parts)

        additional_data = {
            # Иконка профессии
            'profession_icon': profession_icon,

            # Основные атрибуты безопасности
            'is_responsible_for_safety': obj.is_responsible_for_safety,
            'can_be_internship_leader': obj.can_be_internship_leader,
            'can_sign_orders': obj.can_sign_orders,
            'is_electrical_personnel': obj.is_electrical_personnel,
            'electrical_group': obj.electrical_safety_group,
            'drives_company_vehicle': obj.drives_company_vehicle,

            # Инструкции по охране труда
            'instruction_numbers': instruction_numbers,
            'has_instructions': has_any_instruction,
        }

        # ===== СИЗ =====
        # 1. Проверяем переопределенные нормы СИЗ
        # ОПТИМИЗИРОВАНО: используем bool() вместо .exists() для prefetch'енных данных
        has_custom_siz_norms = bool(obj.siz_norms.all())

        # 2. Если переопределений нет, проверяем эталонные нормы
        # ОПТИМИЗИРОВАНО: используем кэш вместо запросов к БД
        has_reference_siz_norms = False
        if not has_custom_siz_norms:
            # Используем кэш, созданный в changelist_view
            has_reference_siz_norms = getattr(self, '_reference_siz_cache', {}).get(obj.position_name, False)

        # 3. Заполняем информацию о СИЗ с учётом флага переопределения
        if obj.siz_norms_overridden:
            # Нормы переопределены - игнорируем эталонные
            if has_custom_siz_norms:
                # Есть свои нормы → индикатор custom
                additional_data['has_siz_norms'] = True
                additional_data['siz_norms_type'] = 'custom'
                additional_data['siz_norms_title'] = 'Переопределенные нормы СИЗ для данной должности'
            else:
                # Нет своих норм → индикатор none (красный - "СИЗ не положены")
                additional_data['has_siz_norms'] = True
                additional_data['siz_norms_type'] = 'none'
                additional_data['siz_norms_title'] = '🚫 СИЗ не положены для данной должности'
        else:
            # Нормы НЕ переопределены - используем стандартную логику
            if has_custom_siz_norms:
                # Есть свои нормы (редкий случай без флага) → custom
                additional_data['has_siz_norms'] = True
                additional_data['siz_norms_type'] = 'custom'
                additional_data['siz_norms_title'] = 'Переопределенные нормы СИЗ для данной должности'
            elif has_reference_siz_norms:
                # Есть эталонные нормы → reference
                additional_data['has_siz_norms'] = True
                additional_data['siz_norms_type'] = 'reference'
                additional_data['siz_norms_title'] = 'Используются стандартные нормы СИЗ'
            else:
                # Ни своих, ни эталонных нет → индикатор не показываем
                additional_data['has_siz_norms'] = False
                additional_data['siz_norms_type'] = 'none'
                additional_data['siz_norms_title'] = 'Нет норм СИЗ'

        # ===== МЕДОСМОТРЫ =====
        # 1. Проверяем переопределенные нормы медосмотров
        # ОПТИМИЗИРОВАНО: используем bool() вместо .exists() для prefetch'енных данных
        has_custom_medical_norms = bool(obj.medical_factors.all())

        # 2. Если переопределений нет, проверяем эталонные нормы
        # ОПТИМИЗИРОВАНО: используем кэш вместо запросов к БД
        has_reference_medical_norms = False
        if not has_custom_medical_norms:
            # Используем кэш, созданный в changelist_view
            has_reference_medical_norms = getattr(self, '_reference_medical_cache', {}).get(obj.position_name, False)

        # 3. Заполняем информацию о медосмотрах с учётом флага переопределения
        if obj.medical_norms_overridden:
            # Нормы переопределены - игнорируем эталонные
            if has_custom_medical_norms:
                # Есть свои нормы → индикатор custom
                additional_data['has_medical_norms'] = True
                additional_data['medical_norms_type'] = 'custom'
                additional_data['medical_norms_title'] = 'Переопределенные нормы медосмотров для данной должности'
            else:
                # Нет своих норм → индикатор none (красный - "медосмотры не требуются")
                additional_data['has_medical_norms'] = True
                additional_data['medical_norms_type'] = 'none'
                additional_data['medical_norms_title'] = '🚫 Медосмотры не требуются для данной должности'
        else:
            # Нормы НЕ переопределены - используем стандартную логику
            if has_custom_medical_norms:
                # Есть свои нормы (редкий случай без флага) → custom
                additional_data['has_medical_norms'] = True
                additional_data['medical_norms_type'] = 'custom'
                additional_data['medical_norms_title'] = 'Переопределенные нормы медосмотров для данной должности'
            elif has_reference_medical_norms:
                # Есть эталонные нормы → reference
                additional_data['has_medical_norms'] = True
                additional_data['medical_norms_type'] = 'reference'
                additional_data['medical_norms_title'] = 'Используются стандартные нормы медосмотров'
            else:
                # Ни своих, ни эталонных нет → индикатор не показываем
                additional_data['has_medical_norms'] = False
                additional_data['medical_norms_type'] = 'none'
                additional_data['medical_norms_title'] = 'Нет норм медосмотров'

        # ===== РОЛИ В КОМИССИЯХ =====
        # ВРЕМЕННО ОТКЛЮЧЕНО для оптимизации (убрано 2400 SQL-запросов)
        # Эта информация не критична для древовидного представления
        # Если необходимо - можно добавить prefetch в get_queryset
        additional_data['commission_roles'] = []

        return additional_data

    def has_module_permission(self, request):
        """
        👮‍♂️ Проверка прав на доступ к модулю
        """
        if request.user.is_superuser:
            return True
        if hasattr(request.user, 'profile'):
            return request.user.profile.organizations.exists()
        return False

    def has_view_permission(self, request, obj=None):
        """
        👀 Проверка прав на просмотр
        """
        if request.user.is_superuser:
            return True
        if not obj:
            return True
        if hasattr(request.user, 'profile'):
            return obj.organization in request.user.profile.organizations.all()
        return False

    def has_change_permission(self, request, obj=None):
        """
        ✏️ Проверка прав на редактирование
        """
        return self.has_view_permission(request, obj)

    def has_delete_permission(self, request, obj=None):
        """
        🗑️ Проверка прав на удаление
        """
        return self.has_view_permission(request, obj)

    def import_view(self, request):
        """📥 Импорт организационной структуры"""
        context = self.admin_site.each_context(request)

        if request.method == 'POST':
            if 'confirm' in request.POST:
                # Финальное подтверждение импорта
                dataset_data = request.session.get('position_dataset')
                if not dataset_data:
                    messages.error(request, 'Данные для импорта не найдены. Загрузите файл заново.')
                    return redirect('admin:directory_position_import')

                dataset = Dataset().load(dataset_data)
                resource = OrganizationStructureResource()
                result = resource.import_data(dataset, dry_run=False)

                del request.session['position_dataset']

                messages.success(request, f'✅ Импорт завершен! Создано: {result.totals["new"]}, обновлено: {result.totals["update"]}')
                return redirect('admin:directory_position_changelist')
            else:
                # Предпросмотр импорта
                import_file = request.FILES.get('import_file')
                if not import_file:
                    messages.error(request, 'Файл не выбран')
                    return redirect('admin:directory_position_import')

                file_format = import_file.name.split('.')[-1].lower()
                if file_format not in ['xlsx', 'xls']:
                    messages.error(request, 'Поддерживаются только файлы XLSX и XLS')
                    return redirect('admin:directory_position_import')

                try:
                    dataset = Dataset().load(import_file.read(), format=file_format)
                    resource = OrganizationStructureResource()
                    result = resource.import_data(dataset, dry_run=True)

                    # Сохраняем данные в сессии для финального импорта
                    request.session['position_dataset'] = dataset.export('json')

                    context.update({
                        'title': 'Предпросмотр импорта организационной структуры',
                        'result': result,
                        'dataset': dataset,
                    })
                    return render(request, 'admin/directory/position/import_preview.html', context)
                except Exception as e:
                    messages.error(request, f'Ошибка при обработке файла: {str(e)}')
                    return redirect('admin:directory_position_import')

        context.update({
            'title': 'Импорт организационной структуры',
            'subtitle': None,
        })
        return render(request, 'admin/directory/position/import.html', context)

    def export_view(self, request):
        """📤 Экспорт организационной структуры"""
        from directory.models import Organization

        # Фильтрация по организации (если указана)
        organization_id = request.GET.get('organization_id')

        if organization_id:
            queryset = Position.objects.filter(organization_id=organization_id)
        else:
            queryset = Position.objects.all()

        # Применяем права доступа
        if not request.user.is_superuser and hasattr(request.user, 'profile'):
            allowed_orgs = request.user.profile.organizations.all()
            queryset = queryset.filter(organization__in=allowed_orgs)

        queryset = queryset.select_related('organization', 'subdivision', 'department')

        resource = OrganizationStructureResource()
        dataset = resource.export(queryset)

        response = HttpResponse(
            dataset.export('xlsx'),
            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
        response['Content-Disposition'] = 'attachment; filename="organization_structure.xlsx"'
        return response

    def copy_instructions_from_template(self, request, queryset):
        """
        🔄 Массовое действие для тиражирования инструкций и атрибутов между должностями.

        Логика:
        1. Пользователь выбирает ОДНУ должность-эталон
        2. Система находит все должности с таким же названием в той же организации
        3. Копирует атрибуты и инструкции

        Копируются поля:
        - safety_instructions_numbers (основные инструкции по ОТ) - если пусто
        - company_vehicle_instructions (для водителей) - если пусто и drives_company_vehicle=True
        - is_responsible_for_safety (ответственный за ОТ) - если True у эталона
        - can_be_internship_leader (может быть руководителем стажировки) - если True у эталона
        - can_sign_orders (может подписывать распоряжения) - если True у эталона
        """
        # Проверка: выбрана ровно 1 должность
        if queryset.count() != 1:
            self.message_user(
                request,
                'Выберите ровно одну должность-эталон с инструкциями для тиражирования.',
                level=messages.ERROR
            )
            return

        template_position = queryset.first()

        # Проверка: у эталона есть хотя бы что-то для тиражирования
        has_safety_instructions = bool(
            template_position.safety_instructions_numbers and
            template_position.safety_instructions_numbers.strip()
        )
        has_vehicle_instructions = bool(
            template_position.company_vehicle_instructions and
            template_position.company_vehicle_instructions.strip()
        )
        has_attributes = (
            template_position.is_responsible_for_safety or
            template_position.can_be_internship_leader or
            template_position.can_sign_orders
        )

        if not has_safety_instructions and not has_vehicle_instructions and not has_attributes:
            self.message_user(
                request,
                f'У выбранной должности "{template_position.position_name}" нет инструкций или атрибутов для тиражирования.',
                level=messages.WARNING
            )
            return

        # Находим все должности с таким же названием в той же организации
        candidates = Position.objects.filter(
            position_name=template_position.position_name,
            organization=template_position.organization,
        ).exclude(
            id=template_position.id
        ).select_related('subdivision')

        if not candidates.exists():
            self.message_user(
                request,
                f'Не найдено других должностей "{template_position.position_name}" '
                f'в организации "{template_position.organization.short_name_ru}".',
                level=messages.WARNING
            )
            return

        # Копируем инструкции и атрибуты
        updated_count = 0
        updated_safety_count = 0
        updated_vehicle_count = 0
        updated_responsible_count = 0
        updated_internship_leader_count = 0
        updated_sign_orders_count = 0

        for position in candidates:
            updated = False

            # 1. Основные инструкции по ОТ (только если пусто)
            if has_safety_instructions:
                if not position.safety_instructions_numbers or not position.safety_instructions_numbers.strip():
                    position.safety_instructions_numbers = template_position.safety_instructions_numbers
                    updated = True
                    updated_safety_count += 1

            # 2. Инструкции для водителей (только если пусто и drives_company_vehicle=True)
            if has_vehicle_instructions and position.drives_company_vehicle:
                if not position.company_vehicle_instructions or not position.company_vehicle_instructions.strip():
                    position.company_vehicle_instructions = template_position.company_vehicle_instructions
                    updated = True
                    updated_vehicle_count += 1

            # 3. Флаг "Ответственный за ОТ" (копируем если True у эталона и False у кандидата)
            if template_position.is_responsible_for_safety and not position.is_responsible_for_safety:
                position.is_responsible_for_safety = True
                updated = True
                updated_responsible_count += 1

            # 4. Флаг "Может быть руководителем стажировки" (копируем если True у эталона и False у кандидата)
            if template_position.can_be_internship_leader and not position.can_be_internship_leader:
                position.can_be_internship_leader = True
                updated = True
                updated_internship_leader_count += 1

            # 5. Флаг "Может подписывать распоряжения" (копируем если True у эталона и False у кандидата)
            if template_position.can_sign_orders and not position.can_sign_orders:
                position.can_sign_orders = True
                updated = True
                updated_sign_orders_count += 1

            if updated:
                position.save()
                updated_count += 1

        # Формируем сообщение о результате
        if updated_count > 0:
            details = []
            if updated_safety_count > 0:
                details.append(f'📋 инструкции по ОТ: {updated_safety_count} должн.')
            if updated_vehicle_count > 0:
                details.append(f'🚗 инструкции водителей: {updated_vehicle_count} должн.')
            if updated_responsible_count > 0:
                details.append(f'🔰 ответственный за ОТ: {updated_responsible_count} должн.')
            if updated_internship_leader_count > 0:
                details.append(f'🎓 руководитель стажировки: {updated_internship_leader_count} должн.')
            if updated_sign_orders_count > 0:
                details.append(f'📝 подпись распоряжений: {updated_sign_orders_count} должн.')

            message = (
                f'✅ Обновлено {updated_count} должностей '
                f'"{template_position.position_name}": {", ".join(details)}'
            )
            self.message_user(request, message, level=messages.SUCCESS)
        else:
            self.message_user(
                request,
                f'Все должности "{template_position.position_name}" уже имеют все атрибуты и инструкции. '
                f'Тиражирование не требуется.',
                level=messages.INFO
            )

    copy_instructions_from_template.short_description = '🔄 Заполнить инструкции и атрибуты из эталона'

    def copy_to_subdivision(self, request, queryset):
        """📋 Копировать выбранные должности в другое структурное подразделение."""
        from directory.models import StructuralSubdivision
        from directory.models.siz import SIZNorm
        from deadline_control.models.medical_norm import PositionMedicalFactor

        # Шаг 2: пришло подтверждение с выбранным подразделением
        if request.POST.get('confirm_copy'):
            target_subdivision_id = request.POST.get('target_subdivision') or None
            position_ids = request.POST.getlist('position_ids')

            if not position_ids:
                self.message_user(request, 'Не переданы ID должностей.', level=messages.ERROR)
                return

            positions = Position.objects.filter(pk__in=position_ids)

            if target_subdivision_id:
                try:
                    target_subdivision = StructuralSubdivision.objects.get(pk=target_subdivision_id)
                except StructuralSubdivision.DoesNotExist:
                    self.message_user(request, 'Выбранное подразделение не найдено.', level=messages.ERROR)
                    return
                target_org = target_subdivision.organization
            else:
                target_subdivision = None
                # Организацию берём из первой должности — все должны быть одной орг.
                target_org = positions.first().organization

            created, skipped = 0, 0
            for pos in positions:
                # Проверяем уникальность: такая же должность в целевом подразделении
                if Position.objects.filter(
                    position_name=pos.position_name,
                    organization=target_org,
                    subdivision=target_subdivision,
                    department=None,
                ).exists():
                    skipped += 1
                    continue

                # Создаём копию
                new_pos = Position(
                    position_name=pos.position_name,
                    organization=target_org,
                    subdivision=target_subdivision,
                    department=None,
                    safety_instructions_numbers=pos.safety_instructions_numbers,
                    electrical_safety_group=pos.electrical_safety_group,
                    internship_period_days=pos.internship_period_days,
                    is_responsible_for_safety=pos.is_responsible_for_safety,
                    is_electrical_personnel=pos.is_electrical_personnel,
                    can_be_internship_leader=pos.can_be_internship_leader,
                    can_sign_orders=pos.can_sign_orders,
                    drives_company_vehicle=pos.drives_company_vehicle,
                    requires_siz=pos.requires_siz,
                    siz_norms_overridden=pos.siz_norms_overridden,
                    medical_norms_overridden=pos.medical_norms_overridden,
                )
                new_pos.save()

                # M2M: документы, оборудование, виды ответственности
                new_pos.documents.set(pos.documents.all())
                new_pos.equipment.set(pos.equipment.all())
                new_pos.responsibility_types.set(pos.responsibility_types.all())

                # Нормы СИЗ (переопределённые)
                for norm in pos.siz_norms.all():
                    SIZNorm.objects.create(
                        position=new_pos,
                        siz=norm.siz,
                        condition=norm.condition,
                        quantity=norm.quantity,
                        order=norm.order,
                    )

                # Медицинские факторы
                for mf in pos.medical_factors.all():
                    PositionMedicalFactor.objects.create(
                        position=new_pos,
                        harmful_factor=mf.harmful_factor,
                        periodicity_override=mf.periodicity_override,
                        is_disabled=mf.is_disabled,
                        notes=mf.notes,
                    )

                created += 1

            parts = []
            if created:
                parts.append(f'создано {created} должн.')
            if skipped:
                parts.append(f'пропущено {skipped} (уже существуют)')
            sub_label = target_subdivision.name if target_subdivision else 'без подразделения'
            self.message_user(
                request,
                f'Копирование в «{sub_label}» завершено: {", ".join(parts)}.',
                level=messages.SUCCESS if created else messages.WARNING,
            )
            return

        # Шаг 1: показать форму выбора подразделения
        orgs = queryset.values_list('organization_id', flat=True).distinct()
        subdivisions = StructuralSubdivision.objects.filter(
            organization_id__in=orgs
        ).select_related('organization').order_by('organization__short_name_ru', 'name')

        return render(request, 'admin/directory/position/copy_to_subdivision.html', {
            'queryset': queryset,
            'subdivisions': subdivisions,
            'opts': self.model._meta,
            'title': 'Копировать должности в другое подразделение',
            **self.admin_site.each_context(request),
        })

    copy_to_subdivision.short_description = '📋 Скопировать в другое подразделение'
