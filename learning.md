# Обучение на производстве — текущая картина работ

## 1. Что изменено / добавлено (по файлам)

### Генерация WordArt/VML в DOCX
- `directory/utils/docx_vml.py`
  - Новый модуль для замены текста внутри VML‑shape (WordArt) в DOCX.
  - Это позволяет заполнять поля WordArt в `макет.docx` без Word/COM.

- `directory/document_generators/base.py`
  - Добавлен импорт `replace_vml_text_in_docx`.
  - В `generate_docx_from_template` появился аргумент `vml_replacements`.
  - После рендера docxtpl выполняется замена текста в VML‑полях.

### Новый тип комиссии
- `directory/models/commission.py`
  - Добавлен тип комиссии: `qualification` (🎓 Квалификационная комиссия).

### Новое приложение `production_training`
- `production_training/__init__.py`
- `production_training/apps.py`
  - `ProductionTrainingConfig` с `verbose_name = "🎓 Обучение на производстве"`.

#### Модели
- `production_training/models.py`
  - Справочники:
    - `TrainingType`
    - `TrainingQualificationGrade`
    - `TrainingProfession`
    - `EducationLevel`
    - `TrainingEntryType`
    - `TrainingScheduleRule`
    - `TrainingRoleType`
  - Программы:
    - `TrainingProgram`
    - `TrainingProgramSection`
    - `TrainingProgramEntry`
  - Основная сущность:
    - `ProductionTraining`
  - Записи:
    - `TrainingRoleAssignment`
    - `TrainingDiaryEntry`
    - `TrainingTheoryConsultation`

#### Админка
- `production_training/admin.py`
  - Регистрация всех моделей.
  - Инлайны для ролей/дневника/консультаций и структуры программ.

#### Фронтенд‑раздел
- `production_training/views.py`
  - `ProductionTrainingListView` (список обучений).
- `production_training/urls.py`
  - Роут `production-training/`.
- `production_training/templates/production_training/training_list.html`
  - Шаблон списка обучений.

#### Миграции
- `production_training/migrations/0001_initial.py`
- `production_training/migrations/__init__.py`

### Подключение приложения
- `settings.py`
  - Добавлен `production_training.apps.ProductionTrainingConfig`.

### Роутинг
- `urls.py`
  - Добавлен маршрут `path('production-training/', include('production_training.urls'))`.

### Админ‑меню
- `config/admin_site.py`
  - Добавлен раздел “🎓 Обучение на производстве” со всеми моделями.

### Пользовательское меню
- `directory/management/commands/populate_menu_items.py`
  - Добавлен пункт “Обучение на производстве” → `production_training:training_list`.

### Импорт из Excel
- `production_training/management/commands/import_learning_from_excel.py`
  - Импорт профессий, образования, ролей, программ, пунктов дневника, карточек обучений.
  - Парсинг XLSM выполнен через zip+XML (без openpyxl).

### Перенос Word‑шаблона
- `media/document_templates/learning/макет.docx`
  - Перенесён из `learning/макет.docx`.


## 2. Что изменилось в системе
- Подготовлен модуль “Обучение на производстве” как отдельное приложение.
- Есть административная часть и минимальный фронт‑список.
- Добавлена поддержка WordArt/VML заполнения в DOCX.
- Добавлен тип комиссии для квалификационных комиссий.


## 3. Что осталось сделать

### A. Миграции и запуск БД
- PostgreSQL должен быть доступен на `localhost:5432`.
- После запуска БД выполнить:
  - `/home/django/webapps/potby/venv/bin/python manage.py migrate`

### B. Заполнить меню
- Выполнить:
  - `/home/django/webapps/potby/venv/bin/python manage.py populate_menu_items`

### C. Импорт из Excel
- Выполнить:
  - `/home/django/webapps/potby/venv/bin/python manage.py import_learning_from_excel`

### D. Генерация документов обучения
- Реализовать генераторы документов под Excel‑шаблоны:
  - Заявление
  - Приказ на обучение
  - Карточка теории
  - Дневник (подготовка/переподготовка)
  - Заявление на пробную работу
  - Заключение на пробную работу
  - Представление
  - Протокол комиссии
- Для `макет.docx` использовать `vml_replacements`.

### E. Привязка документов
- Создать `DocumentTemplateType` для каждого документа обучения.
- Связать генерацию с `ProductionTraining`.

### F. UI для работы с обучением
- В админке уже есть все CRUD‑формы.
- Для пользовательского UI нужны формы создания/редактирования и просмотр деталей.


## 4. Формулировка задачи
Внедрить модуль “Обучение на производстве” как отдельное приложение, выполнить импорт всех данных из Excel, обеспечить генерацию документов на государственных бланках через WordArt/VML‑поля, и дать доступ к модулю в админке и пользовательском меню.


## 5. Рекомендуемый порядок дальнейших действий
1) Запустить PostgreSQL.
2) Применить миграции.
3) Заполнить меню.
4) Импортировать Excel.
5) Реализовать генераторы документов и шаблоны.
6) Добавить пользовательские формы (по необходимости).


## 6. Проверка заглушек в шаблонах документов (обучение)

### Источник
- `media/document_templates/learning/*.docx`

### Итоги
- Заглушки есть в: `1.Заявление.docx`, `2. Приказ о назначении обучения.docx`, `3. Карточка теория.docx`, `5. Завление на квалификационный экзамен.docx`, `6. Заключение на пробную работу.docx`, `7. Представление на квалификационную работу.docx`, `8. Протокол квалификационной комиссии.docx`.
- Заглушек нет в: `4.1.diary_podgotovka_voditel_pogruzchika*.docx`, `4.diary_perepodgotovka_voditel_pogruzchika*.docx`, `макет.docx`.
- Особенности: в `2. Приказ о назначении обучения.docx` есть и `{{ familiarization_list }}` и цикл `{% for person in familiarization_list %}`; в `7. Представление на квалификационную работу.docx` используется `{{ submission_number|default("___") }}`.

### 1.Заявление.docx
- `{{ application_date }}`
- `{{ application_date|default("") }}`
- `{{ director.full_name_dative }}`
- `{{ director.position_dative }}`
- `{{ education_level.name_ru }}`
- `{{ employee.birth_date }}`
- `{{ employee.birth_date|default("") }}`
- `{{ employee.full_name_genitive }}`
- `{{ employee.full_name_nominative }}`
- `{{ employee.position_genitive }}`
- `{{ employee.short_name }}`
- `{{ organization.full_name_ru }}`
- `{{ prior_qualification }}`
- `{{ profession.name_ru_nominative }}`
- `{{ qualification_grade.label_ru }}`
- `{{ training_type.name_ru_accusative }}`

### 2. Приказ о назначении обучения.docx
- `{{ director.position_nominative }}`
- `{{ director.short_name }}`
- `{{ employee.full_name_genitive }}`
- `{{ employee.position_genitive }}`
- `{{ employee.short_name_genitive }}`
- `{{ end_date|default("") }}`
- `{{ familiarization_list }}`
- `{{ instructor.position_nominative }}`
- `{{ instructor.short_name }}`
- `{{ order_date }}`
- `{{ order_date|default("") }}`
- `{{ order_number }}`
- `{{ organization.full_name_ru }}`
- `{{ person.position_nominative }}`
- `{{ person.short_name }}`
- `{{ profession.name_ru_nominative }}`
- `{{ qualification_grade.label_ru_genitive }}`
- `{{ responsible_person.full_name_accusative }}`
- `{{ responsible_person.position_accusative }}`
- `{{ start_date|default("") }}`
- `{{ theory_consultant.position_nominative }}`
- `{{ theory_consultant.short_name }}`
- `{{ training_supervisor.position_nominative }}`
- `{{ training_supervisor.short_name }}`
- `{{ training_type.name_ru_genitive }}`
- `{% for person in familiarization_list %} ... {% endfor %}`

### 3. Карточка теория.docx
- `{{ consultant.full_name_nominative }}`
- `{{ consultant.position_nominative }}`
- `{{ consultant.short_name }}`
- `{{ consultation_end_date|default("") }}`
- `{{ consultation_start_date|default("") }}`
- `{{ employee.full_name_nominative }}`
- `{{ employee.short_name }}`
- `{{ organization.legal_form }}`
- `{{ organization.short_name_ru }}`
- `{{ profession.name_ru_nominative }}`
- `{{ qualification_grade.label_ru }}`
- `{{ session.consultant_initials }}`
- `{{ session.date }}`
- `{{ session.hours }}`
- `{{ total_consultation_hours }}`
- `{{ training_type.name_ru }}`
- `{% for consultant in theory_consultants %} ... {% endfor %}`
- `{% for session in consultation_sessions %} ... {% endfor %}`

### 5. Завление на квалификационный экзамен.docx
- `{{ commission_chairman.full_name_dative }}`
- `{{ employee.short_name }}`
- `{{ exam_application_date|default("") }}`
- `{{ organization.full_name_ru }}`
- `{{ profession.name_ru_nominative }}`
- `{{ qualification_grade.label_ru }}`
- `{{ training_type.name_ru_genitive }}`

### 6. Заключение на пробную работу.docx
- `{{ actual_time_hours }}`
- `{{ director.position_nominative }}`
- `{{ director.short_name }}`
- `{{ employee.full_name_nominative }}`
- `{{ organization.full_name_ru }}`
- `{{ practical_score }}`
- `{{ practical_score_word }}`
- `{{ practical_work_topic }}`
- `{{ profession.name_ru_nominative }}`
- `{{ qualification_grade.label_ru }}`
- `{{ report_date|default("") }}`
- `{{ time_norm_hours }}`
- `{{ training_supervisor.position_nominative }}`
- `{{ training_supervisor.short_name }}`

### 7. Представление на квалификационную работу.docx
- `{{ commission_chairman.full_name_dative }}`
- `{{ employee.full_name_nominative }}`
- `{{ organization.full_name_ru }}`
- `{{ profession.name_ru_nominative }}`
- `{{ qualification_grade.label_ru_genitive }}`
- `{{ start_date|default("") }}`
- `{{ submission_date|default("") }}`
- `{{ submission_number|default("___") }}`
- `{{ training_supervisor.position_nominative }}`
- `{{ training_supervisor.short_name }}`
- `{{ training_type.name_ru_accusative }}`
- `{{ training_type.name_ru_genitive }}`

### 8. Протокол квалификационной комиссии.docx
- `{{ commission_chairman.position_nominative }}`
- `{{ commission_chairman.short_name }}`
- `{{ loop.index }}`
- `{{ member.position_nominative }}`
- `{{ member.short_name }}`
- `{{ organization.full_name_ru }}`
- `{{ protocol_date }}`
- `{{ protocol_number }}`
- `{{ student.birth_year }}`
- `{{ student.education_level }}`
- `{{ student.exam_score }}`
- `{{ student.exam_score_word }}`
- `{{ student.full_name_nominative }}`
- `{{ student.note|default("") }}`
- `{{ student.practical_score }}`
- `{{ student.practical_score_word }}`
- `{{ student.profession }}`
- `{{ student.rank }}`
- `{{ student.theory_score }}`
- `{{ student.theory_score_word }}`
- `{% for member in commission_members %} ... {% endfor %}`
- `{% for student in exam_candidates %} ... {% endfor %}`
