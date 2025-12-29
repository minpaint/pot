# 📨 Логика выбора получателей email для рассылки журналов инструктажей

## Оглавление
1. [Общая концепция](#общая-концепция)
2. [Три источника получателей](#три-источника-получателей)
3. [Алгоритм сбора](#алгоритм-сбора)
4. [Приоритеты и правила](#приоритеты-и-правила)
5. [Примеры сценариев](#примеры-сценариев)
6. [Граничные случаи](#граничные-случаи)
7. [Блок-схема алгоритма](#блок-схема-алгоритма)
8. [Код реализации](#код-реализации)

---

## Общая концепция

### Задача
Для каждого структурного подразделения собрать список уникальных email-адресов, на которые будет отправлен образец журнала повторных инструктажей.

### Принцип
**Комбинированный подход** — объединение получателей из трёх независимых источников:
1. 📧 **Email подразделения** — специфичные адреса для конкретного подразделения
2. 👑 **Email ответственных за ОТ** — адреса сотрудников с должностью "Ответственный за охрану труда"
3. 🏢 **Email организации** — общие адреса из настроек EmailSettings

### Философия
- **Не исключаем, а дополняем** — все источники работают параллельно
- **Без дубликатов** — автоматическое удаление повторяющихся адресов
- **Fail-safe** — если один источник не работает, используются остальные
- **Гибкость** — можно настроить только нужные источники

---

## Три источника получателей

### Источник 1️⃣: Email подразделения (SubdivisionEmail)

**Что это:**
Специальные email-адреса, привязанные к конкретному структурному подразделению через inline-модель.

**Модель:**
```python
class SubdivisionEmail(models.Model):
    subdivision = ForeignKey(StructuralSubdivision)
    email = EmailField()
    description = CharField()  # "Главный инженер", "Служба ОТ"
    is_active = BooleanField(default=True)
```

**Когда используется:**
- Есть конкретное подразделение (subdivision != None)
- В подразделении настроены email (SubdivisionEmail.objects.filter(...).exists())
- Email активен (is_active=True)

**Примеры адресов:**
```
engineer@biomilk.com        (Главный инженер цеха)
workshop.safety@biomilk.com (Служба ОТ цеха)
foreman@biomilk.com         (Старший мастер)
```

**Настройка:**
Админка → Структурные подразделения → Выбрать подразделение → Секция "Email для уведомлений"

**Преимущества:**
- ✅ Точная адресация (конкретно для подразделения)
- ✅ Можно указать несколько адресов
- ✅ Есть описание роли получателя
- ✅ Можно временно отключить (is_active=False)

---

### Источник 2️⃣: Email ответственных за ОТ (Employee.email)

**Что это:**
Email-адреса сотрудников, у которых в должности установлен флаг `is_responsible_for_safety=True`.

**Связанные модели:**
```python
# Employee
class Employee:
    email = EmailField(blank=True)
    subdivision = ForeignKey(StructuralSubdivision)
    position = ForeignKey(Position)
    status = CharField()  # 'active', 'fired', ...

# Position
class Position:
    is_responsible_for_safety = BooleanField(default=False)
```

**Условия включения:**
```python
Employee.objects.filter(
    subdivision=subdivision,              # Сотрудник из этого подразделения
    status='active',                      # Активный сотрудник
    position__is_responsible_for_safety=True,  # Ответственный за ОТ
    email__isnull=False                   # Email не пустой
).exclude(email='')
```

**Примеры:**
```
ivanov.ii@biomilk.com   (Иванов И.И., Инженер по ОТ)
petrova.as@biomilk.com  (Петрова А.С., Специалист по ОТ)
```

**Настройка:**
1. В должности установить галочку "Ответственный за ОТ"
2. У сотрудника заполнить поле Email

**Преимущества:**
- ✅ Автоматическое обнаружение ответственных
- ✅ Привязка к конкретному подразделению
- ✅ Не нужно дублировать адреса вручную

**Логика:**
Ответственный за ОТ **сам проводит инструктажи**, поэтому ему нужен образец журнала.

---

### Источник 3️⃣: Email организации (EmailSettings)

**Что это:**
Общие email-адреса на уровне всей организации, настроенные в EmailSettings.

**Модель:**
```python
class EmailSettings(models.Model):
    organization = OneToOneField(Organization)
    recipient_emails = TextField()  # Многострочное поле
    is_active = BooleanField(default=True)
    # ... SMTP настройки ...
```

**Формат `recipient_emails`:**
```
hr@biomilk.com
director@biomilk.com
safety.department@biomilk.com
```
(По одному адресу на строку)

**Метод извлечения:**
```python
def get_recipient_list(self):
    """Парсит текстовое поле в список"""
    emails = [
        email.strip()
        for email in self.recipient_emails.strip().split('\n')
        if email.strip()
    ]
    return emails
```

**Когда используется:**
- EmailSettings существует для организации
- EmailSettings активен (is_active=True)
- Поле recipient_emails не пустое

**Примеры адресов:**
```
hr@biomilk.com              (Отдел кадров)
director@biomilk.com        (Директор)
safety.dept@biomilk.com     (Служба охраны труда)
admin@biomilk.com           (Администратор)
```

**Настройка:**
Админка → Deadline Control → Email Settings (SMTP) → Поле "Email получателей"

**Преимущества:**
- ✅ Единое место настройки для всей организации
- ✅ Всегда информируются ключевые лица (HR, директор)
- ✅ Fallback на случай отсутствия других источников

---

## Алгоритм сбора

### Псевдокод

```
ФУНКЦИЯ collect_recipients_for_subdivision(subdivision, organization):
    recipients = ПУСТОЕ_МНОЖЕСТВО  // Set для автоудаления дубликатов

    // ШАГ 1: Email подразделения
    ЕСЛИ subdivision НЕ ПУСТО:
        subdivision_emails = SubdivisionEmail.query(
            subdivision=subdivision,
            is_active=True
        ).values(email)

        recipients.ДОБАВИТЬ_ВСЕ(subdivision_emails)

    // ШАГ 2: Email ответственных за ОТ
    ЕСЛИ subdivision НЕ ПУСТО:
        responsible_emails = Employee.query(
            subdivision=subdivision,
            status='active',
            position.is_responsible_for_safety=True,
            email НЕ ПУСТО
        ).values(email)

        recipients.ДОБАВИТЬ_ВСЕ(responsible_emails)

    // ШАГ 3: Email организации
    ПОПЫТКА:
        email_settings = organization.email_settings

        ЕСЛИ email_settings.is_active:
            org_emails = email_settings.get_recipient_list()
            recipients.ДОБАВИТЬ_ВСЕ(org_emails)
    ОБРАБОТКА_ОШИБКИ:
        ЛОГИРОВАТЬ("EmailSettings не найдены для {organization}")

    // Преобразуем множество в список
    ВЕРНУТЬ список(recipients)
```

### Python-реализация

```python
def collect_recipients_for_subdivision(subdivision, organization):
    """
    Собирает всех получателей для подразделения.

    Args:
        subdivision (StructuralSubdivision|None): Подразделение
        organization (Organization): Организация

    Returns:
        list[str]: Список уникальных email-адресов
    """
    from directory.models import Employee
    import logging

    logger = logging.getLogger(__name__)
    recipients = set()  # Set для автоматического удаления дубликатов

    # ИСТОЧНИК 1: Email подразделения
    if subdivision:
        subdivision_emails = subdivision.notification_emails.filter(
            is_active=True
        ).values_list('email', flat=True)

        recipients.update(subdivision_emails)
        logger.info(
            f"[Источник 1] Подразделение '{subdivision.name}': "
            f"найдено {len(subdivision_emails)} email"
        )

    # ИСТОЧНИК 2: Email ответственных за ОТ
    if subdivision:
        responsible_employees = Employee.objects.filter(
            subdivision=subdivision,
            status='active',
            position__is_responsible_for_safety=True,
            email__isnull=False
        ).exclude(email='').values_list('email', flat=True)

        recipients.update(responsible_employees)
        logger.info(
            f"[Источник 2] Ответственные за ОТ в '{subdivision.name}': "
            f"найдено {len(responsible_employees)} email"
        )

    # ИСТОЧНИК 3: Email организации
    try:
        email_settings = organization.email_settings

        if email_settings.is_active:
            org_emails = email_settings.get_recipient_list()
            recipients.update(org_emails)
            logger.info(
                f"[Источник 3] Организация '{organization.short_name_ru}': "
                f"найдено {len(org_emails)} email"
            )
        else:
            logger.warning(
                f"EmailSettings для '{organization.short_name_ru}' отключены"
            )
    except Exception as e:
        logger.warning(
            f"EmailSettings не найдены для '{organization.short_name_ru}': {e}"
        )

    # Итоговая статистика
    logger.info(
        f"ИТОГО для '{subdivision.name if subdivision else 'без подразделения'}': "
        f"{len(recipients)} уникальных получателей"
    )

    return list(recipients)
```

---

## Приоритеты и правила

### Нет приоритетов — только объединение

**Важно:** Источники **НЕ имеют приоритетов**. Все три работают параллельно и их результаты объединяются.

```
┌─────────────────┐
│  Источник 1     │ ──┐
│  [A, B]         │   │
└─────────────────┘   │
                      ├──► ОБЪЕДИНЕНИЕ ──► [A, B, C, D]
┌─────────────────┐   │    (уникальные)
│  Источник 2     │ ──┤
│  [B, C]         │   │
└─────────────────┘   │
                      │
┌─────────────────┐   │
│  Источник 3     │ ──┘
│  [C, D]         │
└─────────────────┘
```

### Автоматическое удаление дубликатов

**Проблема:** Email может встречаться в нескольких источниках.

**Пример:**
```
Источник 1 (SubdivisionEmail): engineer@biomilk.com
Источник 2 (Employee):         engineer@biomilk.com  ← тот же адрес
Источник 3 (EmailSettings):    hr@biomilk.com
```

**Решение:** Использование `set()` в Python автоматически убирает дубликаты.

```python
recipients = set()  # Множество (set)
recipients.update(['a@test.com', 'b@test.com'])
recipients.update(['b@test.com', 'c@test.com'])  # 'b@test.com' дублируется
print(list(recipients))  # ['a@test.com', 'b@test.com', 'c@test.com']
```

### Правила включения/исключения

| Условие | Включается? | Причина |
|---------|-------------|---------|
| Email пустой (`''`) | ❌ Нет | Некуда отправлять |
| Email = NULL | ❌ Нет | Не заполнен |
| SubdivisionEmail.is_active = False | ❌ Нет | Временно отключен |
| Employee.status = 'fired' | ❌ Нет | Уволенный сотрудник |
| EmailSettings.is_active = False | ❌ Нет | Отключены настройки |
| Email невалидный | ⚠️ Зависит | Django EmailField валидирует |

### Fallback-стратегия

**Сценарий:** Что если источники пустые?

```
Источник 1 (SubdivisionEmail):  []  ← Нет email
Источник 2 (Employee):          []  ← Нет ответственных
Источник 3 (EmailSettings):     [hr@biomilk.com]  ← Есть!

ИТОГО: [hr@biomilk.com]  ✅ Хотя бы один получатель есть
```

**Критическая ситуация:** Все источники пустые
```python
if not recipients:
    logger.warning(f"Нет получателей для {subdivision_name}")
    # Рассылка НЕ отправляется
    return None
```

---

## Примеры сценариев

### Сценарий 1: Полная настройка (все 3 источника)

**Исходные данные:**

**Подразделение:** Производственный цех

**Источник 1 (SubdivisionEmail):**
```sql
subdivision_id | email                   | description        | is_active
1              | engineer@biomilk.com    | Главный инженер    | TRUE
1              | foreman@biomilk.com     | Старший мастер     | TRUE
```

**Источник 2 (Employee):**
```sql
id  | full_name      | email              | position_id | subdivision_id | status
101 | Иванов И.И.    | ivanov@biomilk.com | 5 (ОТ)      | 1              | active
```

**Источник 3 (EmailSettings):**
```
hr@biomilk.com
director@biomilk.com
```

**Выполнение:**
```python
collect_recipients_for_subdivision(
    subdivision=StructuralSubdivision(id=1, name="Производственный цех"),
    organization=Organization(id=1, short_name_ru="ООО БиоМилк")
)
```

**Результат:**
```python
[
    'engineer@biomilk.com',     # Источник 1
    'foreman@biomilk.com',      # Источник 1
    'ivanov@biomilk.com',       # Источник 2
    'hr@biomilk.com',           # Источник 3
    'director@biomilk.com'      # Источник 3
]
# Итого: 5 уникальных получателей
```

**Логи:**
```
[INFO] [Источник 1] Подразделение 'Производственный цех': найдено 2 email
[INFO] [Источник 2] Ответственные за ОТ в 'Производственный цех': найдено 1 email
[INFO] [Источник 3] Организация 'ООО БиоМилк': найдено 2 email
[INFO] ИТОГО для 'Производственный цех': 5 уникальных получателей
```

---

### Сценарий 2: Только email организации

**Исходные данные:**

**Подразделение:** Административный корпус

**Источник 1:** Пусто (нет SubdivisionEmail)

**Источник 2:** Пусто (нет ответственных за ОТ с email)

**Источник 3 (EmailSettings):**
```
admin@biomilk.com
hr@biomilk.com
```

**Результат:**
```python
[
    'admin@biomilk.com',  # Источник 3
    'hr@biomilk.com'      # Источник 3
]
# Итого: 2 получателя (только из EmailSettings)
```

**Логи:**
```
[INFO] [Источник 1] Подразделение 'Административный корпус': найдено 0 email
[INFO] [Источник 2] Ответственные за ОТ в 'Административный корпус': найдено 0 email
[INFO] [Источник 3] Организация 'ООО БиоМилк': найдено 2 email
[INFO] ИТОГО для 'Административный корпус': 2 уникальных получателей
```

---

### Сценарий 3: С дубликатами

**Исходные данные:**

**Подразделение:** Складское хозяйство

**Источник 1:**
```
safety@biomilk.com      (Служба ОТ)
```

**Источник 2:**
```
safety@biomilk.com      (Петров П.П., Инженер по ОТ) ← ДУБЛИКАТ
```

**Источник 3:**
```
hr@biomilk.com
safety@biomilk.com      ← ДУБЛИКАТ
```

**Результат (без дубликатов):**
```python
[
    'safety@biomilk.com',  # Встречался 3 раза, оставлен 1 раз
    'hr@biomilk.com'
]
# Итого: 2 уникальных получателя (дубликаты удалены)
```

**Процесс удаления дубликатов:**
```
Шаг 1: recipients = {}
Шаг 2: recipients.update(['safety@biomilk.com'])          → {'safety@biomilk.com'}
Шаг 3: recipients.update(['safety@biomilk.com'])          → {'safety@biomilk.com'}  (дубликат игнорируется)
Шаг 4: recipients.update(['hr@biomilk.com', 'safety@...']) → {'safety@biomilk.com', 'hr@biomilk.com'}
```

---

### Сценарий 4: Нет получателей (критическая ситуация)

**Исходные данные:**

**Подразделение:** Новый цех (только что создан)

**Источник 1:** Пусто
**Источник 2:** Пусто
**Источник 3:** EmailSettings НЕ настроен (не существует)

**Результат:**
```python
[]  # Пустой список
```

**Логи:**
```
[INFO] [Источник 1] Подразделение 'Новый цех': найдено 0 email
[INFO] [Источник 2] Ответственные за ОТ в 'Новый цех': найдено 0 email
[WARNING] EmailSettings не найдены для 'ООО БиоМилк': Organization has no email_settings.
[WARNING] Нет получателей для Новый цех
```

**Поведение системы:**
```python
recipients = collect_recipients_for_subdivision(subdivision, organization)

if not recipients:
    logger.warning(f"Нет получателей для {subdivision.name}")
    messages.warning(request, f"Не удалось отправить письмо для '{subdivision.name}': нет получателей")
    # Пропускаем отправку для этого подразделения
    continue
```

---

### Сценарий 5: Сотрудники без подразделения

**Исходные данные:**

**Подразделение:** `None` (сотрудники привязаны только к организации)

**Источник 1:** ❌ Не работает (нет subdivision)
**Источник 2:** ❌ Не работает (нет subdivision для фильтра)
**Источник 3:** ✅ Работает

**Результат:**
```python
[
    'hr@biomilk.com',       # Источник 3
    'director@biomilk.com'  # Источник 3
]
# Только email организации
```

**Логика в коде:**
```python
# Источники 1 и 2 проверяют: if subdivision:
if subdivision:
    # Собираем email подразделения
    # Собираем email ответственных
# else: пропускаем

# Источник 3 работает всегда (не зависит от subdivision)
```

---

## Граничные случаи

### Случай 1: Отключенные email

**Ситуация:**
```sql
SubdivisionEmail:
  email: old.engineer@biomilk.com, is_active=FALSE  ← отключен
  email: new.engineer@biomilk.com, is_active=TRUE   ← активен
```

**Результат:**
```python
['new.engineer@biomilk.com']  # Только активный
```

**Фильтр в коде:**
```python
subdivision.notification_emails.filter(is_active=True)
```

---

### Случай 2: Уволенный ответственный за ОТ

**Ситуация:**
```sql
Employee:
  id: 101, email: fired.ot@biomilk.com, status='fired', position.is_responsible=True
  id: 102, email: new.ot@biomilk.com, status='active', position.is_responsible=True
```

**Результат:**
```python
['new.ot@biomilk.com']  # Только активный
```

**Фильтр в коде:**
```python
Employee.objects.filter(
    status='active',  # Только активные
    position__is_responsible_for_safety=True
)
```

---

### Случай 3: Невалидный email

**Ситуация:**
```sql
SubdivisionEmail:
  email: 'invalid-email'  ← невалидный формат
```

**Поведение:**
- Django `EmailField` валидирует при сохранении в админке
- Невалидный email **не может быть сохранён** в БД
- Если как-то попал (миграция, прямой SQL) — будет проигнорирован при отправке SMTP

**Безопасность:**
```python
# В модели:
email = models.EmailField()  # Автоматическая валидация

# При отправке:
try:
    email.send(fail_silently=False)
except SMTPException as e:
    logger.error(f"Невалидный email: {e}")
```

---

### Случай 4: Пустое поле recipient_emails

**Ситуация:**
```python
EmailSettings:
  recipient_emails = ""  # Пустая строка
```

**Результат:**
```python
email_settings.get_recipient_list()  # Вернёт []
```

**Реализация get_recipient_list():**
```python
def get_recipient_list(self):
    if not self.recipient_emails:
        return []

    emails = [
        email.strip()
        for email in self.recipient_emails.strip().split('\n')
        if email.strip()  # Пропускаем пустые строки
    ]
    return emails
```

---

### Случай 5: Множественные организации

**Ситуация:** Пользователь имеет доступ к нескольким организациям.

**Вопрос:** Какие email используются?

**Ответ:** Email из EmailSettings **конкретной организации**, к которой относится подразделение.

```python
# Подразделение всегда привязано к организации
subdivision.organization  # Organization(id=1, name="ООО БиоМилк")

# Берём EmailSettings именно этой организации
email_settings = subdivision.organization.email_settings
```

**НЕ смешиваются** email из разных организаций.

---

## Блок-схема алгоритма

```
                        НАЧАЛО
                           │
                           ▼
            ┌──────────────────────────────┐
            │ Входные параметры:           │
            │ - subdivision                │
            │ - organization               │
            └──────────────┬───────────────┘
                           │
                           ▼
            ┌──────────────────────────────┐
            │ recipients = set()           │
            │ (пустое множество)           │
            └──────────────┬───────────────┘
                           │
        ┌──────────────────┼──────────────────┐
        │                  │                  │
        ▼                  ▼                  ▼
   ┌────────┐        ┌────────┐        ┌────────┐
   │ИСТОЧНИК│        │ИСТОЧНИК│        │ИСТОЧНИК│
   │   1    │        │   2    │        │   3    │
   └────┬───┘        └────┬───┘        └────┬───┘
        │                 │                 │
        ▼                 ▼                 ▼
   ┌─────────────┐  ┌──────────────┐  ┌──────────────┐
   │subdivision  │  │Employee.query│  │EmailSettings │
   │  != None?   │  │subdivision   │  │.get_recipient│
   └─────┬───────┘  │  + active    │  │_list()       │
         │ Да       │  + is_resp   │  └──────┬───────┘
         ▼          └──────┬───────┘         │
   ┌─────────────┐         │                 │
   │SubdivisionE-│         │                 │
   │mail.filter( │         │                 │
   │active=True) │         │                 │
   └─────┬───────┘         │                 │
         │                 │                 │
         ▼                 ▼                 ▼
   ┌─────────────────────────────────────────┐
   │   recipients.update(emails)             │
   │   (добавление в множество)              │
   └─────────────┬───────────────────────────┘
                 │
                 ▼
          ┌──────────────┐
          │ recipients   │ Нет
          │ пустое?      ├─────────┐
          └──────┬───────┘         │
                 │ Да               │
                 ▼                  ▼
          ┌──────────────┐   ┌─────────────┐
          │ Логировать   │   │ Вернуть     │
          │ WARNING      │   │ list(recip) │
          └──────┬───────┘   └─────────────┘
                 │                  │
                 ▼                  │
          ┌──────────────┐         │
          │ Вернуть []   │         │
          └──────────────┘         │
                 │                  │
                 └──────────────────┘
                           │
                           ▼
                        КОНЕЦ
```

---

## Код реализации

### Полная реализация функции

**Файл:** `directory/utils/email_recipients.py`

```python
"""
Утилиты для сбора получателей email-рассылок
"""
import logging
from typing import List, Optional
from directory.models import Employee, StructuralSubdivision, Organization

logger = logging.getLogger(__name__)


def collect_recipients_for_subdivision(
    subdivision: Optional[StructuralSubdivision],
    organization: Organization
) -> List[str]:
    """
    Собирает всех получателей email для подразделения из трёх источников:
    1. SubdivisionEmail (email подразделения)
    2. Employee.email (ответственные за ОТ)
    3. EmailSettings.recipient_emails (общие email организации)

    Args:
        subdivision: Структурное подразделение (может быть None)
        organization: Организация

    Returns:
        Список уникальных email-адресов (без дубликатов)

    Examples:
        >>> collect_recipients_for_subdivision(
        ...     subdivision=StructuralSubdivision.objects.get(name="Производственный цех"),
        ...     organization=Organization.objects.get(short_name_ru="ООО БиоМилк")
        ... )
        ['engineer@biomilk.com', 'ivanov@biomilk.com', 'hr@biomilk.com']
    """
    recipients = set()  # Используем set для автоматического удаления дубликатов
    subdivision_name = subdivision.name if subdivision else "без подразделения"

    # ==========================================
    # ИСТОЧНИК 1: Email подразделения
    # ==========================================
    if subdivision:
        try:
            subdivision_emails = subdivision.notification_emails.filter(
                is_active=True
            ).values_list('email', flat=True)

            count = len(subdivision_emails)
            if count > 0:
                recipients.update(subdivision_emails)
                logger.info(
                    f"[Источник 1: SubdivisionEmail] Подразделение '{subdivision.name}': "
                    f"найдено {count} активных email"
                )
            else:
                logger.debug(
                    f"[Источник 1: SubdivisionEmail] Подразделение '{subdivision.name}': "
                    f"email не настроены"
                )
        except Exception as e:
            logger.warning(
                f"[Источник 1: SubdivisionEmail] Ошибка получения email для '{subdivision.name}': {e}"
            )

    # ==========================================
    # ИСТОЧНИК 2: Email ответственных за ОТ
    # ==========================================
    if subdivision:
        try:
            responsible_employees = Employee.objects.filter(
                subdivision=subdivision,
                status='active',
                position__is_responsible_for_safety=True,
                email__isnull=False
            ).exclude(
                email=''
            ).values_list('email', flat=True)

            count = len(responsible_employees)
            if count > 0:
                recipients.update(responsible_employees)
                logger.info(
                    f"[Источник 2: Employee] Ответственные за ОТ в '{subdivision.name}': "
                    f"найдено {count} email"
                )
            else:
                logger.debug(
                    f"[Источник 2: Employee] Ответственные за ОТ в '{subdivision.name}': "
                    f"не найдены или email не заполнены"
                )
        except Exception as e:
            logger.warning(
                f"[Источник 2: Employee] Ошибка получения ответственных за ОТ для '{subdivision.name}': {e}"
            )

    # ==========================================
    # ИСТОЧНИК 3: Email организации
    # ==========================================
    try:
        email_settings = organization.email_settings

        if email_settings.is_active:
            org_emails = email_settings.get_recipient_list()
            count = len(org_emails)

            if count > 0:
                recipients.update(org_emails)
                logger.info(
                    f"[Источник 3: EmailSettings] Организация '{organization.short_name_ru}': "
                    f"найдено {count} email"
                )
            else:
                logger.debug(
                    f"[Источник 3: EmailSettings] Организация '{organization.short_name_ru}': "
                    f"email не настроены"
                )
        else:
            logger.warning(
                f"[Источник 3: EmailSettings] EmailSettings для '{organization.short_name_ru}' отключены (is_active=False)"
            )

    except organization._meta.model.email_settings.RelatedObjectDoesNotExist:
        logger.warning(
            f"[Источник 3: EmailSettings] EmailSettings не существует для организации '{organization.short_name_ru}'"
        )
    except Exception as e:
        logger.error(
            f"[Источник 3: EmailSettings] Неожиданная ошибка при получении настроек для '{organization.short_name_ru}': {e}"
        )

    # ==========================================
    # ИТОГОВАЯ СТАТИСТИКА
    # ==========================================
    total_count = len(recipients)

    if total_count > 0:
        logger.info(
            f"✅ ИТОГО для '{subdivision_name}': {total_count} уникальных получателей"
        )
    else:
        logger.warning(
            f"⚠️ ВНИМАНИЕ: Для '{subdivision_name}' не найдено ни одного получателя! "
            f"Проверьте настройки SubdivisionEmail, ответственных за ОТ или EmailSettings."
        )

    return list(recipients)


def validate_email_list(emails: List[str]) -> List[str]:
    """
    Валидирует список email-адресов.

    Args:
        emails: Список email-адресов

    Returns:
        Список валидных email-адресов

    Raises:
        ValidationError: Если есть невалидные email
    """
    from django.core.validators import validate_email
    from django.core.exceptions import ValidationError

    valid_emails = []
    invalid_emails = []

    for email in emails:
        try:
            validate_email(email)
            valid_emails.append(email)
        except ValidationError:
            invalid_emails.append(email)
            logger.warning(f"Невалидный email: {email}")

    if invalid_emails:
        raise ValidationError(f"Невалидные email-адреса: {', '.join(invalid_emails)}")

    return valid_emails
```

### Тесты

**Файл:** `directory/tests/test_email_recipients.py`

```python
from django.test import TestCase
from directory.models import Organization, StructuralSubdivision, Employee, Position, SubdivisionEmail
from deadline_control.models import EmailSettings
from directory.utils.email_recipients import collect_recipients_for_subdivision


class EmailRecipientsTestCase(TestCase):
    """Тесты для логики сбора получателей email"""

    def setUp(self):
        """Создание тестовых данных"""
        # Организация
        self.org = Organization.objects.create(
            short_name_ru="ООО Тест",
            full_name_ru="Общество с ограниченной ответственностью Тест"
        )

        # Подразделение
        self.subdivision = StructuralSubdivision.objects.create(
            name="Тестовый цех",
            organization=self.org
        )

        # EmailSettings
        self.email_settings = EmailSettings.objects.create(
            organization=self.org,
            is_active=True,
            recipient_emails="hr@test.com\ndirector@test.com"
        )

        # Должность (ответственный за ОТ)
        self.position_ot = Position.objects.create(
            position_name="Инженер по ОТ",
            organization=self.org,
            is_responsible_for_safety=True
        )

    def test_all_three_sources(self):
        """Тест: все три источника возвращают email"""
        # Источник 1
        SubdivisionEmail.objects.create(
            subdivision=self.subdivision,
            email="engineer@test.com",
            is_active=True
        )

        # Источник 2
        Employee.objects.create(
            full_name_nominative="Иванов Иван Иванович",
            organization=self.org,
            subdivision=self.subdivision,
            position=self.position_ot,
            status='active',
            email="ivanov@test.com"
        )

        # Источник 3 (уже создан в setUp)

        # Сбор получателей
        recipients = collect_recipients_for_subdivision(self.subdivision, self.org)

        # Проверки
        self.assertEqual(len(recipients), 4)  # 1 + 1 + 2
        self.assertIn('engineer@test.com', recipients)  # Источник 1
        self.assertIn('ivanov@test.com', recipients)    # Источник 2
        self.assertIn('hr@test.com', recipients)        # Источник 3
        self.assertIn('director@test.com', recipients)  # Источник 3

    def test_duplicates_removed(self):
        """Тест: дубликаты автоматически удаляются"""
        # Один и тот же email в двух источниках
        SubdivisionEmail.objects.create(
            subdivision=self.subdivision,
            email="same@test.com",
            is_active=True
        )

        Employee.objects.create(
            full_name_nominative="Петров Петр Петрович",
            organization=self.org,
            subdivision=self.subdivision,
            position=self.position_ot,
            status='active',
            email="same@test.com"  # Дубликат
        )

        recipients = collect_recipients_for_subdivision(self.subdivision, self.org)

        # Проверка: дубликат удалён
        self.assertEqual(recipients.count('same@test.com'), 1)

    def test_no_recipients(self):
        """Тест: нет получателей (пустой результат)"""
        # Удаляем EmailSettings
        self.email_settings.delete()

        # Нет SubdivisionEmail, нет ответственных

        recipients = collect_recipients_for_subdivision(self.subdivision, self.org)

        # Проверка: пустой список
        self.assertEqual(len(recipients), 0)

    def test_inactive_excluded(self):
        """Тест: неактивные email исключаются"""
        SubdivisionEmail.objects.create(
            subdivision=self.subdivision,
            email="inactive@test.com",
            is_active=False  # Неактивен
        )

        recipients = collect_recipients_for_subdivision(self.subdivision, self.org)

        # Проверка: неактивный email не включён
        self.assertNotIn('inactive@test.com', recipients)
```

---

## Заключение

### Ключевые принципы логики

1. **Три независимых источника** — работают параллельно
2. **Объединение без приоритетов** — все результаты суммируются
3. **Автоматическое удаление дубликатов** — через Python `set()`
4. **Fail-safe подход** — если один источник не работает, используются остальные
5. **Детальное логирование** — каждый источник логирует свои результаты

### Преимущества подхода

- ✅ **Гибкость** — можно настроить только нужные источники
- ✅ **Надёжность** — fallback на другие источники при сбое
- ✅ **Прозрачность** — детальные логи позволяют отследить откуда взялись email
- ✅ **Масштабируемость** — легко добавить 4-й, 5-й источник
- ✅ **Простота настройки** — понятные места для управления email

### Рекомендации по использованию

**Минимальная настройка:**
- Заполните EmailSettings для организации → будет работать для всех подразделений

**Оптимальная настройка:**
- EmailSettings (общие адреса)
- + SubdivisionEmail (специфичные адреса подразделений)
- + Employee.email для ответственных за ОТ

**Полная настройка:**
- Все три источника → максимальное покрытие

---

**Дата создания:** 02.12.2025
**Версия документа:** 1.0
**Автор:** Claude Code (Anthropic)
