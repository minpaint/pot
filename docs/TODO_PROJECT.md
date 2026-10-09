# TODO по проекту (результаты обзора 2026-10-09)

## Инфраструктура / безопасность
- 🔲 **Проверить HSTS на CWP-сервере (192.168.37.55).** В `settings.py` `SECURE_HSTS_*` закомментированы, по документации заголовок должен выставлять CWP. Проверить: `curl -sI https://pot.by | grep -i strict-transport`. Если заголовка нет — добавить на CWP (или включить `SECURE_HSTS_SECONDS` в `settings_prod.py`).
- 🔲 Redis не установлен на сервере, хотя указан в `CLAUDE.md`. Сейчас в `settings_prod.py` кэш = `LocMemCache`, пока не задан `REDIS_URL`. Решить: ставить Redis или убрать упоминания из документации.
- 🔲 Проверить, что `backup_db.sh` запускается по cron, и копировать дампы и `media/` за пределы сервера.

## Репозиторий / документация
- 🔲 Очистить корень проекта (мусор, worktree и ветка `claude/crazy-bardeen-989820` уже удалены 2026-10-09): решить судьбу `db.sqlite3`, `db_old.sqlite3` (старые дампы за декабрь 2025), `4import`, `.venv/` (Windows-остаток).
- 🔲 Свести устаревшие документы в корне (`NEXT_SESSION_PLAN.md`, `REPORT.md`, `SECURITY_FIX_SUMMARY.md`, `learning.md`, `GEMINI.md`, `AGENTS.md`, `README_GIT.md`, `GIT_QUICKSTART.md`, `DEPLOYMENT.md`, `PRODUCTION_QUICKSTART.md`) в `docs/`, убрать дубли.
- 🔲 Актуализировать `CLAUDE.md` (пути `G:\...`, `py manage.py`, Redis).
- 🔲 `NEXT_SESSION_PLAN.md`: выяснить, закрыта ли «Фаза 3 — medical views» (права доступа).
- 🔲 `wsgi.py` жёстко ставит `settings_prod`, а в unit-файле `gunicorn-potby.service` указано `DJANGO_SETTINGS_MODULE=settings` — привести к одному виду.

## Качество кода
- 🔲 `AccessControlHelper.can_access_object` возвращает False для самих моделей Organization/StructuralSubdivision/Department (проверяет только атрибуты `organization`/`subdivision`/`department` у объекта). Сейчас применяется к Employee/Equipment, но если начнут передавать оргструктуру — учесть.
- 🔲 Эндпоинт `/directory/debug-permissions/` отключён от urls; файл `directory/views/debug_permissions.py` и шаблон `directory/templates/debug_permissions.html` можно удалить.
- 🔲 Тесты: расчёт сроков, генерация документов, склонение фамилий, квиз (права доступа — см. `directory/tests/test_access_control.py`).
- 🔲 Разбить крупные модули: `directory/views/siz.py`, `directory/views/hiring.py`, `deadline_control/views/equipment.py`.
- 🔲 Привести шаблоны к дизайн-системе: ~32 шаблона с FontAwesome/Bootstrap Icons, ~14 с `table-striped`/`nav-tabs`/`data-bs-toggle="collapse"`.
