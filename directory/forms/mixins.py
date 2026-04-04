"""
🔀 Миксины для форм

Этот файл содержит:
1. 🔒 OrganizationRestrictionFormMixin - базовый миксин для ограничения выборок по организациям
2. 🎨 CrispyFormMixin - миксин для стилизации форм с помощью django-crispy-forms
3. 🎨🔒 CrispyOrganizationFormMixin - комбинированный миксин для форм с ограничением и стилизацией
"""
from django import forms
from crispy_forms.helper import FormHelper
from crispy_forms.layout import Submit, Layout, Div, HTML, Field, ButtonHolder
from crispy_forms.bootstrap import FormActions, PrependedText, AppendedText


class OrganizationRestrictionFormMixin:
    """
    🔒 Миксин для ограничения выборок по организациям, доступным пользователю.

    Применение:
    - Поле "organization" будет ограничено организациями из профиля пользователя. 🏢
    - Поля "subdivision", "department", "position", "document" и "equipment" будут
      фильтроваться по organization, если такие поля есть в модели. 🔍
    """

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop('user', None)
        initial_org_id = kwargs.pop('initial_org_id', None)
        super().__init__(*args, **kwargs)

        # Суперпользователям ничего не ограничиваем
        # Всегда включаем организацию текущего инстанса, чтобы не терять выбранное значение при редактировании
        instance_org = getattr(getattr(self, 'instance', None), 'organization', None)
        is_new_instance = not getattr(getattr(self, 'instance', None), 'pk', None)

        from directory.models import Organization  # локальный импорт, чтобы избежать циклов

        if self.user and (getattr(self.user, 'is_superuser', False) or getattr(self.user, 'is_staff', False)):
            allowed_orgs = Organization.objects.all()
        elif self.user and hasattr(self.user, 'profile'):
            allowed_orgs = self.user.profile.organizations.all()
        else:
            allowed_orgs = Organization.objects.none()

        # Подмешиваем текущую организацию, если она не входит в allowed_orgs
        if instance_org and instance_org.pk and instance_org not in allowed_orgs:
            allowed_orgs = allowed_orgs | Organization.objects.filter(pk=instance_org.pk)

        if 'organization' in self.fields:
            if initial_org_id and is_new_instance:
                # При создании нового объекта — ограничиваем queryset выбранной организацией
                # (если она входит в доступные) и предзаполняем поле
                restricted = allowed_orgs.filter(pk=initial_org_id)
                if restricted.exists():
                    self.fields['organization'].queryset = restricted
                    if not self.data.get('organization') and not self.initial.get('organization'):
                        self.initial['organization'] = initial_org_id
                else:
                    self.fields['organization'].queryset = allowed_orgs
            else:
                # При редактировании или без выбранной организации — стандартное поведение
                self.fields['organization'].queryset = allowed_orgs
                self.fields['organization'].initial = (
                    self.fields['organization'].initial or getattr(instance_org, 'pk', None)
                )
            self.fields['organization'].help_text = "🏢 Выберите организацию из разрешённых"

        for field_name in ['subdivision', 'department', 'position', 'document', 'equipment']:
            if field_name in self.fields:
                qs = self.fields[field_name].queryset
                # Если редактируем, включаем текущее значение даже если оно вне allowed_orgs
                current_obj = getattr(self.instance, field_name, None)
                current_value = getattr(current_obj, 'pk', None)
                filtered_qs = qs.filter(organization__in=allowed_orgs)
                if current_value:
                    filtered_qs = filtered_qs | qs.filter(pk=current_value)
                self.fields[field_name].queryset = filtered_qs
                if current_value and not self.fields[field_name].initial:
                    self.fields[field_name].initial = current_value
                self.fields[field_name].help_text = "🔍 Фильтрация по разрешённым организациям"


class CrispyFormMixin:
    """
    🎨 Миксин для стилизации форм с помощью crispy-forms

    Предоставляет базовую функциональность для всех форм:
    - Настройку FormHelper
    - Добавление кнопок отправки/отмены
    - Базовые классы Bootstrap
    - Управление макетом формы
    """

    # ⚙️ Настройки стилей по умолчанию (можно переопределить в дочерних классах)
    crispy_settings = {
        'form_class': 'form-horizontal',  # Класс для формы
        'label_class': 'col-lg-3',        # Класс для меток полей
        'field_class': 'col-lg-9',        # Класс для полей ввода
        'submit_text': 'Сохранить',       # Текст кнопки отправки
        'cancel_text': 'Отмена',          # Текст кнопки отмены
        'include_cancel': True,           # Включать ли кнопку отмены
        'submit_css_class': 'btn-primary' # Класс для кнопки отправки
    }

    def __init__(self, *args, **kwargs):
        """
        🏗️ Инициализация формы со стилизацией crispy

        Создаёт экземпляр FormHelper и настраивает его согласно настройкам.
        """
        # Вызываем инициализацию родительского класса
        super().__init__(*args, **kwargs)

        # Создаём помощник формы
        self.helper = FormHelper()

        # Применяем базовые настройки
        self.helper.form_method = 'post'
        self.helper.form_tag = False  # По умолчанию не включаем тег <form>

        # Применяем настройки классов из crispy_settings
        self.helper.form_class = self.crispy_settings.get('form_class')
        self.helper.label_class = self.crispy_settings.get('label_class')
        self.helper.field_class = self.crispy_settings.get('field_class')

        # Добавляем действия формы (кнопки)
        self._setup_form_actions()

    def _setup_form_actions(self):
        """
        🔘 Настройка кнопок действий формы

        Добавляет кнопку отправки формы и, если нужно, кнопку отмены.
        """
        # Создаём контейнер для кнопок
        actions = []

        # Добавляем кнопку отправки
        submit_text = self.crispy_settings.get('submit_text')
        submit_css = f"btn {self.crispy_settings.get('submit_css_class')}"
        actions.append(
            Submit('submit', submit_text, css_class=submit_css)
        )

        # Добавляем кнопку отмены, если включена
        if self.crispy_settings.get('include_cancel'):
            cancel_text = self.crispy_settings.get('cancel_text')
            actions.append(
                HTML(f'<a href="javascript:history.back()" class="btn btn-secondary">{cancel_text}</a>')
            )

        # Добавляем контейнер действий в layout
        self.helper.add_input(actions[0])

        # Добавляем остальные действия, если есть
        for action in actions[1:]:
            self.helper.add_input(action)

    def set_layout(self, layout):
        """
        📐 Установка кастомного макета формы

        Позволяет задать произвольный макет полей формы через crispy Layout.

        Args:
            layout (Layout): Экземпляр crispy Layout с настройкой полей
        """
        self.helper.layout = layout

    def add_form_classes(self, *css_classes):
        """
        🎯 Добавление CSS-классов к форме

        Args:
            *css_classes: Строки с CSS-классами для добавления
        """
        existing = self.helper.form_class.split() if self.helper.form_class else []
        self.helper.form_class = ' '.join(existing + list(css_classes))

    def set_form_action(self, url):
        """
        🔗 Установка URL для отправки формы

        Args:
            url (str): URL, куда будет отправлена форма
        """
        self.helper.form_action = url
        self.helper.form_tag = True  # Включаем тег <form>, если задан action


class CrispyOrganizationFormMixin(OrganizationRestrictionFormMixin, CrispyFormMixin):
    """
    🎨🔒 Комбинированный миксин для форм с ограничением по организациям и стилизацией crispy

    Объединяет функциональность:
    - Ограничение доступа к организациям по профилю пользователя
    - Стилизация форм через crispy-forms
    """

    def __init__(self, *args, **kwargs):
        """
        🏗️ Инициализация комбинированного миксина
        """
        super().__init__(*args, **kwargs)

        # Добавляем подсветку для полей, связанных с организациями
        for field_name in ['organization', 'subdivision', 'department', 'position', 'document', 'equipment']:
            if field_name in self.fields:
                # Добавляем класс для визуального выделения организационных полей
                self.fields[field_name].widget.attrs['class'] = 'org-field'
