# Сравнение моделей: Старая vs Упрощённая версия

## Статистика

| Метрика | models.py (старая) | models_simplified.py | Изменение |
|---------|-------------------|---------------------|-----------|
| **Моделей** | 14 | 6 | **-57%** ✅ |
| **Строк кода** | 707 | 678 | -4% |
| **Справочников** | 7 | 4 | -43% |
| **Основных моделей** | 2 | 2 | 0% |

---

## Удалённые модели (8 шт.)

### 1. ❌ TrainingProgramSection
**Было:** Отдельная модель для разделов программы
```python
class TrainingProgramSection(models.Model):
    program = models.ForeignKey(TrainingProgram)
    title = models.CharField(max_length=255)
    order = models.PositiveIntegerField()
```

**Стало:** Часть JSON в `TrainingProgram.content`
```json
{
  "sections": [
    {"title": "Раздел 1", "entries": [...]}
  ]
}
```

**Причина удаления:** Программы статичны, не нужна детализация в БД

---

### 2. ❌ TrainingProgramEntry
**Было:** Отдельная модель для тем программы
```python
class TrainingProgramEntry(models.Model):
    section = models.ForeignKey(TrainingProgramSection)
    entry_type = models.ForeignKey(TrainingEntryType)
    topic = models.TextField()
    hours = models.DecimalField()
```

**Стало:** Часть JSON в `TrainingProgram.content`
```json
{
  "sections": [
    {
      "entries": [
        {"type": "theory", "topic": "Тема 1", "hours": 4}
      ]
    }
  ]
}
```

**Причина удаления:** Избыточная детализация, JSON гибче

---

### 3. ❌ TrainingEntryType
**Было:** Справочник типов записей (теория, практика, консультация)
```python
class TrainingEntryType(models.Model):
    code = models.CharField(max_length=50)  # theory, practice
    name = models.CharField(max_length=255)
```

**Стало:** Choices в коде
```python
ENTRY_TYPES = [
    ('theory', 'Теоретическое обучение'),
    ('practice', 'Производственное обучение'),
    ('consultation', 'Консультация'),
]
```

**Причина удаления:** Всего 3 значения, не нужна отдельная таблица

---

### 4. ❌ TrainingScheduleRule
**Было:** Модель для правил расписания
```python
class TrainingScheduleRule(models.Model):
    name = models.CharField(max_length=255)
    pattern_days = models.JSONField()  # [1,3,1,3]
    use_workdays = models.BooleanField()
```

**Стало:** Удалено

**Причина удаления:** YAGNI - нет реализации, не используется

---

### 5. ❌ TrainingRoleType
**Было:** Справочник типов ролей
```python
class TrainingRoleType(models.Model):
    code = models.CharField(max_length=50)  # instructor, consultant
    name = models.CharField(max_length=255)
    is_required = models.BooleanField()
```

**Стало:** Прямые поля в `ProductionTraining`
```python
class ProductionTraining(models.Model):
    instructor = models.ForeignKey(Employee)
    theory_consultant = models.ForeignKey(Employee)
    commission_chairman = models.ForeignKey(Employee)
    commission_members = models.ManyToManyField(Employee)
```

**Причина удаления:** Всего 4 роли, проще сделать полями

---

### 6. ❌ TrainingRoleAssignment
**Было:** Связь многие-ко-многим между обучением и ролями
```python
class TrainingRoleAssignment(models.Model):
    training = models.ForeignKey(ProductionTraining)
    role_type = models.ForeignKey(TrainingRoleType)
    employee = models.ForeignKey(Employee)
    order = models.PositiveIntegerField()
```

**Стало:** Прямые поля (см. выше)

**Причина удаления:** Излишняя сложность для 4 ролей

---

### 7. ❌ TrainingDiaryEntry
**Было:** Записи дневника обучения
```python
class TrainingDiaryEntry(models.Model):
    training = models.ForeignKey(ProductionTraining)
    entry_date = models.DateField()
    entry_type = models.ForeignKey(TrainingEntryType)
    topic = models.TextField()
    hours = models.DecimalField()
    score = models.CharField(max_length=50)
```

**Стало:** Пока удалено (можно вернуть при необходимости)

**Причина удаления:**
- Дублирование программы
- Не критично для генерации документов
- Можно вернуть, если HR нужна детализация

---

### 8. ❌ TrainingTheoryConsultation
**Было:** Теоретические консультации
```python
class TrainingTheoryConsultation(models.Model):
    training = models.ForeignKey(ProductionTraining)
    date = models.DateField()
    hours = models.DecimalField()
    consultant = models.ForeignKey(Employee)
```

**Стало:** Удалено (или можно объединить с дневником)

**Причина удаления:** Можно заменить записью дневника с типом "consultation"

---

## Оставшиеся модели (6 шт.)

### ✅ 1. TrainingType
**Статус:** БЕЗ ИЗМЕНЕНИЙ
**Назначение:** Типы обучения (подготовка, переподготовка)
**Строк:** ~40

---

### ✅ 2. TrainingQualificationGrade
**Статус:** БЕЗ ИЗМЕНЕНИЙ
**Назначение:** Разряды квалификации (2, 3, 4, 5, 6)
**Строк:** ~45

---

### ✅ 3. TrainingProfession
**Статус:** УПРОЩЕНА
**Изменения:**
- ❌ Удалено: `assigned_name_ru`, `assigned_name_by`
- ❌ Удалено: `qualification_grade_default`

**Причина:** Эти поля не используются, разряд указывается в `ProductionTraining`
**Строк:** ~50 → ~40

---

### ✅ 4. EducationLevel
**Статус:** БЕЗ ИЗМЕНЕНИЙ
**Назначение:** Уровни образования (среднее, высшее и т.д.)
**Строк:** ~35

---

### ✅ 5. TrainingProgram
**Статус:** КАРДИНАЛЬНО УПРОЩЕНА ⭐
**Было:** Связь с Section → Entry → EntryType (3 модели)
**Стало:** JSON-поле `content`

**Добавлено:**
```python
content = models.JSONField(default=dict, blank=True)

def get_total_hours(self): ...
def get_sections(self): ...
def calculate_hours(self): ...
```

**Пример JSON:**
```json
{
  "sections": [
    {
      "title": "Раздел 1. Теоретическое обучение",
      "entries": [
        {"type": "theory", "topic": "Тема 1", "hours": 4},
        {"type": "theory", "topic": "Тема 2", "hours": 6}
      ]
    }
  ],
  "total_hours": 10,
  "theory_hours": 10,
  "practice_hours": 0
}
```

**Строк:** ~110 → ~140 (с методами работы с JSON)

---

### ✅ 6. ProductionTraining
**Статус:** УПРОЩЕНА И РАСШИРЕНА ⭐
**Изменения:**

**Удалено:**
- ❌ `schedule_rule` (YAGNI)
- ❌ Связь с `TrainingRoleAssignment`

**Добавлено:**
- ✅ `instructor` — инструктор (прямое поле)
- ✅ `theory_consultant` — консультант (прямое поле)
- ✅ `commission_chairman` — председатель (прямое поле)
- ✅ `commission_members` — члены комиссии (M2M)
- ✅ `workplace` — место работы (из Excel)
- ✅ `exam_date` — дата экзамена (отдельно)
- ✅ `practical_date` — дата практики (отдельно)
- ✅ `protocol_date` — дата протокола

**Методы для генерации документов:**
```python
def get_instructor_name(self): ...
def get_consultant_name(self): ...
def get_chairman_name(self): ...
def get_commission_members_list(self): ...
def get_exam_date_formatted(self, language='ru'): ...
def get_practical_date_formatted(self, language='ru'): ...
```

**Строк:** ~280 → ~380 (с новыми полями и методами)

---

## Преимущества упрощённой версии

### 1. ✅ Меньше JOIN'ов в запросах

**Было (старая версия):**
```python
# Получить все темы программы:
sections = program.sections.all()
for section in sections:
    entries = section.entries.all()  # JOIN 1
    for entry in entries:
        entry_type = entry.entry_type  # JOIN 2
```

**Стало (упрощённая):**
```python
# Получить все темы программы:
sections = program.get_sections()  # Из JSON, без JOIN
for section in sections:
    for entry in section['entries']:
        # Всё в памяти, без запросов к БД
```

### 2. ✅ Меньше миграций при изменениях

**Было:** Добавить новый тип записи в программу
1. Создать запись в TrainingEntryType
2. Миграция
3. Обновить админку

**Стало:** Просто использовать новый тип в JSON
```json
{"type": "exam", "topic": "Экзамен", "hours": 2}
```

### 3. ✅ Проще импорт из Excel

**Было:**
```python
# Для каждой темы:
section = TrainingProgramSection.objects.create(...)
entry = TrainingProgramEntry.objects.create(section=section, ...)
# 2 INSERT запроса на каждую тему
```

**Стало:**
```python
# Для всей программы:
program.content = json_from_excel
program.save()
# 1 INSERT для всей программы
```

### 4. ✅ Проще создание обучения

**Было:** Создать обучение + 4 TrainingRoleAssignment
```python
training = ProductionTraining.objects.create(...)
TrainingRoleAssignment.objects.create(training=training, role_type=instructor_role, employee=emp1)
TrainingRoleAssignment.objects.create(training=training, role_type=consultant_role, employee=emp2)
# ...
```

**Стало:** Всё в одной форме
```python
training = ProductionTraining.objects.create(
    instructor=emp1,
    theory_consultant=emp2,
    commission_chairman=emp3,
)
training.commission_members.add(emp4, emp5)
```

---

## Недостатки упрощённой версии

### ⚠️ 1. Удалён дневник обучения

**Проблема:** Если HR нужна детализация по дням/темам

**Решение:** Можно вернуть `TrainingDiaryEntry`, но упростить:
```python
class TrainingDiaryEntry(models.Model):
    training = models.ForeignKey(ProductionTraining)
    program_entry_index = models.PositiveIntegerField()  # Индекс темы в program.content
    entry_date = models.DateField()
    actual_hours = models.DecimalField()
    score = models.CharField(max_length=50)
```

### ⚠️ 2. JSON менее удобен для редактирования

**Проблема:** Редактировать JSON в админке неудобно

**Решение:**
- Использовать `django-jsoneditor` для красивого UI
- Или создать отдельную админку "Конструктор программ"

### ⚠️ 3. Нет истории изменений программ

**Проблема:** Если программа изменилась, старые обучения будут ссылаться на новую версию

**Решение:**
- Хранить snapshot программы в `ProductionTraining` при создании
- Или использовать `django-simple-history` для версионирования

---

## Миграционный путь

### Вариант 1: Постепенная миграция (рекомендуется)

1. **Фаза 1:** Добавить новые поля в существующие модели
   - `TrainingProgram.content` (JSONField)
   - `ProductionTraining.instructor`, `theory_consultant` и т.д.

2. **Фаза 2:** Миграция данных
   - Перенести Section+Entry → JSON
   - Перенести RoleAssignment → прямые поля

3. **Фаза 3:** Удалить старые модели
   - Удалить Section, Entry, EntryType, RoleAssignment и т.д.

4. **Фаза 4:** Обновить админку и views

### Вариант 2: Быстрая миграция

1. Создать новые модели с новыми названиями (TrainingProgram2, ProductionTraining2)
2. Мигрировать данные
3. Переключить код на новые модели
4. Удалить старые модели

---

## Рекомендации

### ✅ Делать:
1. Использовать упрощённую версию для новых проектов
2. Протестировать на копии БД перед применением
3. Создать скрипт миграции данных
4. Обновить документацию

### ❌ Не делать:
1. Удалять старые модели до переноса данных
2. Применять на production без тестирования
3. Игнорировать ошибки миграции

---

## Заключение

Упрощённая версия:
- ✅ **-57% моделей** (14 → 6)
- ✅ Проще поддержка и расширение
- ✅ Быстрее работа (меньше JOIN'ов)
- ✅ Гибче структура (JSON вместо таблиц)
- ⚠️ Нужна аккуратная миграция данных
- ⚠️ JSON менее удобен для редактирования

**Рекомендация:** Использовать упрощённую версию, но вернуть `TrainingDiaryEntry` при необходимости.
