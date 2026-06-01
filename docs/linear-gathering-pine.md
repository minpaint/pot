# План: Встраивание Dogovor (contracts + taxes) в OT_online — только для суперпользователя

## Контекст

Существует отдельный проект **Dogovor** (`G:\Мой диск\OT_online\Dogovor\`), включающий два Django-приложения:
- **contracts** — клиенты, договора, акты выполненных работ, генерация DOCX, конвертация валют по курсу НБРБ
- **taxes** — расчёт налогов ИП по кварталам

Нужно встроить оба приложения в основной проект **OT_online** как блок, видимый **только суперпользователю** (`is_superuser`):
- В Django admin — раздел «Договоры и акты»
- На фронтэнде (dashboard) — виджет с краткой статистикой

---

## Шаги реализации

### 1. Установить недостающие Python-пакеты

В вирт. окружении `c:\venvs\OT_online` уже есть `docxtpl`, но отсутствуют:
- `num2words` — для суммы прописью в `contracts/docx_builder.py`
- `docxcompose` — для объединения актов в один DOCX

```bash
c:\venvs\OT_online\Scripts\pip.exe install num2words docxcompose
```

### 2. Скопировать app-директории и DOCX-шаблоны

- `Dogovor/contracts/` → `OT_online/contracts/`
- `Dogovor/taxes/` → `OT_online/taxes/`
- `Dogovor/templates_docx/` → `OT_online/templates_docx/`

### 3. Исправить путь к DOCX-шаблонам в `contracts/docx_builder.py`

**Файл:** `contracts/docx_builder.py`

Найти строку:
```python
TEMPLATES_DIR = Path(__file__).parent.parent / "templates_docx"
```
Заменить на:
```python
from django.conf import settings
TEMPLATES_DIR = settings.BASE_DIR / "templates_docx"
```

### 4. Добавить SuperuserOnlyMixin к admin-классам

Чтобы **никто, кроме суперпользователя**, не мог видеть и редактировать договоры/налоги в admin — добавить миксин в начало **`contracts/admin.py`**:

```python
class SuperuserOnlyMixin:
    def has_view_permission(self, request, obj=None):
        return request.user.is_superuser
    def has_add_permission(self, request):
        return request.user.is_superuser
    def has_change_permission(self, request, obj=None):
        return request.user.is_superuser
    def has_delete_permission(self, request, obj=None):
        return request.user.is_superuser
```

Применить ко всем admin-классам:
```python
class ClientAdmin(SuperuserOnlyMixin, admin.ModelAdmin): ...
class ContractAdmin(SuperuserOnlyMixin, admin.ModelAdmin): ...
class ActAdmin(SuperuserOnlyMixin, admin.ModelAdmin): ...
```

Аналогично добавить миксин в **`taxes/admin.py`** (для `TaxYearAdmin`, `TaxQuarterAdmin`).

### 5. Исправить SQLite-специфичную миграцию 0006

**Файл:** `contracts/migrations/0006_fix_act_is_paid_default.py`

Миграция содержит SQLite-специфичный RAW SQL (`INTEGER PRIMARY KEY AUTOINCREMENT`), который сломает PostgreSQL в продакшне. Заменить содержимое `operations` на no-op:

```python
operations = [
    migrations.RunSQL("SELECT 1;", "SELECT 1;"),
]
```

(На свежей базе OT_online колонка `is_paid` создаётся корректно через `AddField` из `0003`.)

### 6. Добавить приложения в `settings.py`

**Файл:** `G:\Мой диск\OT_online\settings.py`

В `INSTALLED_APPS` добавить:
```python
'contracts',
'taxes',
```

### 7. Добавить раздел в меню `OTAdminSite`

**Файл:** `G:\Мой диск\OT_online\config\admin_site.py`

В `MENU_ORDER` добавить новый раздел:
```python
(_("💼 Договоры и акты"), [
    "Client", "Contract", "Act",
    "TaxYear", "TaxQuarter",
]),
```

Django auto-discovery подхватит `contracts/admin.py` и `taxes/admin.py` автоматически, т.к. `config.apps.OTAdminConfig` реализует `AdminConfig` с автодискавери.

### 8. Фронтэнд-виджет на dashboard (только `is_superuser`)

**Файл:** `G:\Мой диск\OT_online\deadline_control\views\dashboard.py`

В метод `get_context_data()` добавить блок:
```python
if user.is_superuser:
    from contracts.models import Act
    from django.db.models import Sum, Count, Q
    contracts_stats = Act.objects.aggregate(
        unpaid_count=Count('id', filter=Q(is_paid=False)),
        unpaid_sum=Sum('amount', filter=Q(is_paid=False)),
    )
    context['contracts_stats'] = contracts_stats
```

**Файл:** `G:\Мой диск\OT_online\templates\deadline_control\dashboard.html`

Добавить виджет в конец блока `{% block content %}`, перед `{% endblock %}`:
```html
{% if user.is_superuser %}
<div class="row mt-4">
  <div class="col-md-4">
    <div class="card border-warning">
      <div class="card-header bg-warning text-dark fw-bold">💼 Договоры и акты</div>
      <div class="card-body">
        <p class="mb-1">Неоплаченных актов: <strong>{{ contracts_stats.unpaid_count|default:0 }}</strong></p>
        <p class="mb-2">Долг: <strong>{{ contracts_stats.unpaid_sum|default:"0.00" }} руб.</strong></p>
        <a href="/admin/contracts/act/" class="btn btn-sm btn-warning">Открыть акты →</a>
      </div>
    </div>
  </div>
</div>
{% endif %}
```

---

## Критические файлы

| Файл | Действие |
|------|----------|
| `contracts/` (новая директория) | Скопировать из `Dogovor/contracts/` |
| `taxes/` (новая директория) | Скопировать из `Dogovor/taxes/` |
| `templates_docx/` (новая директория) | Скопировать из `Dogovor/templates_docx/` |
| `contracts/docx_builder.py` | Исправить `TEMPLATES_DIR` на `settings.BASE_DIR / "templates_docx"` |
| `contracts/admin.py` | Добавить `SuperuserOnlyMixin` ко всем 3 admin-классам |
| `taxes/admin.py` | Добавить `SuperuserOnlyMixin` ко всем admin-классам |
| `contracts/migrations/0006_*.py` | Заменить `operations` на no-op `RunSQL("SELECT 1;", "SELECT 1;")` |
| `settings.py` | Добавить `'contracts'`, `'taxes'` в `INSTALLED_APPS` |
| `config/admin_site.py` | Добавить раздел `💼 Договоры и акты` в `MENU_ORDER` |
| `deadline_control/views/dashboard.py` | Добавить `contracts_stats` для суперпользователя |
| `templates/deadline_control/dashboard.html` | Добавить виджет с guard `{% if user.is_superuser %}` |

---

## Проверка

```bash
# 1. Установить пакеты
c:\venvs\OT_online\Scripts\pip.exe install num2words docxcompose

# 2. Применить миграции
py manage.py migrate

# 3. Проверить отсутствие системных ошибок
py manage.py check

# 4. Запустить сервер
py manage.py runserver

# 5. Открыть /admin/ как суперпользователь
#    → должен быть раздел "💼 Договоры и акты" с клиентами, договорами, актами, налогами

# 6. Открыть /admin/ как обычный staff-пользователь
#    → раздел "Договоры и акты" не должен отображаться

# 7. Открыть / (dashboard) как суперпользователь
#    → виджет с количеством неоплаченных актов и суммой долга

# 8. Открыть / как обычный пользователь
#    → виджет не должен отображаться
```
