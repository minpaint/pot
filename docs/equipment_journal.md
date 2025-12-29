# Система журналов осмотра оборудования

Этот модуль формирует журналы осмотра оборудования по выбранному типу и поддерживает отправку по email с логированием.

## Где находится

- Основные view: `deadline_control/views/equipment.py`
- Генератор документов: `directory/document_generators/equipment_journal_generator.py`
- Шаблоны интерфейса:
  - `templates/deadline_control/equipment/journal_tree.html`
  - `templates/deadline_control/equipment/journal_preview.html`
- Логи рассылки:
  - `deadline_control/models/equipment_send_log.py`
  - `deadline_control/admin/equipment_send_log.py`
- Команда для шаблона письма:
  - `deadline_control/management/commands/create_equipment_journal_template.py`

## Точка входа

Страница журнала:
`/deadline-control/equipment/journal/`

URL-ендпоинты:
- `journal/` -> `EquipmentJournalView`
- `journal/send-sample/<subdivision_id>/` -> отправка образца для подразделения
- `journal/preview/<organization_id>/` -> предпросмотр массовой отправки
- `journal/send-organization/<organization_id>/` -> массовая отправка

## Логика страницы журнала

1. Пользователь выбирает тип оборудования и дату осмотра.
2. Строится дерево: Организация -> Подразделение -> Отдел -> Оборудование.
3. Доступ ограничен `AccessControlHelper`.
4. Параметры `equipment_type` и `inspection_date` сохраняются в сессию (`equipment_journal_params`) и используются в отправке.

Кнопки:
- "Скачать общий журнал": один файл по всему списку.
- "Скачать по подразделениям": ZIP с отдельным файлом на подразделение.
- "Отправить образец": email с вложением для выбранного подразделения.
- "Предпросмотр рассылки": показывает, кто получит письма и тему.

## Генерация документов

Функции:
- `generate_equipment_journal_for_subdivision(...)` — основной генератор для общего журнала и по подразделениям.
- `generate_equipment_journal(...)` — совместимость со старой формой генерации.

Поведение:
- Таблица журнала очищается и заполняется только данными (пустые строки не добавляются).
- Шрифт данных: 14 pt.
- В колонке инвентарного номера выводится формат `"Инв. № {номер}"`.
- Границы выставляются только для строк с данными.
- Дата осмотра берется из выбранной пользователем даты (если задана), иначе из `last_maintenance_date`.

### Место эксплуатации

Заполнение зависит от типа генерации:
- Общий журнал (`Скачать общий журнал`): две последние сущности из цепочки Организация -> Подразделение -> Отдел.
  - Примеры: "Подразделение / Отдел", либо "Организация / Подразделение".
- По подразделениям и email-рассылка: один последний уровень (Отдел, иначе Подразделение, иначе Организация).

## Титульный лист

В шаблоне используется переменная `structural_unit`:
- Общий журнал: полное название организации.
- По подразделениям: название структурного подразделения.

Дополнительно передаются стандартные переменные:
- `organization.full_name_ru`, `organization.short_name_ru`
- `start_date`, `end_date`
- `equipment_records`
- `subdivision_name`

## Имена файлов

Формат имени:

`Журнал осмотра {тип} {организация/подразделение} {дата}.docx`

Дата в формате `DD.MM.YYYY`.

Особый случай:
- Для типа "грузовая тележка" / "грузовые тележки" используется метка `"тележек"`.

Примеры:
- `Журнал осмотра тележек Производственный цех №1 25.12.2025.docx`
- `Журнал осмотра лестница ООО Ромашка 25.12.2025.docx`

## Email-рассылка

Источники получателей:
- `collect_recipients_for_subdivision(..., notification_type='general')`.

Шаблон письма:
- код типа: `equipment_journal`.
- создается командой `create_equipment_journal_template`.

Переменные шаблона:
- `organization_name`
- `subdivision_name`
- `department_name`
- `inspection_date`
- `equipment_type`
- `equipment_count`

## Логи рассылки

Модели:
- `EquipmentJournalSendLog` — общий лог рассылки.
- `EquipmentJournalSendDetail` — детализация по подразделениям.

Статусы:
- `in_progress`, `completed`, `partial`, `failed`.
- детали: `success`, `failed`, `skipped`.

Причины пропуска:
- `no_recipients`, `no_equipment`, `doc_generation_failed`, `template_not_found`, `email_send_failed`.

Админка:
- `EquipmentJournalSendLogAdmin` показывает статистику и детали отправки.

## Запуск

1. Применить миграции:
   `py manage.py migrate`
2. Создать эталонный email-шаблон:
   `py manage.py create_equipment_journal_template`
3. Открыть страницу журнала:
   `/deadline-control/equipment/journal/`

## Примечания

- Параметры журнала берутся из сессии, поэтому перед отправкой образца/массовой рассылки необходимо сначала выбрать тип и дату на странице журнала.
- Если email-шаблон не настроен, отправка фиксируется как ошибка в логах.
