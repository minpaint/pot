import json

from django.contrib import admin
from django.urls import reverse
from django.utils.html import format_html
from directory.models.siz import SIZ, SIZNorm, ProfessionSIZNorm
from directory.models.position import Position
from directory.forms.siz import SIZForm, SIZNormForm
from import_export import resources, fields, widgets
from import_export.admin import ImportExportModelAdmin
from django.db.models import Count, Case, When, Value, IntegerField, Q
from django.utils.translation import ngettext
from django.contrib import messages
from django.db import IntegrityError, transaction
from django.db.models.functions import Lower
from directory.resources.siz_norm import SIZNormResource
from directory.resources.profession_siz_norm import ProfessionSIZNormResource


class WearPeriodWidget(widgets.IntegerWidget):
    """Виджет для обработки поля 'Срок носки' с поддержкой текста 'До износа' и 'Дежурный/ая/ые'"""

    def clean(self, value, row=None, **kwargs):
        """Преобразует текст 'До износа' и 'Дежурный/ая/ые' в 0 и сохраняет тип в wear_type"""
        if isinstance(value, str):
            value_stripped = value.strip()
            value_lower = value_stripped.lower()

            # Список особых типов выдачи
            special_types = {
                'до износа': 'До износа',
                'доизноса': 'До износа',
                'до_износа': 'До износа',
                'дежурный': 'Дежурный',
                'дежурная': 'Дежурная',
                'дежурные': 'Дежурные',
                'дежурное': 'Дежурное'
            }

            if value_lower in special_types:
                # Сохраняем тип выдачи в row для последующего использования
                if row is not None:
                    row['wear_type'] = special_types[value_lower]
                return 0

        # Для числовых значений очищаем wear_type
        if row is not None:
            row['wear_type'] = ''

        # Для остальных значений используем стандартную обработку
        return super().clean(value, row, **kwargs)


class SIZResource(resources.ModelResource):
    """🔄 Ресурс для импорта/экспорта данных СИЗ"""

    wear_period = fields.Field(
        column_name='wear_period',
        attribute='wear_period',
        widget=WearPeriodWidget()
    )

    class Meta:
        model = SIZ
        fields = ('name', 'classification', 'unit', 'wear_period', 'wear_type', 'cost')
        export_order = ('name', 'classification', 'unit', 'wear_period', 'wear_type', 'cost')
        import_id_fields = []  # Пустой список означает "всегда создавать новые записи"
        skip_unchanged = False
        report_skipped = False


@admin.register(SIZ)
class SIZAdmin(ImportExportModelAdmin):
    """🛡️ Административный интерфейс для СИЗ"""
    resource_class = SIZResource
    form = SIZForm
    list_display = ('name', 'classification', 'unit', 'get_wear_period', 'cost', 'norms_count')
    list_filter = ('classification', 'unit')
    search_fields = ('name', 'classification')
    fieldsets = (
        ('Основная информация', {
            'fields': ('name', 'classification', 'unit', 'wear_period', 'wear_type', 'cost')
        }),
    )

    def get_wear_period(self, obj):
        """🕒 Получение отображаемого значения срока носки"""
        if obj.wear_period == 0:
            return obj.wear_type if obj.wear_type else "До износа"
        return f"{obj.wear_period} мес."

    get_wear_period.short_description = "Срок носки"

    def norms_count(self, obj):
        """🔢 Количество норм, где используется данное СИЗ"""
        count = obj.norms.count()
        if count > 0:
            url = reverse('admin:directory_siznorm_changelist') + f'?siz__id__exact={obj.id}'
            return format_html('<a href="{}">{} норм</a>', url, count)
        return "0 норм"

    norms_count.short_description = "Использование"


class SIZNormInline(admin.TabularInline):
    """📋 Встроенный интерфейс для норм выдачи СИЗ"""
    model = SIZNorm
    extra = 1
    fields = ('siz', 'classification_display', 'unit_display', 'quantity', 'condition', 'wear_period_display')
    readonly_fields = ('classification_display', 'unit_display', 'wear_period_display')
    autocomplete_fields = ['siz']

    def classification_display(self, obj):
        """🏷️ Отображение классификации СИЗ"""
        return obj.siz.classification if obj.siz else '-'

    classification_display.short_description = "Классификация"

    def unit_display(self, obj):
        """📏 Отображение единицы измерения СИЗ"""
        return obj.siz.unit if obj.siz else '-'

    unit_display.short_description = "Единица измерения"

    def wear_period_display(self, obj):
        """🕒 Отображение срока носки СИЗ"""
        if not obj.siz:
            return '-'
        return "До износа" if obj.siz.wear_period == 0 else f"{obj.siz.wear_period} мес."

    wear_period_display.short_description = "Срок носки"


class SIZNormInlineForPosition(admin.TabularInline):
    """📋 Встроенные нормы СИЗ для должности с группировкой по условиям"""
    model = SIZNorm
    extra = 1
    fields = ('siz', 'quantity', 'condition', 'order')
    verbose_name = "Переопределённая норма СИЗ"
    verbose_name_plural = "Переопределённые нормы СИЗ"
    autocomplete_fields = ['siz']

    def get_queryset(self, request):
        """🔍 Оптимизация запроса для получения всех норм для должности"""
        return super().get_queryset(request)


@admin.register(SIZNorm)
class SIZNormAdmin(ImportExportModelAdmin):
    """📊 Административный интерфейс для норм выдачи СИЗ"""
    resource_class = SIZNormResource
    form = SIZNormForm
    change_form_template = "admin/directory/siznorm/change_form.html"
    list_display = ('position', 'siz', 'quantity', 'get_condition', 'order')
    list_filter = ('position', 'condition', 'siz')
    search_fields = ('position__position_name', 'siz__name', 'condition')
    # autocomplete_fields убран - виджет настраивается в форме через formfield_overrides
    # Указываем шаблон для отображения древовидной структуры
    change_list_template = "admin/directory/siznorm/change_list_tree.html"

    fieldsets = (
        ('Основная информация', {
            'fields': ('unique_position_name', 'quantity', 'order')
        }),
        ('Условия выдачи', {
            'fields': ('condition',),
            'description': 'Укажите условие выдачи СИЗ (например, "При работе в зимнее время", "При влажной уборке" и т.д.)'
        }),
    )
    def get_condition(self, obj):
        """📝 Получение условия выдачи для отображения в списке"""
        return obj.condition if obj.condition else "Основная норма"

    get_condition.short_description = "Условие выдачи"

    def current_siz_display(self, obj):
        """Текущий СИЗ для формы редактирования."""
        if not obj or not obj.siz:
            return "-"
        if obj.siz.classification:
            return f"{obj.siz.name} ({obj.siz.classification})"
        return obj.siz.name

    current_siz_display.short_description = "Текущий СИЗ"

    def get_fieldsets(self, request, obj=None):
        if obj is None:
            return [
                ('Основная информация', {
                    'fields': ('unique_position_name', 'quantity', 'order')
                }),
            ]

        return [
            ('Основная информация', {
                'fields': ('unique_position_name', 'current_siz_display', 'quantity', 'order')
            }),
            ('Условия выдачи', {
                'fields': ('condition',),
                'description': 'Укажите условие выдачи СИЗ для текущей нормы.'
            }),
        ]

    def get_readonly_fields(self, request, obj=None):
        readonly_fields = list(super().get_readonly_fields(request, obj))
        if obj is not None:
            readonly_fields.append('current_siz_display')
        return readonly_fields

    def _get_batch_siz_choices(self):
        choices = []
        for siz in SIZ.objects.order_by('name', 'classification'):
            choices.append({
                'id': siz.pk,
                'label': f"{siz.name} ({siz.classification})" if siz.classification else siz.name,
            })
        return choices

    def _get_batch_condition_choices(self):
        return list(
            SIZNorm.objects.exclude(condition='')
            .order_by('condition')
            .values_list('condition', flat=True)
            .distinct()[:200]
        )

    def render_change_form(self, request, context, add=False, change=False, form_url='', obj=None):
        form = context.get('adminform').form
        raw_groups = form.data.get('batch_groups_json') if form.is_bound else form.initial.get('batch_groups_json', '')
        try:
            initial_groups = json.loads(raw_groups) if raw_groups else []
        except json.JSONDecodeError:
            initial_groups = []

        context = {
            **context,
            'batch_siz_choices': self._get_batch_siz_choices(),
            'batch_condition_choices': self._get_batch_condition_choices(),
            'batch_initial_groups_json': json.dumps(initial_groups),
            'batch_group_title': 'Группы СИЗ для добавления' if add else 'Добавить ещё группы СИЗ',
            'batch_group_description': (
                'Каждая группа создаёт свои нормы СИЗ. Оставьте условие пустым для основной нормы '
                'или заполните его для дополнительной.'
                if add else
                'Текущая норма редактируется выше. Ниже можно добавить ещё группы СИЗ: '
                'пустое условие создаст основные нормы, заполненное - дополнительные.'
            ),
        }
        return super().render_change_form(request, context, add=add, change=change, form_url=form_url, obj=obj)

    def get_form(self, request, obj=None, **kwargs):
        """Получение формы с передачей дополнительных параметров"""
        position_id = request.GET.get('position')
        Form = super().get_form(request, obj, **kwargs)

        if position_id:
            # Создаем замыкание с position_id
            class FormWithPosition(Form):
                def __new__(cls, *args, **kwargs):
                    kwargs['position_id'] = position_id
                    return Form(*args, **kwargs)

            return FormWithPosition
        return Form

    def save_model(self, request, obj, form, change):
        """Создает дополнительные нормы при пакетном добавлении."""
        super().save_model(request, obj, form, change)

        batch_groups = form.cleaned_data.get('batch_groups') or []
        if not batch_groups:
            return

        next_order = (obj.order or 0) + 10
        created_count = 0
        skipped_count = 0

        for group in batch_groups:
            group_condition = group['condition']
            for siz in group['sizs']:
                if siz.pk == obj.siz_id and group_condition == obj.condition:
                    continue

                if SIZNorm.objects.filter(
                    position=obj.position,
                    siz=siz,
                    condition=group_condition,
                ).exists():
                    skipped_count += 1
                    continue

                try:
                    with transaction.atomic():
                        SIZNorm.objects.create(
                            position=obj.position,
                            siz=siz,
                            quantity=obj.quantity,
                            condition=group_condition,
                            order=next_order,
                        )
                    next_order += 10
                    created_count += 1
                except IntegrityError:
                    skipped_count += 1

        if created_count:
            messages.success(
                request,
                f"Добавление групп СИЗ: дополнительно создано {created_count} норм."
            )
        if skipped_count:
            messages.warning(
                request,
                f"Добавление групп СИЗ: пропущено дублей {skipped_count}."
            )

    def changelist_view(self, request, extra_context=None):
        """
        📋 Представление списка норм СИЗ с группировкой по профессиям и условиям

        Формирует структуру данных для шаблона, где нормы СИЗ группируются:
        1. По названиям профессий/должностей
        2. По условиям выдачи СИЗ внутри каждой профессии
        """
        extra_context = extra_context or {}

        # Получаем уникальные названия профессий, у которых есть нормы СИЗ
        position_names = Position.objects.filter(
            siz_norms__isnull=False
        ).values_list('position_name', flat=True).distinct().order_by(Lower('position_name'))

        # Данные профессий
        professions_data = []

        for position_name in position_names:
            # Получаем все должности с таким названием
            positions = Position.objects.filter(position_name=position_name)

            # Берем первую должность с нормами как эталонную (по алфавиту организаций)
            reference_position = positions.filter(
                siz_norms__isnull=False
            ).order_by('organization__full_name_ru').first()

            if not reference_position:
                continue

            # Получаем все нормы СИЗ для эталонной должности
            all_norms = SIZNorm.objects.filter(position=reference_position).select_related('siz', 'position')

            # Базовые нормы (без условий)
            base_norms = all_norms.filter(condition='').order_by('order', 'id')

            # 🔄 ИСПРАВЛЕНИЕ: Получаем уникальные условия и группируем нормы более эффективно
            # Используем словарь для хранения сгруппированных норм, чтобы избежать дублирования
            grouped_norms = {}

            # Выбираем только нормы с условиями
            condition_norms = all_norms.exclude(condition='')

            # Группируем нормы по названию условия
            for norm in condition_norms:
                condition_name = norm.condition

                # Инициализируем список для условия, если он еще не существует
                if condition_name not in grouped_norms:
                    grouped_norms[condition_name] = []

                # Добавляем норму в группу, избегая дублирования
                # Проверяем, нет ли уже такой комбинации СИЗ+условие
                norm_key = f"{norm.siz_id}_{norm.condition}"
                exists = False
                for existing_norm in grouped_norms[condition_name]:
                    existing_key = f"{existing_norm.siz_id}_{existing_norm.condition}"
                    if existing_key == norm_key:
                        exists = True
                        break

                if not exists:
                    grouped_norms[condition_name].append(norm)

            # Преобразуем словарь в список для шаблона
            group_norms = []
            for condition_name, norms in grouped_norms.items():
                # Сортируем нормы по порядку
                sorted_norms = sorted(norms, key=lambda x: (x.order, x.id))
                group_norms.append({
                    'name': condition_name,
                    'norms': sorted_norms
                })

            # Добавляем информацию о профессии
            profession_data = {
                'name': position_name,
                'positions': positions,
                'base_norms': base_norms,
                'group_norms': group_norms,
            }

            professions_data.append(profession_data)

        extra_context['professions'] = professions_data

        return super().changelist_view(request, extra_context)


@admin.register(ProfessionSIZNorm)
class ProfessionSIZNormAdmin(ImportExportModelAdmin):
    """📖 Административный интерфейс для эталонных норм СИЗ профессий"""
    resource_class = ProfessionSIZNormResource
    list_display = ('profession_name', 'siz', 'quantity', 'get_condition', 'order')
    list_filter = ('profession_name',)
    search_fields = ('profession_name', 'siz__name', 'condition')
    autocomplete_fields = ['siz']
    ordering = ['profession_name', 'condition', 'order', 'siz__name']

    # Используем кастомный шаблон для древовидного отображения
    change_list_template = "admin/directory/professionsiznorm/change_list_tree.html"

    fieldsets = (
        ('Основная информация', {
            'fields': ('profession_name', 'siz', 'quantity', 'order')
        }),
        ('Условия выдачи', {
            'fields': ('condition',),
            'description': 'Укажите условие выдачи СИЗ (например, "При работе в зимнее время", "При влажной уборке" и т.д.)'
        }),
    )

    def get_condition(self, obj):
        """📝 Получение условия выдачи для отображения в списке"""
        return obj.condition if obj.condition else "Основная норма"

    get_condition.short_description = "Условие выдачи"

    def changelist_view(self, request, extra_context=None):
        """
        📋 Представление списка эталонных норм СИЗ с группировкой по профессиям

        Формирует структуру данных для шаблона, где нормы СИЗ группируются:
        1. По названиям профессий
        2. По условиям выдачи СИЗ внутри каждой профессии
        """
        extra_context = extra_context or {}

        # Получаем уникальные названия профессий, у которых есть эталонные нормы СИЗ
        profession_names = ProfessionSIZNorm.objects.values_list(
            'profession_name', flat=True
        ).distinct().order_by(Lower('profession_name'))

        # Данные профессий
        professions_data = []

        for profession_name in profession_names:
            # Получаем все нормы для профессии
            all_norms = ProfessionSIZNorm.objects.filter(
                profession_name=profession_name
            ).select_related('siz')

            # Базовые нормы (без условий)
            base_norms = all_norms.filter(condition='').order_by('order', 'id')

            # Группируем нормы по условиям
            grouped_norms = {}
            condition_norms = all_norms.exclude(condition='')

            for norm in condition_norms:
                condition_name = norm.condition
                if condition_name not in grouped_norms:
                    grouped_norms[condition_name] = []
                grouped_norms[condition_name].append(norm)

            # Преобразуем словарь в список для шаблона
            group_norms = []
            for condition_name, norms in grouped_norms.items():
                sorted_norms = sorted(norms, key=lambda x: (x.order, x.id))
                group_norms.append({
                    'name': condition_name,
                    'norms': sorted_norms
                })

            # Получаем количество должностей с таким названием
            positions_count = Position.objects.filter(position_name=profession_name).count()

            # Добавляем информацию о профессии
            profession_data = {
                'name': profession_name,
                'positions_count': positions_count,
                'base_norms': base_norms,
                'group_norms': group_norms,
            }

            professions_data.append(profession_data)

        extra_context['professions'] = professions_data

        return super().changelist_view(request, extra_context)
