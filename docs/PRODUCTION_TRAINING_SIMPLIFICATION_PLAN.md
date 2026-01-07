# План упрощения модуля "Обучение на производстве"

## Цели упрощения

**Исходная ситуация:**
- 14 моделей
- 1573 строки кода
- Сложная структура программ обучения
- Нет генерации документов

**Целевая ситуация:**
- 6-7 моделей (~50% меньше)
- ~800-900 строк кода
- Простая структура
- **Работающая генерация всех документов** (главная задача!)

**Принципы:**
1. ✅ **Программы статичны** → хранить как JSON/файлы, не как модели
2. ✅ **Генерация документов - приоритет №1**
3. ✅ **HR заполняет всё** → упростить валидацию
4. ✅ **Языки не расширяются** → оставить `_ru`/`_by`

---

## Этап 1: Анализ документов и полей

### 1.1. Изучить макет.docx

**Задача:** Определить все VML-поля (WordArt) в шаблоне

```bash
cd /home/django/webapps/potby
unzip -l media/document_templates/learning/макет.docx | grep "word/"
```

**Создать скрипт для извлечения VML-полей:**

```python
# utility_scripts/extract_vml_fields.py
import zipfile
import xml.etree.ElementTree as ET

VML_NS = {
    'w': 'http://schemas.openxmlformats.org/wordprocessingml/2006/main',
    'v': 'urn:schemas-microsoft-com:vml',
}

def extract_vml_fields(docx_path):
    """Извлекает список VML-полей из DOCX."""
    fields = []
    with zipfile.ZipFile(docx_path, 'r') as z:
        for part in ['word/document.xml', 'word/header1.xml', 'word/footer1.xml']:
            try:
                xml = z.read(part)
                root = ET.fromstring(xml)
                for shape in root.findall('.//v:shape', VML_NS):
                    shape_id = shape.attrib.get('id') or shape.attrib.get('alt')
                    if shape_id:
                        fields.append(shape_id)
            except:
                pass
    return fields

if __name__ == '__main__':
    fields = extract_vml_fields('media/document_templates/learning/макет.docx')
    print("VML поля в макет.docx:")
    for f in sorted(set(fields)):
        print(f"  - {f}")
```

**Результат:** Список полей типа `field1`, `field2`, ..., которые нужно заполнять

### 1.2. Сопоставить поля Excel с VML

Из VBA-кода (`Module2.bas`):
```vba
For j = 11 To 21 ' Колонки K-U
    shpName = CStr(xlSheet.Cells(6, j).value)  ' Имя поля из строки 6
    data = CStr(xlSheet.Cells(i, j).Text)      ' Данные из строки i
```

**Создать маппинг полей:**

```python
# production_training/document_templates/field_mapping.py

# Маппинг из Excel (колонка K-U, строка 6) в VML-поля макет.docx
EXCEL_TO_VML_MAPPING = {
    # Из анализа Excel файла:
    'K': 'field1',  # Например: ФИО сотрудника
    'L': 'field2',  # Профессия
    'M': 'field3',  # Разряд
    'N': 'field4',  # Образование
    'O': 'field5',  # Дата начала
    'P': 'field6',  # Дата окончания
    'Q': 'field7',  # Инструктор
    'R': 'field8',  # Оценка за экзамен
    'S': 'field9',  # Дата экзамена (русский)
    'T': 'field10', # Оценка за практику
    'U': 'field11', # Дата практики (русский)
}

# Какие данные из модели соответствуют полям
MODEL_TO_VML_MAPPING = {
    'field1': lambda training: training.employee.full_name_nominative,
    'field2': lambda training: training.profession.name_ru_nominative,
    'field3': lambda training: training.qualification_grade.label_ru if training.qualification_grade else '',
    'field4': lambda training: training.education_level.name_ru if training.education_level else '',
    'field5': lambda training: training.start_date.strftime('%d.%m.%Y') if training.start_date else '',
    'field6': lambda training: training.end_date.strftime('%d.%m.%Y') if training.end_date else '',
    'field7': lambda training: training.get_instructor_name(),
    'field8': lambda training: training.exam_score or '',
    'field9': lambda training: training.get_exam_date_ru(),
    'field10': lambda training: training.practical_score or '',
    'field11': lambda training: training.get_practical_date_ru(),
}
```

### 1.3. Определить список документов

**8 документов для генерации:**

1. **Заявление** (`application.docx`)
2. **Приказ на обучение** (`order.docx`)
3. **Карточка теории** (`theory_card.docx`)
4. **Дневник подготовки** (`diary_preparation.docx`)
5. **Дневник переподготовки** (`diary_retraining.docx`)
6. **Заявление на пробную работу** (`practical_application.docx`)
7. **Заключение на пробную работу** (`practical_conclusion.docx`)
8. **Протокол комиссии** (`protocol.docx`)

**Создать шаблоны:**
```
media/document_templates/learning/
  ├── макет.docx                    # Основной шаблон (уже есть)
  ├── application.docx              # Заявление
  ├── order.docx                    # Приказ
  ├── theory_card.docx              # Карточка теории
  ├── diary_preparation.docx        # Дневник подготовки
  ├── diary_retraining.docx         # Дневник переподготовки
  ├── practical_application.docx    # Заявление на пробную работу
  ├── practical_conclusion.docx     # Заключение
  └── protocol.docx                 # Протокол
```

---

## Этап 2: Упрощение моделей

### 2.1. Какие модели УДАЛИТЬ

**8 моделей на удаление:**

1. ❌ `TrainingProgramSection` — разделы программы
2. ❌ `TrainingProgramEntry` — пункты программы
3. ❌ `TrainingEntryType` — типы записей (теория/практика)
4. ❌ `TrainingScheduleRule` — правила расписания (YAGNI)
5. ❌ `TrainingDiaryEntry` — записи дневника (переделать)
6. ❌ `TrainingTheoryConsultation` — консультации (объединить с ролями)
7. ❌ `TrainingRoleAssignment` — роли (упростить)
8. ❌ `TrainingRoleType` — типы ролей (перевести в choices)

### 2.2. Какие модели ОСТАВИТЬ/ИЗМЕНИТЬ

**6 моделей остаются:**

#### 1. TrainingType (БЕЗ ИЗМЕНЕНИЙ)
```python
class TrainingType(models.Model):
    code = models.CharField(max_length=50, unique=True)
    name_ru = models.CharField(max_length=255)
    name_by = models.CharField(max_length=255, blank=True)
    is_active = models.BooleanField(default=True)
```

#### 2. TrainingQualificationGrade (БЕЗ ИЗМЕНЕНИЙ)
```python
class TrainingQualificationGrade(models.Model):
    grade_number = models.PositiveIntegerField()
    label_ru = models.CharField(max_length=255)
    label_by = models.CharField(max_length=255, blank=True)
```

#### 3. TrainingProfession (УПРОСТИТЬ)
```python
class TrainingProfession(models.Model):
    name_ru_nominative = models.CharField(max_length=255)
    name_ru_genitive = models.CharField(max_length=255)
    name_by_nominative = models.CharField(max_length=255, blank=True)
    name_by_genitive = models.CharField(max_length=255, blank=True)

    # УДАЛИТЬ:
    # assigned_name_ru, assigned_name_by (не используются)
    # qualification_grade_default (можно задать в ProductionTraining)

    is_active = models.BooleanField(default=True)
```

#### 4. EducationLevel (БЕЗ ИЗМЕНЕНИЙ)
```python
class EducationLevel(models.Model):
    name_ru = models.CharField(max_length=255, unique=True)
    name_by = models.CharField(max_length=255, blank=True)
    is_active = models.BooleanField(default=True)
```

#### 5. TrainingProgram (КАРДИНАЛЬНО УПРОСТИТЬ)
```python
class TrainingProgram(models.Model):
    """Шаблон программы обучения."""
    name = models.CharField(max_length=255, verbose_name="Название")
    training_type = models.ForeignKey(TrainingType, on_delete=models.PROTECT)
    profession = models.ForeignKey(TrainingProfession, on_delete=models.PROTECT)
    qualification_grade = models.ForeignKey(
        TrainingQualificationGrade,
        on_delete=models.SET_NULL,
        null=True,
        blank=True
    )

    # Программа как JSON (вместо Section + Entry):
    content = models.JSONField(
        default=dict,
        blank=True,
        verbose_name="Содержание программы",
        help_text="JSON с разделами и темами"
    )
    # Структура JSON:
    # {
    #   "sections": [
    #     {
    #       "title": "Раздел 1. Теоретическое обучение",
    #       "entries": [
    #         {"type": "theory", "topic": "Тема 1", "hours": 4},
    #         {"type": "theory", "topic": "Тема 2", "hours": 6}
    #       ]
    #     },
    #     {
    #       "title": "Раздел 2. Производственное обучение",
    #       "entries": [
    #         {"type": "practice", "topic": "Практика 1", "hours": 40}
    #       ]
    #     }
    #   ],
    #   "total_hours": 120,
    #   "theory_hours": 40,
    #   "practice_hours": 80
    # }

    duration_days = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        verbose_name = "📘 Программа обучения"
        unique_together = ['name', 'training_type', 'profession']

    def get_total_hours(self):
        """Подсчитать общее количество часов из JSON."""
        return self.content.get('total_hours', 0)

    def get_sections(self):
        """Получить список разделов."""
        return self.content.get('sections', [])
```

#### 6. ProductionTraining (УПРОСТИТЬ И РЕОРГАНИЗОВАТЬ)

```python
class ProductionTraining(models.Model):
    """Карточка обучения сотрудника на производстве."""

    STATUS_CHOICES = [
        ('draft', 'Черновик'),
        ('active', 'В процессе'),
        ('completed', 'Завершено'),
    ]

    # === ОСНОВНЫЕ ДАННЫЕ ===
    employee = models.ForeignKey(
        'directory.Employee',
        on_delete=models.PROTECT,
        related_name='production_trainings',
        verbose_name="Сотрудник"
    )
    organization = models.ForeignKey(
        'directory.Organization',
        on_delete=models.PROTECT,
        verbose_name="Организация"
    )
    subdivision = models.ForeignKey(
        'directory.StructuralSubdivision',
        on_delete=models.PROTECT,
        null=True, blank=True,
        verbose_name="Подразделение"
    )
    department = models.ForeignKey(
        'directory.Department',
        on_delete=models.PROTECT,
        null=True, blank=True,
        verbose_name="Отдел"
    )

    # === ПРОГРАММА ОБУЧЕНИЯ ===
    training_type = models.ForeignKey(
        TrainingType,
        on_delete=models.PROTECT,
        verbose_name="Тип обучения"
    )
    program = models.ForeignKey(
        TrainingProgram,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        verbose_name="Программа"
    )
    profession = models.ForeignKey(
        TrainingProfession,
        on_delete=models.PROTECT,
        verbose_name="Профессия"
    )
    qualification_grade = models.ForeignKey(
        TrainingQualificationGrade,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        verbose_name="Разряд"
    )

    # === ДОПОЛНИТЕЛЬНЫЕ ДАННЫЕ СОТРУДНИКА ===
    education_level = models.ForeignKey(
        EducationLevel,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        verbose_name="Образование"
    )
    current_position = models.ForeignKey(
        'directory.Position',
        on_delete=models.SET_NULL,
        null=True, blank=True,
        verbose_name="Текущая должность"
    )
    prior_qualification = models.TextField(
        blank=True,
        verbose_name="Имеющаяся квалификация"
    )

    # === ДАТЫ ===
    start_date = models.DateField(
        null=True, blank=True,
        verbose_name="Дата начала"
    )
    end_date = models.DateField(
        null=True, blank=True,
        verbose_name="Дата окончания"
    )

    # === РЕЗУЛЬТАТЫ ЭКЗАМЕНА ===
    exam_date = models.DateField(
        null=True, blank=True,
        verbose_name="Дата экзамена"
    )
    exam_score = models.CharField(
        max_length=50, blank=True,
        verbose_name="Отметка за экзамен"
    )

    # === РЕЗУЛЬТАТЫ ПРАКТИКИ ===
    practical_date = models.DateField(
        null=True, blank=True,
        verbose_name="Дата пробной работы"
    )
    practical_score = models.CharField(
        max_length=50, blank=True,
        verbose_name="Отметка за пробную работу"
    )
    practical_work_topic = models.TextField(
        blank=True,
        verbose_name="Тема пробной работы"
    )

    # === ДОКУМЕНТЫ ===
    registration_number = models.CharField(
        max_length=100, blank=True,
        verbose_name="Регистрационный номер"
    )
    protocol_number = models.CharField(
        max_length=100, blank=True,
        verbose_name="Номер протокола"
    )
    protocol_date = models.DateField(
        null=True, blank=True,
        verbose_name="Дата протокола"
    )

    # === МЕСТО ПРОВЕДЕНИЯ ===
    training_city_ru = models.CharField(
        max_length=255, blank=True,
        verbose_name="Место (рус)"
    )
    training_city_by = models.CharField(
        max_length=255, blank=True,
        verbose_name="Место (бел)"
    )

    # === РОЛИ (упрощённо, без отдельной модели) ===
    instructor = models.ForeignKey(
        'directory.Employee',
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='training_as_instructor',
        verbose_name="Инструктор производственного обучения"
    )
    theory_consultant = models.ForeignKey(
        'directory.Employee',
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='training_as_consultant',
        verbose_name="Консультант по теории"
    )
    commission_chairman = models.ForeignKey(
        'directory.Employee',
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='training_as_chairman',
        verbose_name="Председатель квалификационной комиссии"
    )
    commission_members = models.ManyToManyField(
        'directory.Employee',
        blank=True,
        related_name='training_as_member',
        verbose_name="Члены комиссии"
    )

    # === МЕТАДАННЫЕ ===
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='draft',
        verbose_name="Статус"
    )
    notes = models.TextField(blank=True, verbose_name="Примечания")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "📒 Обучение на производстве"
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['organization', 'employee']),
            models.Index(fields=['start_date', 'end_date']),
        ]

    def __str__(self):
        return f"{self.employee.full_name_nominative} — {self.profession.name_ru_nominative}"

    # === МЕТОДЫ ДЛЯ ГЕНЕРАЦИИ ДОКУМЕНТОВ ===

    def get_instructor_name(self):
        """ФИО инструктора."""
        return self.instructor.full_name_nominative if self.instructor else ''

    def get_exam_date_ru(self):
        """Дата экзамена в русском формате (с названием месяца)."""
        if not self.exam_date:
            return ''
        return format_date_ru(self.exam_date)

    def get_practical_date_ru(self):
        """Дата практики в русском формате."""
        if not self.practical_date:
            return ''
        return format_date_ru(self.practical_date)

    def get_commission_members_list(self):
        """Список членов комиссии."""
        return ', '.join([m.full_name_nominative for m in self.commission_members.all()])


def format_date_ru(date):
    """Преобразовать дату в формат: '5 января 2025 г.'"""
    months_ru = [
        '', 'января', 'февраля', 'марта', 'апреля', 'мая', 'июня',
        'июля', 'августа', 'сентября', 'октября', 'ноября', 'декабря'
    ]
    return f"{date.day} {months_ru[date.month]} {date.year} г."
```

### 2.3. Миграция данных

**Создать миграцию для упрощения:**

```python
# production_training/migrations/0002_simplify_models.py
from django.db import migrations, models
import django.db.models.deletion


def migrate_program_to_json(apps, schema_editor):
    """
    Перенести данные из TrainingProgramSection/Entry в JSON-поле TrainingProgram.content
    """
    TrainingProgram = apps.get_model('production_training', 'TrainingProgram')

    for program in TrainingProgram.objects.all():
        sections = []

        for section in program.sections.all():
            entries = []
            for entry in section.entries.all():
                entries.append({
                    'type': entry.entry_type.code if entry.entry_type else 'theory',
                    'topic': entry.topic,
                    'hours': float(entry.hours)
                })

            sections.append({
                'title': section.title,
                'entries': entries
            })

        # Подсчитать общие часы
        total_hours = sum(
            entry['hours']
            for section in sections
            for entry in section['entries']
        )

        program.content = {
            'sections': sections,
            'total_hours': total_hours
        }
        program.save()


def migrate_roles(apps, schema_editor):
    """
    Перенести TrainingRoleAssignment в поля ProductionTraining
    """
    ProductionTraining = apps.get_model('production_training', 'ProductionTraining')
    TrainingRoleAssignment = apps.get_model('production_training', 'TrainingRoleAssignment')

    for training in ProductionTraining.objects.all():
        for role in training.role_assignments.all():
            role_code = role.role_type.code

            if role_code == 'instructor':
                training.instructor = role.employee
            elif role_code == 'consultant':
                training.theory_consultant = role.employee
            elif role_code == 'chairman':
                training.commission_chairman = role.employee
            elif role_code == 'member':
                training.commission_members.add(role.employee)

        training.save()


class Migration(migrations.Migration):
    dependencies = [
        ('production_training', '0001_initial'),
    ]

    operations = [
        # 1. Добавить новые поля в TrainingProgram
        migrations.AddField(
            model_name='trainingprogram',
            name='content',
            field=models.JSONField(default=dict, blank=True),
        ),

        # 2. Добавить поля ролей в ProductionTraining
        migrations.AddField(
            model_name='productiontraining',
            name='instructor',
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.SET_NULL,
                null=True, blank=True,
                related_name='training_as_instructor',
                to='directory.employee'
            ),
        ),
        # ... остальные поля ролей

        # 3. Мигрировать данные
        migrations.RunPython(migrate_program_to_json, migrations.RunPython.noop),
        migrations.RunPython(migrate_roles, migrations.RunPython.noop),

        # 4. Удалить старые модели
        migrations.DeleteModel(name='TrainingProgramSection'),
        migrations.DeleteModel(name='TrainingProgramEntry'),
        migrations.DeleteModel(name='TrainingEntryType'),
        migrations.DeleteModel(name='TrainingScheduleRule'),
        migrations.DeleteModel(name='TrainingRoleAssignment'),
        migrations.DeleteModel(name='TrainingRoleType'),
        migrations.DeleteModel(name='TrainingDiaryEntry'),
        migrations.DeleteModel(name='TrainingTheoryConsultation'),

        # 5. Удалить старые поля
        migrations.RemoveField(
            model_name='trainingprogram',
            name='order',
        ),
        migrations.RemoveField(
            model_name='trainingprofession',
            name='assigned_name_ru',
        ),
        migrations.RemoveField(
            model_name='trainingprofession',
            name='assigned_name_by',
        ),
        # ... и т.д.
    ]
```

---

## Этап 3: Генераторы документов

### 3.1. Базовый генератор

```python
# production_training/document_generators/__init__.py
from directory.document_generators.base import BaseDocxGenerator
from directory.utils.docx_vml import replace_vml_text_in_docx


class TrainingDocumentGenerator(BaseDocxGenerator):
    """Генератор документов обучения на производстве."""

    def __init__(self, training):
        self.training = training
        super().__init__()

    def _get_base_context(self):
        """Общий контекст для всех документов."""
        t = self.training

        return {
            # Сотрудник
            'employee_name_nom': t.employee.full_name_nominative,
            'employee_name_dat': t.employee.full_name_dative,
            'employee_name_gen': t.employee.full_name_genitive,

            # Профессия
            'profession_nom': t.profession.name_ru_nominative,
            'profession_gen': t.profession.name_ru_genitive,
            'profession_by_nom': t.profession.name_by_nominative,
            'profession_by_gen': t.profession.name_by_genitive,

            # Разряд
            'grade': t.qualification_grade.label_ru if t.qualification_grade else '',
            'grade_number': t.qualification_grade.grade_number if t.qualification_grade else '',

            # Образование
            'education': t.education_level.name_ru if t.education_level else '',
            'education_by': t.education_level.name_by if t.education_level else '',

            # Даты
            'start_date': t.start_date.strftime('%d.%m.%Y') if t.start_date else '',
            'end_date': t.end_date.strftime('%d.%m.%Y') if t.end_date else '',
            'start_date_ru': self._format_date_ru(t.start_date),
            'end_date_ru': self._format_date_ru(t.end_date),
            'exam_date': t.exam_date.strftime('%d.%m.%Y') if t.exam_date else '',
            'exam_date_ru': self._format_date_ru(t.exam_date),
            'practical_date': t.practical_date.strftime('%d.%m.%Y') if t.practical_date else '',
            'practical_date_ru': self._format_date_ru(t.practical_date),
            'protocol_date': t.protocol_date.strftime('%d.%m.%Y') if t.protocol_date else '',
            'protocol_date_ru': self._format_date_ru(t.protocol_date),

            # Оценки
            'exam_score': t.exam_score or '',
            'practical_score': t.practical_score or '',
            'practical_topic': t.practical_work_topic or '',

            # Роли
            'instructor': t.instructor.full_name_nominative if t.instructor else '',
            'consultant': t.theory_consultant.full_name_nominative if t.theory_consultant else '',
            'chairman': t.commission_chairman.full_name_nominative if t.commission_chairman else '',
            'members': t.get_commission_members_list(),

            # Документы
            'reg_number': t.registration_number or '',
            'protocol_number': t.protocol_number or '',

            # Место
            'city_ru': t.training_city_ru or '',
            'city_by': t.training_city_by or '',

            # Организация
            'organization': t.organization.name,
            'subdivision': t.subdivision.name if t.subdivision else '',
        }

    def _format_date_ru(self, date):
        """Дата в формате: 5 января 2025 г."""
        if not date:
            return ''
        months = ['', 'января', 'февраля', 'марта', 'апреля', 'мая', 'июня',
                  'июля', 'августа', 'сентября', 'октября', 'ноября', 'декабря']
        return f"{date.day} {months[date.month]} {date.year} г."

    def _generate_with_vml(self, template_name, vml_mapping):
        """
        Сгенерировать документ с заменой VML-полей.

        Args:
            template_name: Имя шаблона (например, 'learning/application.docx')
            vml_mapping: Словарь {vml_field_name: context_key}
        """
        context = self._get_base_context()

        # Создать VML replacements из маппинга
        vml_replacements = {
            vml_field: context.get(context_key, '')
            for vml_field, context_key in vml_mapping.items()
        }

        return self.generate_docx_from_template(
            template_name=template_name,
            context=context,
            vml_replacements=vml_replacements
        )
```

### 3.2. Конкретные генераторы

```python
# production_training/document_generators/__init__.py (продолжение)

class TrainingDocumentGenerator(BaseDocxGenerator):
    # ... (базовый код выше)

    def generate_application(self):
        """1. Заявление на обучение."""
        vml_mapping = {
            'field1': 'employee_name_gen',  # ФИО (родительный падеж)
            'field2': 'profession_gen',      # Профессия (родительный падеж)
            'field3': 'grade',               # Разряд
            'field4': 'education',           # Образование
            'field5': 'start_date_ru',       # Дата начала
        }
        return self._generate_with_vml('learning/application.docx', vml_mapping)

    def generate_order(self):
        """2. Приказ на обучение."""
        vml_mapping = {
            'field1': 'employee_name_dat',  # ФИО (дательный падеж)
            'field2': 'profession_gen',      # Профессия
            'field3': 'grade',
            'field4': 'start_date_ru',
            'field5': 'end_date_ru',
            'field6': 'instructor',          # Инструктор
            'field7': 'consultant',          # Консультант
        }
        return self._generate_with_vml('learning/order.docx', vml_mapping)

    def generate_theory_card(self):
        """3. Карточка теоретического обучения."""
        vml_mapping = {
            'field1': 'employee_name_nom',
            'field2': 'profession_nom',
            'field3': 'grade',
            'field4': 'education',
            'field5': 'start_date',
            'field6': 'end_date',
            'field7': 'consultant',
        }
        return self._generate_with_vml('learning/theory_card.docx', vml_mapping)

    def generate_diary(self):
        """4. Дневник (подготовка или переподготовка)."""
        # Выбрать шаблон в зависимости от типа обучения
        if self.training.training_type.code == 'preparation':
            template = 'learning/diary_preparation.docx'
        else:
            template = 'learning/diary_retraining.docx'

        context = self._get_base_context()

        # Добавить программу из JSON
        if self.training.program:
            context['program_sections'] = self.training.program.get_sections()
            context['total_hours'] = self.training.program.get_total_hours()

        vml_mapping = {
            'field1': 'employee_name_nom',
            'field2': 'profession_nom',
            'field3': 'grade',
            'field4': 'start_date',
            'field5': 'end_date',
        }

        return self._generate_with_vml(template, vml_mapping)

    def generate_practical_application(self):
        """5. Заявление на пробную работу."""
        vml_mapping = {
            'field1': 'employee_name_gen',
            'field2': 'profession_gen',
            'field3': 'grade',
            'field4': 'practical_date_ru',
            'field5': 'practical_topic',
        }
        return self._generate_with_vml('learning/practical_application.docx', vml_mapping)

    def generate_practical_conclusion(self):
        """6. Заключение на пробную работу."""
        vml_mapping = {
            'field1': 'employee_name_nom',
            'field2': 'profession_nom',
            'field3': 'grade',
            'field4': 'practical_date_ru',
            'field5': 'practical_score',
            'field6': 'practical_topic',
            'field7': 'instructor',
        }
        return self._generate_with_vml('learning/practical_conclusion.docx', vml_mapping)

    def generate_presentation(self):
        """7. Представление на квалификационную комиссию."""
        vml_mapping = {
            'field1': 'employee_name_dat',
            'field2': 'profession_gen',
            'field3': 'grade',
            'field4': 'exam_score',
            'field5': 'practical_score',
            'field6': 'instructor',
        }
        return self._generate_with_vml('learning/presentation.docx', vml_mapping)

    def generate_protocol(self):
        """8. Протокол квалификационной комиссии."""
        vml_mapping = {
            'field1': 'protocol_number',
            'field2': 'protocol_date_ru',
            'field3': 'chairman',
            'field4': 'members',
            'field5': 'employee_name_dat',
            'field6': 'profession_gen',
            'field7': 'grade',
            'field8': 'exam_score',
            'field9': 'practical_score',
            'field10': 'reg_number',
        }
        return self._generate_with_vml('learning/protocol.docx', vml_mapping)

    def generate_all(self):
        """
        Сгенерировать все документы для обучения.

        Returns:
            dict: {document_type: bytes}
        """
        documents = {}

        documents['application'] = self.generate_application()
        documents['order'] = self.generate_order()
        documents['theory_card'] = self.generate_theory_card()
        documents['diary'] = self.generate_diary()
        documents['practical_application'] = self.generate_practical_application()
        documents['practical_conclusion'] = self.generate_practical_conclusion()
        documents['presentation'] = self.generate_presentation()
        documents['protocol'] = self.generate_protocol()

        return documents
```

### 3.3. Сохранение сгенерированных документов

```python
# production_training/models.py (добавить в ProductionTraining)

from django.core.files.base import ContentFile


class ProductionTraining(models.Model):
    # ... (существующие поля)

    # Добавить поля для хранения документов
    document_application = models.FileField(
        upload_to='training_documents/%Y/%m/%d/',
        blank=True,
        verbose_name="Заявление"
    )
    document_order = models.FileField(
        upload_to='training_documents/%Y/%m/%d/',
        blank=True,
        verbose_name="Приказ"
    )
    document_theory_card = models.FileField(
        upload_to='training_documents/%Y/%m/%d/',
        blank=True,
        verbose_name="Карточка теории"
    )
    document_diary = models.FileField(
        upload_to='training_documents/%Y/%m/%d/',
        blank=True,
        verbose_name="Дневник"
    )
    document_practical_application = models.FileField(
        upload_to='training_documents/%Y/%m/%d/',
        blank=True,
        verbose_name="Заявление на практику"
    )
    document_practical_conclusion = models.FileField(
        upload_to='training_documents/%Y/%m/%d/',
        blank=True,
        verbose_name="Заключение"
    )
    document_presentation = models.FileField(
        upload_to='training_documents/%Y/%m/%d/',
        blank=True,
        verbose_name="Представление"
    )
    document_protocol = models.FileField(
        upload_to='training_documents/%Y/%m/%d/',
        blank=True,
        verbose_name="Протокол"
    )

    def generate_documents(self):
        """Сгенерировать и сохранить все документы."""
        generator = TrainingDocumentGenerator(self)
        documents = generator.generate_all()

        # Сохранить файлы
        employee_name = self.employee.full_name_nominative.replace(' ', '_')

        for doc_type, content in documents.items():
            filename = f"{employee_name}_{doc_type}.docx"
            field_name = f"document_{doc_type}"

            field = getattr(self, field_name)
            field.save(filename, ContentFile(content), save=False)

        self.save()
        return documents
```

---

## Этап 4: Админка

### 4.1. Упрощённая админка

```python
# production_training/admin.py

from django.contrib import admin
from django.utils.html import format_html
from django.urls import reverse
from django.http import HttpResponse

from .models import (
    TrainingType,
    TrainingQualificationGrade,
    TrainingProfession,
    EducationLevel,
    TrainingProgram,
    ProductionTraining,
)


@admin.register(TrainingProgram)
class TrainingProgramAdmin(admin.ModelAdmin):
    list_display = ('name', 'training_type', 'profession', 'qualification_grade', 'get_total_hours', 'is_active')
    list_filter = ('training_type', 'profession', 'is_active')
    search_fields = ('name',)

    # Виджет для редактирования JSON
    from django.forms import widgets
    formfield_overrides = {
        models.JSONField: {'widget': widgets.Textarea(attrs={'rows': 20, 'cols': 80})},
    }

    def get_total_hours(self, obj):
        return obj.get_total_hours()
    get_total_hours.short_description = 'Часов'


@admin.register(ProductionTraining)
class ProductionTrainingAdmin(admin.ModelAdmin):
    list_display = (
        'employee',
        'profession',
        'training_type',
        'start_date',
        'end_date',
        'status',
        'documents_status',
        'action_buttons'
    )
    list_filter = ('training_type', 'status', 'profession')
    search_fields = ('employee__full_name_nominative',)
    ordering = ('-created_at',)

    fieldsets = (
        ('Основная информация', {
            'fields': ('employee', 'organization', 'subdivision', 'department')
        }),
        ('Программа обучения', {
            'fields': ('training_type', 'program', 'profession', 'qualification_grade')
        }),
        ('Данные сотрудника', {
            'fields': ('education_level', 'current_position', 'prior_qualification')
        }),
        ('Даты', {
            'fields': ('start_date', 'end_date')
        }),
        ('Роли', {
            'fields': ('instructor', 'theory_consultant', 'commission_chairman', 'commission_members')
        }),
        ('Экзамен', {
            'fields': ('exam_date', 'exam_score')
        }),
        ('Пробная работа', {
            'fields': ('practical_date', 'practical_score', 'practical_work_topic')
        }),
        ('Документы', {
            'fields': ('registration_number', 'protocol_number', 'protocol_date')
        }),
        ('Место', {
            'fields': ('training_city_ru', 'training_city_by')
        }),
        ('Статус', {
            'fields': ('status', 'notes')
        }),
        ('Сгенерированные документы', {
            'fields': (
                'document_application',
                'document_order',
                'document_theory_card',
                'document_diary',
                'document_practical_application',
                'document_practical_conclusion',
                'document_presentation',
                'document_protocol',
            ),
            'classes': ('collapse',)
        }),
    )

    def documents_status(self, obj):
        """Статус сгенерированных документов."""
        count = sum([
            bool(obj.document_application),
            bool(obj.document_order),
            bool(obj.document_theory_card),
            bool(obj.document_diary),
            bool(obj.document_practical_application),
            bool(obj.document_practical_conclusion),
            bool(obj.document_presentation),
            bool(obj.document_protocol),
        ])

        if count == 8:
            return format_html('<span style="color: green;">✓ Все (8)</span>')
        elif count > 0:
            return format_html('<span style="color: orange;">⚠ {}/8</span>', count)
        else:
            return format_html('<span style="color: red;">✗ Нет</span>')

    documents_status.short_description = 'Документы'

    def action_buttons(self, obj):
        """Кнопки действий."""
        if obj.pk:
            return format_html(
                '<a class="button" href="{}">📄 Генерировать все</a>',
                reverse('admin:production_training_generate_docs', args=[obj.pk])
            )
        return ''

    action_buttons.short_description = 'Действия'

    def get_urls(self):
        from django.urls import path
        urls = super().get_urls()
        custom_urls = [
            path(
                '<int:training_id>/generate-docs/',
                self.admin_site.admin_view(self.generate_documents_view),
                name='production_training_generate_docs'
            ),
        ]
        return custom_urls + urls

    def generate_documents_view(self, request, training_id):
        """View для генерации документов."""
        training = ProductionTraining.objects.get(pk=training_id)

        try:
            documents = training.generate_documents()

            self.message_user(
                request,
                f"Успешно сгенерировано {len(documents)} документов для {training.employee.full_name_nominative}"
            )
        except Exception as e:
            self.message_user(request, f"Ошибка генерации: {str(e)}", level='error')

        # Редирект обратно на страницу обучения
        return HttpResponseRedirect(
            reverse('admin:production_training_productiontraining_change', args=[training_id])
        )
```

### 4.2. Массовая генерация документов

```python
# production_training/admin.py (добавить actions)

@admin.register(ProductionTraining)
class ProductionTrainingAdmin(admin.ModelAdmin):
    # ... (существующий код)

    actions = ['generate_documents_for_selected']

    def generate_documents_for_selected(self, request, queryset):
        """Action для массовой генерации документов."""
        success_count = 0
        error_count = 0

        for training in queryset:
            try:
                training.generate_documents()
                success_count += 1
            except Exception as e:
                error_count += 1
                self.message_user(
                    request,
                    f"Ошибка для {training.employee.full_name_nominative}: {str(e)}",
                    level='error'
                )

        if success_count:
            self.message_user(
                request,
                f"Успешно сгенерированы документы для {success_count} обучений"
            )
        if error_count:
            self.message_user(
                request,
                f"Ошибок: {error_count}",
                level='warning'
            )

    generate_documents_for_selected.short_description = "📄 Сгенерировать документы для выбранных"
```

---

## Этап 5: Импорт из Excel

### 5.1. Упрощённый импорт

```python
# production_training/management/commands/import_learning_from_excel.py

from django.core.management.base import BaseCommand
from django.db import transaction
from openpyxl import load_workbook

from directory.models import Employee, Organization
from production_training.models import (
    TrainingType,
    TrainingProfession,
    EducationLevel,
    TrainingProgram,
    ProductionTraining,
)


class Command(BaseCommand):
    help = 'Импорт обучений из Excel (упрощённая версия)'

    def add_arguments(self, parser):
        parser.add_argument(
            '--path',
            default='learning/Обучение на производстве_Сфера Торговый дом.xlsm',
            help='Путь к Excel файлу'
        )

    @transaction.atomic
    def handle(self, *args, **options):
        path = options['path']

        # Использовать openpyxl вместо ручного XML
        wb = load_workbook(path, data_only=True)

        # Импорт справочников
        self._import_professions(wb['Профессии (данные)'])
        self._import_education_levels(wb['База'])

        # Импорт программ
        self._import_programs(wb)

        # Импорт карточек обучений
        self._import_trainings(wb['База'])

        self.stdout.write(self.style.SUCCESS('Импорт завершён'))

    def _import_professions(self, ws):
        """Импорт профессий."""
        for row in ws.iter_rows(min_row=2, values_only=True):
            if not row[0]:
                continue

            TrainingProfession.objects.get_or_create(
                name_ru_nominative=row[0],
                defaults={
                    'name_ru_genitive': row[1] or '',
                    'name_by_nominative': row[2] or '',
                    'name_by_genitive': row[3] or '',
                }
            )

    def _import_programs(self, wb):
        """
        Импорт программ из листов "4. Дневник (переподготовка)" и
        "4.1 Дневник (подготовка)".
        """
        # Пример: прочитать структуру дневника и сохранить в JSON

        for sheet_name in ['4. Дневник (переподготовка)', '4.1 Дневник (подготовка)']:
            ws = wb[sheet_name]

            # Определить тип обучения
            training_type_code = 'retraining' if 'переподготовка' in sheet_name else 'preparation'
            training_type = TrainingType.objects.get(code=training_type_code)

            # Извлечь разделы и темы
            sections = self._parse_program_sheet(ws)

            # Создать программу для каждой профессии
            for profession in TrainingProfession.objects.all():
                program, created = TrainingProgram.objects.get_or_create(
                    name=f"Программа {training_type.name_ru} ({profession.name_ru_nominative})",
                    training_type=training_type,
                    profession=profession,
                    defaults={
                        'content': {
                            'sections': sections,
                            'total_hours': self._calculate_total_hours(sections)
                        }
                    }
                )

    def _parse_program_sheet(self, ws):
        """Парсинг структуры программы из листа Excel."""
        sections = []
        current_section = None

        for row in ws.iter_rows(min_row=2, values_only=True):
            # Логика парсинга разделов и тем
            # (зависит от структуры Excel)
            pass

        return sections
```

---

## Этап 6: Тестирование

### 6.1. Unit-тесты

```python
# production_training/tests/test_document_generation.py

from django.test import TestCase
from django.core.files.base import ContentFile

from directory.models import Employee, Organization
from production_training.models import (
    ProductionTraining,
    TrainingType,
    TrainingProfession,
)
from production_training.document_generators import TrainingDocumentGenerator


class DocumentGenerationTest(TestCase):

    def setUp(self):
        """Создать тестовые данные."""
        self.org = Organization.objects.create(name="Тестовая организация")

        self.employee = Employee.objects.create(
            organization=self.org,
            full_name_nominative="Иванов Иван Иванович",
            full_name_dative="Иванову Ивану Ивановичу",
            full_name_genitive="Иванова Ивана Ивановича",
        )

        self.training_type = TrainingType.objects.create(
            code="preparation",
            name_ru="Подготовка"
        )

        self.profession = TrainingProfession.objects.create(
            name_ru_nominative="Сварщик",
            name_ru_genitive="сварщика"
        )

        self.training = ProductionTraining.objects.create(
            employee=self.employee,
            organization=self.org,
            training_type=self.training_type,
            profession=self.profession,
            start_date="2025-01-10",
            end_date="2025-03-10",
        )

    def test_base_context(self):
        """Тест генерации базового контекста."""
        generator = TrainingDocumentGenerator(self.training)
        context = generator._get_base_context()

        self.assertEqual(context['employee_name_nom'], "Иванов Иван Иванович")
        self.assertEqual(context['profession_nom'], "Сварщик")
        self.assertEqual(context['start_date'], "10.01.2025")

    def test_generate_all_documents(self):
        """Тест генерации всех документов."""
        documents = self.training.generate_documents()

        self.assertEqual(len(documents), 8)
        self.assertIn('application', documents)
        self.assertIn('protocol', documents)

        # Проверить что файлы сохранены
        self.assertTrue(self.training.document_application)
        self.assertTrue(self.training.document_protocol)
```

---

## Этап 7: Deployment

### 7.1. Пошаговый deployment

```bash
# 1. Бэкап БД
cd /home/django/webapps/potby
./backup_db.sh

# 2. Применить миграции
python manage.py makemigrations production_training
python manage.py migrate production_training --settings=settings_prod

# 3. Импортировать данные
python manage.py import_learning_from_excel --settings=settings_prod

# 4. Собрать статику
python manage.py collectstatic --noinput --settings=settings_prod

# 5. Перезапустить Gunicorn
./reload_gunicorn.sh

# 6. Проверить
python manage.py check --settings=settings_prod
```

### 7.2. Rollback plan

```bash
# Если что-то пошло не так:

# 1. Откатить миграции
python manage.py migrate production_training 0001_initial --settings=settings_prod

# 2. Восстановить БД из бэкапа
./restore_db.sh /home/django/backups/pg-ot_online-YYYYMMDD_HHMMSS.sql.gz

# 3. Перезапустить
./reload_gunicorn.sh
```

---

## Итоговый чеклист

### Фаза 1: Подготовка (1-2 дня)
- [ ] Извлечь VML-поля из макет.docx
- [ ] Создать маппинг полей Excel → VML
- [ ] Проверить все 8 шаблонов документов
- [ ] Подготовить тестовые данные

### Фаза 2: Упрощение моделей (2-3 дня)
- [ ] Создать упрощённые модели
- [ ] Написать миграцию с переносом данных
- [ ] Протестировать миграцию на копии БД
- [ ] Обновить админку

### Фаза 3: Генераторы документов (3-4 дня)
- [ ] Базовый генератор TrainingDocumentGenerator
- [ ] 8 методов генерации документов
- [ ] Интеграция с docx_vml.py
- [ ] Сохранение файлов в модели

### Фаза 4: Админка и UI (1-2 дня)
- [ ] Кнопка "Генерировать все документы"
- [ ] Массовая генерация (admin action)
- [ ] Отображение статуса документов
- [ ] Скачивание сгенерированных файлов

### Фаза 5: Импорт (1-2 дня)
- [ ] Переписать импорт с openpyxl
- [ ] Импорт программ в JSON
- [ ] Валидация данных
- [ ] Тестирование на реальном файле

### Фаза 6: Тестирование (2-3 дня)
- [ ] Unit-тесты генераторов
- [ ] Тесты миграции
- [ ] Интеграционные тесты
- [ ] Проверка на production-копии

### Фаза 7: Deployment (1 день)
- [ ] Бэкап БД
- [ ] Применить миграции
- [ ] Импорт данных
- [ ] Сгенерировать тестовые документы
- [ ] Проверка работы

**Общее время: 11-17 дней**

---

## Метрики до/после

| Метрика | До | После | Улучшение |
|---------|-----|--------|-----------|
| Модели | 14 | 6 | -57% |
| Строк кода | ~1573 | ~900 | -43% |
| Полей в ProductionTraining | 30+ | ~25 | -17% |
| Генерация документов | ❌ Нет | ✅ Есть | +100% |
| Сложность миграций | Высокая | Средняя | -40% |
| Время на поддержку | Высокое | Среднее | -50% |

**Главное достижение:** Фокус на генерации документов вместо моделирования структуры Excel.
