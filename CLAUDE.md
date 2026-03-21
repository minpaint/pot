# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Communication Guidelines

**ВАЖНО:** Всегда отвечай на русском языке при работе с этим проектом. Это российско-белорусская система управления охраной труда, и все коммуникации должны быть на русском языке, чтобы соответствовать контексту проекта и ожиданиям пользователя.

**IMPORTANT:** Always respond in Russian when working with this project. This is a Russian-Belarusian occupational safety management system, and all communications should be in Russian to match the project context and user expectations.

## Project Overview

**OT_online** is a comprehensive occupational safety management system (охрана труда) built with Django 5.0. It manages organizational structure, employees, equipment, personal protective equipment (PPE/СИЗ), medical examinations, commissions, and safety quizzes for Russian/Belarusian organizations.

**Primary Language:** Russian (with Belarusian support)
**Production Domain:** https://pot.by
**Python Environment:**
- **Production:** Linux (Ubuntu), `/home/django/webapps/potby/venv/`
- **Development:** Windows (legacy), `c:\venvs\OT_online\Scripts\python.exe`

## Production Architecture

**ВАЖНО:** Проект развёрнут в **двухуровневой архитектуре** через CWP (CentOS Web Panel).

```
Интернет (pot.by)
       ↓ HTTPS
[CWP Server: 192.168.37.55] ← SSL терминация, security headers, редиректы
       ↓ HTTP (внутренняя сеть)
[Django Server: 192.168.37.10:8020] ← Nginx → Gunicorn → Django
       ↓
PostgreSQL (localhost:5432)
Redis (localhost:6379)
```

### Ключевые особенности архитектуры:

1. **CWP сервер (192.168.37.55) - Фронтальный прокси:**
   - Принимает HTTPS запросы от внешнего мира
   - SSL терминация (Let's Encrypt сертификаты)
   - HTTP → HTTPS редиректы
   - www.pot.by → pot.by редиректы
   - Security headers (HSTS, X-Frame-Options, CSP)
   - Rate limiting
   - Проксирует на Django сервер по HTTP

2. **Django сервер (192.168.37.10) - Backend:**
   - Работает по HTTP внутри локальной сети (192.168.37.0/24)
   - Порт 8020 **НЕ открыт** для внешнего доступа
   - Nginx (локальный) на порту 80 проксирует на Gunicorn :8020
   - Gunicorn (3 workers) запускает Django WSGI приложение
   - PostgreSQL и Redis доступны только локально

3. **Безопасность:**
   - **Первый уровень (CWP):** SSL, HSTS, security headers, блокировка по IP
   - **Второй уровень (Django):** CSRF, аутентификация, валидация, application-level security
   - **DEBUG всегда False** в production (жёстко установлено в settings.py)
   - **Кастомные страницы ошибок** без раскрытия технической информации

### Логи в production

В логах Django все запросы приходят от **192.168.37.55** (CWP сервер):
```
192.168.37.55 - - [29/Dec/2025:16:27:49 +0300] "GET /admin/ HTTP/1.0" 200 35985
```
Реальный IP клиента находится в заголовке `X-Forwarded-For`.

### Важные IP адреса

- `192.168.37.55` - CWP сервер (фронтальный прокси)
- `192.168.37.10` - Django сервер (backend, недоступен извне)
- **Оба IP адреса ДОЛЖНЫ быть в `ALLOWED_HOSTS`** для корректной работы прокси

См. подробную документацию: [docs/CWP_ARCHITECTURE.md](docs/CWP_ARCHITECTURE.md)

## Common Commands

### Production (Linux)

```bash
# Управление Gunicorn
cd /home/django/webapps/potby
./start_gunicorn.sh      # Запуск с проверкой DEBUG
./reload_gunicorn.sh     # Graceful reload (без даунтайма)
./stop_gunicorn.sh       # Остановка

# Проверка безопасности
DJANGO_SETTINGS_MODULE=settings_prod venv/bin/python \
    utility_scripts/check_debug_status.py

# Применить миграции
python manage.py migrate --settings=settings_prod

# Собрать статику
python manage.py collectstatic --noinput --settings=settings_prod

# Django shell (production)
python manage.py shell --settings=settings_prod

# Проверка
python manage.py check --settings=settings_prod

# Логи
tail -f logs/gunicorn.access.log
tail -f logs/gunicorn.error.log

# Процессы
ps aux | grep gunicorn | grep potby
```

### Development (Windows)

```bash
# Run development server
py manage.py runserver

# Run development server on alternative port with exam subdomain support
py manage.py runserver 8001

# Create migrations
py manage.py makemigrations

# Apply migrations
py manage.py migrate

# Check for issues
py manage.py check

# Django shell
py manage.py shell

# Create superuser
py manage.py createsuperuser

# Collect static files (for production)
py manage.py collectstatic
```

### Database Operations

```bash
# Show specific migration SQL
py manage.py sqlmigrate directory 0025

# List migrations
py manage.py showmigrations

# Rollback migration
py manage.py migrate directory 0024
```

### Custom Management Commands

```bash
# Import quiz questions (v1)
py manage.py import_quiz_questions

# Import quiz questions (v2, improved)
py manage.py import_quiz_questions_v2
```

## Development Guidelines

### 🚨 КРИТИЧНО: DEBUG и Error Handlers

**ВАЖНО:** В production DEBUG ВСЕГДА должен быть False!

1. **DEBUG жёстко отключён в settings.py:**
   ```python
   DEBUG = False  # КРИТИЧНО: всегда False в production!
   ```

2. **settings_prod.py переопределяет:**
   ```python
   DEBUG = False
   ```

3. **Для development используйте settings_dev.py:**
   ```bash
   export DJANGO_SETTINGS_MODULE=settings_dev
   python manage.py runserver
   ```

4. **Почему это критично:**
   - DEBUG=True раскрывает полную структуру URL
   - Показывает пути к файлам проекта
   - Может показать SECRET_KEY в traceback
   - Раскрывает установленные библиотеки и их версии
   - **Даёт атакующим полную карту приложения!**

5. **Error handlers (directory/error_handlers.py):**
   - **НЕ ПЕРЕДАЮТ** exception details пользователю
   - Детали логируются для разработчиков
   - Пользователям показываются красивые кастомные страницы
   - В шаблонах error-details не должно быть контента

6. **Проверка перед деплоем:**
   ```bash
   DJANGO_SETTINGS_MODULE=settings_prod venv/bin/python \
       scripts/check_debug_status.py
   ```

См. подробнее: [docs/DEBUG_MODE_FIX.md](docs/DEBUG_MODE_FIX.md)

### Test and Utility Scripts

**IMPORTANT:** All test and utility scripts MUST be created in the `utility_scripts/` directory, not in the project root.

- **Location:** `G:\Мой диск\OT_online\utility_scripts/`
- **Purpose:** Temporary scripts for testing, debugging, data analysis, or one-off tasks
- **Git behavior:** This directory is ignored by Git (configured in `.gitignore`)
- **Naming:** Use descriptive names like `check_*.py`, `test_*.py`, `debug_*.py`, `demo_*.py`

**Examples of scripts that belong in utility_scripts/:**
- Database check scripts (`check_medical_template.py`)
- Test email scripts (`demo_medical_email.py`)
- Data migration utilities (`recreate_templates.py`)
- Debug scripts for specific features
- One-time data population scripts

**NEVER create test scripts in:**
- Project root directory
- App directories (`directory/`, `deadline_control/`)
- Template or static directories

Management commands for permanent functionality should use Django's `management/commands/` structure.

## Architecture Overview

### Single-App Structure

The project uses a monolithic Django app structure with **one main application** called `directory` that contains all functionality. This differs from typical multi-app Django projects.

```
OT_online/
├── directory/              # Main and only Django app
│   ├── models/            # Models split by domain (17 models)
│   ├── admin/             # Admin classes split by domain
│   ├── views/             # Views split by functional area
│   ├── resources/         # django-import-export resources
│   ├── forms/             # Form classes
│   ├── middleware/        # Custom middleware
│   └── management/        # Custom management commands
├── templates/             # Global templates
├── static/                # Global static files
├── media/                 # User-uploaded files
├── config/                # Django admin configuration
├── settings.py            # Main settings file
├── settings_prod.py       # Production settings
├── urls.py                # Root URL configuration
└── manage.py              # Django management script
```

### Key Architectural Patterns

1. **Model Organization:** Models are split into separate files by domain (e.g., `employee.py`, `quiz.py`, `medical_examination.py`) but all imported in `directory/models/__init__.py`

2. **Admin Organization:** Each model has its own admin file in `directory/admin/` with custom admin classes, often using `django-import-export` and `nested-admin`

3. **URL Namespacing:** Uses nested URL namespacing:
   - Root: `directory` namespace
   - Sub-namespaces: `auth`, `employees`, `positions`, `quiz`, `medical`, etc.
   - Example: `reverse('directory:quiz:quiz_start', args=[quiz_id])`

4. **Tree View Pattern:** Custom tree-based admin views for hierarchical data (Organization → Subdivision → Department) used for Position, Employee, and Equipment models

5. **Exam Subdomain Isolation:** The quiz system uses a separate subdomain (`exam.*`) with strict access control via middleware (`ExamSubdomainMiddleware`)

### Domain Models (17 Total)

**Organizational Structure (4 models):**
- `Organization` - Companies/organizations
- `StructuralSubdivision` - Departments/divisions
- `Department` - Sub-departments
- `Profile` - User profiles with multi-organization access

**Personnel (3 models):**
- `Position` - Job positions with safety requirements
- `Employee` - Staff members
- `EmployeeHiring` - Hiring history

**Equipment & Documents (2 models):**
- `Equipment` - Equipment requiring maintenance
- `Document` - General documents

**PPE/СИЗ System (3 models):**
- `SIZ` - PPE catalog
- `SIZNorm` - PPE issuance standards per position
- `SIZIssued` - Issued PPE tracking

**Medical Examinations (5 models):**
- `MedicalExaminationType` - Exam types
- `HarmfulFactor` - Occupational hazards
- `MedicalExaminationNorm` - Reference norms
- `PositionMedicalFactor` - Position-hazard mapping
- `EmployeeMedicalExamination` - Employee exam records

**Commissions & Documents (4 models):**
- `Commission` - Safety commissions
- `CommissionMember` - Commission participants
- `DocumentTemplate` - DOCX templates
- `GeneratedDocument` - Generated documents

**Quiz System (6 models):**
- `QuizCategory` - Quiz categories/topics
- `Quiz` - Quiz definitions (training or exam mode)
- `Question` - Questions with images
- `Answer` - Answer options
- `QuizAttempt` - User attempts
- `UserAnswer` - Individual answers
- `QuizAccessToken` - Token-based access
- `QuizQuestionOrder` - Question ordering

## Critical Implementation Details

### 1. Hierarchical Validation

Many models enforce organizational hierarchy validation in their `clean()` method:
- Department must belong to the same organization as its subdivision
- Employee's position must be in the same organizational unit
- Equipment must belong to valid org structure

**When modifying these models**, always maintain validation logic.

### 2. Quiz System Subdomain Security

The quiz system operates on `exam.*` subdomain with strict isolation:

- **Middleware:** `ExamSubdomainMiddleware` blocks ALL non-quiz URLs on exam subdomain
- **Access Control:** Only accessible via `QuizAccessToken` stored in session
- **No Indexing:** robots.txt and X-Robots-Tag headers prevent search engine indexing
- **Security Headers:** CSP, Cache-Control, X-Frame-Options enforce strict security

**When working with quiz views:**
- Check for `request.session.get('quiz_token_mode')` for token-based access
- Use `@login_required` for regular authenticated access
- Store quiz question order in session: `request.session[f'quiz_questions_{attempt_id}']`

### 3. Import/Export System

Uses `django-import-export` with custom Resource classes:
- **StructureResource** - Cascading import: Organization → Subdivision → Department
- **EmployeeResource** - Auto-generates dative case (дательный падеж) using `pymorphy2`
- **EquipmentResource** - Auto-generates inventory numbers (8 digits)

Import process stores preview data in session for confirmation step.

### 4. Document Generation

System supports DOCX template-based document generation using `docxtpl`:
- Templates stored in `media/document_templates/`
- Generated documents in `media/generated_documents/YYYY/MM/DD/`
- Templates can be "reference" (is_default=True) or organization-specific

**Context data** is stored in JSON format in `GeneratedDocument.document_data`.

### 5. Maintenance Date Calculations

Equipment maintenance uses custom date arithmetic in `Equipment._add_months()` that handles month-end edge cases correctly. Always use this method for maintenance date calculations, not simple `timedelta`.

### 6. Declension System

Russian declension using `pymorphy2` for:
- Employee names (nominative → dative for orders/documents)
- Position names in generated documents

Found in `directory/utils/declension.py`.

## Settings and Configuration

### Environment Variables

Configuration loaded from `.env` file (use `python-dotenv`):

**Critical variables:**
- `DJANGO_SECRET_KEY` - Secret key for Django
- `DJANGO_DEBUG` - Debug mode (True/False)
- `DJANGO_ALLOWED_HOSTS` - Comma-separated host list
- `DATABASE_URL` or `DB_ENGINE`, `DB_NAME`, etc. - Database config
- `EXAM_SUBDOMAIN` - Exam subdomain (default: exam.localhost:8001)
- `EXAM_PROTOCOL` - Protocol for exam subdomain (http/https)

**Defaults to SQLite** if no database variables set.

### Two Settings Files

- `settings.py` - Development/staging settings
- `settings_prod.py` - Production settings

### Static Files

- **Development:** Served by Django from `STATICFILES_DIRS`
- **Production:** Uses WhiteNoise with `CompressedManifestStaticFilesStorage`
- **Collection path:** `../data/static/` (outside project root for hosting)

### Media Files

- **Path:** `BASE_DIR / 'media'`
- **Subdirectories:**
  - `quiz/questions/` - Quiz question images
  - `document_templates/` - DOCX templates
  - `generated_documents/` - Generated documents
  - `medical/certificates/` - Medical certificates

## Testing Considerations

When writing tests:

1. **Use `TESTING` flag:** Settings detect test mode via `sys.argv[1] == 'test'`
2. **Separate test DB:** SQLite uses `test_db.sqlite3` for tests
3. **Debug toolbar disabled** during tests
4. **Session handling:** Quiz system heavily uses session - mock appropriately

## Database Migrations

### Zero-Downtime Migrations (Production)

**ВАЖНО:** Проект использует `django-pg-zero-downtime-migrations` для минимизации блокировок при миграциях на production.

**Установлено:**
- `django-pg-zero-downtime-migrations>=0.11` - автоматическая минимизация блокировок
- `django-migration-linter>=5.0` - проверка опасных операций (опционально)
- Backend: `django_zero_downtime_migrations.backends.postgres` (в `settings_prod.py`)

### Workflow создания миграций на Production

**ВСЕГДА следуй этому workflow при создании миграций:**

1. **Изменить модели:**
   ```bash
   nano directory/models/employee.py  # или другая модель
   ```

2. **Создать миграцию:**
   ```bash
   python manage.py makemigrations directory --name описание_изменения --settings=settings_prod
   ```

3. **Проверить SQL (обязательно!):**
   ```bash
   python manage.py sqlmigrate directory 0056 --settings=settings_prod
   ```

4. **Создать бэкап БД:**
   ```bash
   ./backup_db.sh
   ```
   - Бэкапы хранятся в `/home/django/backups/pg-ot_online-YYYYMMDD_HHMMSS.sql.gz`
   - Автоматическая ротация: удаление файлов старше 30 дней

5. **Применить миграцию:**
   ```bash
   python manage.py migrate --settings=settings_prod
   ```

6. **Перезапустить Gunicorn:**
   ```bash
   ./reload_gunicorn.sh  # graceful reload без даунтайма
   ```

7. **Проверить работу сайта:**
   - Открыть https://pot.by
   - Проверить что изменения работают

8. **Закоммитить в Git:**
   ```bash
   git add directory/migrations/0056_*
   git commit -m "Добавлена миграция: описание_изменения"
   git push origin develop
   ```

### Автоматический workflow через deploy_from_git.sh

При использовании `./deploy_from_git.sh`:
- Автоматически проверяет наличие неприменённых миграций
- Создаёт бэкап БД перед применением миграций
- Применяет миграции
- При ошибке показывает команду для отката

### Откат миграций при проблемах

**Быстрый откат к предыдущей миграции:**
```bash
python manage.py migrate directory 0055 --settings=settings_prod
./reload_gunicorn.sh
```

**Полный откат через бэкап (если что-то сломалось):**
```bash
# Посмотреть доступные бэкапы
ls -lth /home/django/backups/

# Восстановить БД
./restore_db.sh /home/django/backups/pg-ot_online-20251231_150000.sql.gz
# restore_db.sh автоматически:
# 1. Остановит Gunicorn
# 2. Завершит активные соединения с БД
# 3. Восстановит БД из дампа
# 4. Запустит Gunicorn
```

**Удалить миграцию полностью:**
```bash
# 1. Откатить миграцию в БД
python manage.py migrate directory 0055 --settings=settings_prod

# 2. Удалить файл миграции
rm directory/migrations/0056_unwanted.py

# 3. Перезапустить
./reload_gunicorn.sh
```

### Zero-Downtime стратегии

**Что безопасно делать напрямую:**
- ✅ Добавление nullable полей
- ✅ Добавление таблиц
- ✅ Создание индексов (автоматически с CONCURRENTLY)

**Что требует осторожности:**
- ❌ **Добавление NOT NULL полей** - делать в 2-3 шага:
  1. Добавить как nullable
  2. Заполнить данные через RunPython
  3. Сделать NOT NULL

- ❌ **Удаление полей** - сначала удалить из кода, потом создать миграцию
- ❌ **Переименование полей** - добавить новое → обновить код → удалить старое
- ❌ **Изменение типа поля** - добавить новое → мигрировать данные → удалить старое

### Migration naming convention

**Используй описательные имена с `--name` flag:**
```bash
py manage.py makemigrations directory --name add_quiz_access_tokens
```

**Recent major migrations:**
- `0025_add_quiz_models` - Added entire quiz system
- `0029_*_quizaccesstoken` - Added token-based access
- `0034_remove_quiz_type` - Removed deprecated quiz_type field

### Важные заметки

- **Бэкапы не коммитятся в Git:** `.gitignore` содержит `backups/` и `*.sql.gz`
- **Автоаутентификация PostgreSQL:** `~/.pgpass` уже настроен
- **Ротация бэкапов:** Автоматическое удаление файлов старше 30 дней
- **Backend для zero-downtime:** `django_zero_downtime_migrations.backends.postgres` в `settings_prod.py`

## Common Patterns

### Autocomplete Views

Uses `django-autocomplete-light` (DAL) with Select2:
- All autocomplete views in `directory/autocomplete_views.py`
- URL pattern: `/directory/autocomplete/{model}/`
- Forward fields supported for cascading dropdowns

### Admin Tree Views

Custom template with JavaScript for collapsible tree:
- Template: `templates/admin/directory/{model}/change_list_tree.html`
- JavaScript: `static/admin/js/tree_view.js`
- Used for: Position, Employee, Equipment

### Validation Pattern

Models use `clean()` method for validation:
```python
def clean(self):
    if self.department and self.department.organization != self.organization:
        raise ValidationError("Department must belong to same organization")
```

Always call `super().clean()` and validate hierarchical relationships.

### Russian Date/Number Formatting

Use `DATE_FORMAT`, `DATETIME_FORMAT` settings for Russian format:
- Language: `ru-ru`
- Timezone: `Europe/Moscow`
- USE_TZ = True (use timezone-aware datetimes)

## Important Quirks

1. **inspect.getargspec monkeypatch:** Required in `manage.py` for Python 3.11+ compatibility with `pymorphy2`

2. **Organization field everywhere:** Almost all models have `organization` ForeignKey - this is intentional for multi-tenancy

3. **Russian field names:** Model fields often use transliterated Russian (e.g., `full_name_nominative`, `full_name_dative`)

4. **Emoji in admin:** Admin interface uses emoji extensively for visual clarity (🏢, 👥, 📋, etc.)

5. **Custom middleware order:** `ExamSubdomainMiddleware` must be early in middleware stack to enforce subdomain restrictions

6. **No REST API:** System uses traditional Django views with AJAX endpoints for interactivity (not Django REST Framework)

## Documentation Files

- `docs/PROJECT_DESCRIPTION.md` - Comprehensive project documentation
- `docs/QUIZ_SYSTEM.md` - Quiz system architecture and usage
- `docs/QUIZ_TOKEN_SETUP.md` - Token-based access setup
- `docs/QUIZ_IMPORT_GUIDE.md` - Importing quiz questions
- `docs/SECURITY_GUIDE.md` - Security best practices
- `docs/IMPORT_EXPORT.md` - Import/export functionality

## Production Deployment Notes

- Use `settings_prod.py` for production
- Configure `STATIC_ROOT` to `../data/static/`
- Set `SECURE_SSL_REDIRECT`, `HSTS` headers for HTTPS
- Configure proper `ALLOWED_HOSTS` and `CSRF_TRUSTED_ORIGINS`
- Use PostgreSQL (configured via `DATABASE_URL`)
- Set up WhiteNoise for static file serving
- Configure exam subdomain in DNS and web server

## Known Issues and Workarounds

1. **pymorphy2 on Python 3.11+:** Requires `inspect.getargspec` monkeypatch in `manage.py`
2. **Windows paths:** Project developed on Windows - path handling uses `Path` objects for cross-platform compatibility
3. **Exam subdomain on localhost:** Use `exam.localhost:8001` format, ensure proper hosts file or browser support

## Git Workflow на Production

**ВАЖНО:** Разработка ведётся **напрямую на production сервере** с коммитами в GitHub.

### Текущий workflow:

```
Production Server (192.168.37.10)
    ↓ разработка
    ↓ git commit
    ↓ git push
GitHub Repository (github.com/minpaint/pot)
    ↓ backup / история
```

### Репозиторий и ветки:

- **GitHub:** https://github.com/minpaint/pot
- **Ветка develop:** для разработки и промежуточных версий
- **Ветка main:** стабильная версия production
- **SSH ключ:** `~/.ssh/id_ed25519_potby`
- **SSH host:** `github-potby` (в `~/.ssh/config`)

### Основные команды:

```bash
# Проверка статуса
git status
git diff

# Коммит изменений в develop
git checkout develop
git add .
git commit -m "Описание изменений"
git push origin develop

# Перенос в main когда готово
git checkout main
git merge develop
git push origin main
```

### Важные правила:

1. ✅ **Коммитить регулярно** - это backup + история изменений
2. ❌ **НЕ коммитить секреты:** `.env`, пароли, API ключи, SECRET_KEY
3. ❌ **НЕ делать** `git push --force` без крайней необходимости
4. ✅ **Проверять изменения** перед коммитом: `git status`, `git diff`
5. ✅ **Писать осмысленные commit messages**
6. ✅ **Использовать ветку develop** для разработки

### Git конфигурация (уже применена):

```bash
git config core.autocrlf input      # Нормализация line endings (Linux)
git config core.fileMode false      # Игнорировать изменения прав доступа
git config user.name "OT_online Developer"
git config user.email "dev@ot-online.local"
```

### Скрипты управления сервером:

- `./start_gunicorn.sh` - Запуск Gunicorn с проверками
- `./reload_gunicorn.sh` - Graceful reload без даунтайма
- `./stop_gunicorn.sh` - Остановка Gunicorn
- `scripts/check_debug_status.py` - Проверка настроек безопасности

### Подробная документация:

- **GIT_WORKFLOW_PRODUCTION.md** - 📋 ПОЛНОЕ руководство по Git workflow (читать в первую очередь!)
- **GIT_QUICKSTART.md** - Быстрый старт по Git
- **docs/CWP_ARCHITECTURE.md** - Архитектура развёртывания

### Для Claude Code:

**При команде "закоммить и запушить" следовать инструкциям из `GIT_WORKFLOW_PRODUCTION.md`:**
1. Проверить статус и изменения
2. Убедиться что нет секретов в коммите
3. Создать осмысленный commit message
4. Запушить в нужную ветку (обычно develop)
5. Показать ссылку на GitHub

---

## Frontend Design System (UI Guidelines)

**ВАЖНО:** Все новые и переработанные страницы фронтенда ОБЯЗАНЫ следовать единому дизайн-системе, описанной ниже. Это не пожелание — это стандарт проекта.

### Эталонные страницы

При создании новых страниц ориентируйся на эти реализованные образцы:
- `templates/deadline_control/equipment/unified.html` — дерево Орг→Подразделение→Тип→Оборудование
- `templates/directory/hiring/list.html` — список с фильтрами и пагинацией
- `templates/directory/siz/mass_generation.html` — двухвкладочная страница с деревом и таблицей

### Обязательные правила

#### 1. Заголовки карточек организации — только градиент

```css
background: linear-gradient(135deg, #2c3e50 0%, #3498db 100%);
color: #fff;
```

**Запрещено:** `bg-primary`, `bg-dark`, `card-header` с Bootstrap-цветами.

#### 2. Иконки — только эмодзи

Использовать встроенные Unicode-эмодзи: 🏢 🏭 📂 👤 📋 ⚙️ 🛡️ 📅 🔍 ✉️ 📥 ✏️ 🗑️ ➕ и т.д.

**Запрещено:** FontAwesome, Bootstrap Icons, любые иконочные шрифты.

#### 3. Панель фильтров / управления — стиль topbar

```css
.XXX-topbar {
    background: #fff;
    border: 1px solid #dee2e6;
    border-radius: 10px;
    padding: 14px 20px;
    margin-bottom: 20px;
    display: flex;
    flex-wrap: wrap;
    align-items: flex-end;
    gap: 12px;
}
.XXX-topbar label {
    font-size: 0.78rem;
    font-weight: 600;
    color: #6c757d;
    margin-bottom: 3px;
    display: block;
    text-transform: uppercase;
    letter-spacing: 0.3px;
}
```

**Запрещено:** `<form class="row g-3">` / `card.card-body` для панели фильтров.

#### 4. Карточки-контейнеры

```css
.XXX-card {
    border: none;
    border-radius: 10px;
    overflow: hidden;
    box-shadow: 0 2px 8px rgba(0,0,0,0.07);
    margin-bottom: 20px;
}
```

**Запрещено:** стандартный Bootstrap `card` с `border` и `card-header bg-*`.

#### 5. Таблицы

```css
.XXX-table { width: 100%; border-collapse: collapse; font-size: 0.88rem; }
.XXX-table th {
    padding: 9px 14px;
    font-size: 0.72rem;
    text-transform: uppercase;
    letter-spacing: 0.35px;
    color: #9aa0ac;
    font-weight: 600;
    border-bottom: 2px solid #f0f0f0;
    background: #fff;
    white-space: nowrap;
}
.XXX-table td { padding: 10px 14px; vertical-align: middle; border-bottom: 1px solid #f5f5f5; }
.XXX-table tbody tr:hover td { background: #f0f7ff; }
```

**Запрещено:** `table-striped`, `table-bordered`, `table-dark`, `table-primary` на строках.

#### 6. Бейджи статусов / счётчиков

Использовать кастомные pill-бейджи с цветовым кодированием, не Bootstrap `badge bg-*`:

```css
/* Светлый бейдж на градиентном фоне (заголовки орг) */
.cnt-badge { background: rgba(255,255,255,0.25); color: #fff; ... }

/* Тёмный бейдж на белом фоне */
.cnt-badge-dark { background: #e3eef8; color: #1a5276; ... }
```

Для статусных бейджей задавать явные цвета по смыслу:
- 🔴 Просрочено / Ошибка: `background: #fde8e8; color: #c0392b;`
- 🟡 Скоро / Предупреждение: `background: #fff3cd; color: #856404;`
- 🟢 OK / Активен: `background: #d1f5d3; color: #1e7e34;`
- ⚪ Нет данных / Неактивен: `background: #f0f0f0; color: #999;`

#### 7. Сворачиваемые деревья

Использовать кастомный JavaScript `toggleBlock()` / `toggleSizBlock()`, **не** Bootstrap collapse (`data-bs-toggle="collapse"`):

```javascript
function toggleBlock(headerEl, contentId) {
    const content = document.getElementById(contentId);
    if (!content) return;
    const isCollapsed = content.classList.contains('collapsed');
    if (isCollapsed) {
        content.style.maxHeight = '9999px';
        content.classList.remove('collapsed');
        headerEl.classList.remove('collapsed');
    } else {
        content.style.maxHeight = content.scrollHeight + 'px';
        content.getBoundingClientRect(); // reflow
        content.style.maxHeight = '0';
        content.classList.add('collapsed');
        headerEl.classList.add('collapsed');
    }
}
```

CSS анимация:
```css
.collapsible { overflow: hidden; transition: max-height 0.25s ease, opacity 0.2s ease; }
.collapsible.collapsed { max-height: 0 !important; opacity: 0; }
```

#### 8. Иерархия дерева (Орг → Подразделение → Отдел → Элемент)

| Уровень | Фон | Отступ слева |
|---------|-----|-------------|
| Организация | Градиент `#2c3e50 → #3498db`, белый текст | 18px |
| Подразделение | `#f8f9fa`, тёмный текст `#2c3e50` | 28px |
| Отдел | `#fafafa`, текст `#495057` | 44px |
| Элемент (строка) | `#fff`, hover `#f0f7ff` | 60px |

#### 9. Пагинация

```css
.XXX-pagination { display: flex; justify-content: center; gap: 4px; margin-top: 20px; }
.XXX-pagination a, .XXX-pagination span {
    display: inline-flex; align-items: center; justify-content: center;
    min-width: 36px; height: 36px; padding: 0 10px;
    border: 1px solid #dee2e6; border-radius: 6px;
    font-size: 0.85rem; text-decoration: none; color: #495057; background: #fff;
}
.XXX-pagination .current { background: #3498db; border-color: #3498db; color: #fff; font-weight: 600; }
```

**Запрещено:** Bootstrap `pagination` с `page-item` / `page-link`.

#### 10. Вкладки

Кастомные кнопки-вкладки, не Bootstrap nav-tabs:

```css
.XXX-tab-btn { padding: 8px 18px; font-weight: 600; color: #6c757d; background: #f8f9fa;
    border: 1px solid #dee2e6; border-bottom: none; border-radius: 8px 8px 0 0; }
.XXX-tab-btn.active {
    background: linear-gradient(135deg, #2c3e50 0%, #3498db 100%);
    color: #fff; border-color: #3498db;
}
```

#### 11. Мобильная адаптация — обязательно

**КРИТИЧНО:** При переработке любой страницы ОБЯЗАТЕЛЬНО проверить и сохранить адаптивность. Каждый шаблон должен содержать блок `@media (max-width: 767px)` с полным набором правил ниже.

##### Чеклист адаптивности (проверять при каждом изменении шаблона)

- [ ] Topbar/actionbar/treebar стекаются вертикально
- [ ] Кнопки в панелях растягиваются на всю ширину (`width: 100%`)
- [ ] Поля ввода (`input`, `select`) растягиваются на всю ширину
- [ ] Таблицы: либо карточный паттерн (`display: block`), либо горизонтальный скролл с уменьшенными отступами
- [ ] Дерево: отступы уровней уменьшены примерно вдвое
- [ ] `margin-left: auto` убирается у счётчиков/кнопок (иначе прилипают к правому краю)
- [ ] Вкладки (`tab-btn`) переносятся (`flex-wrap: wrap`)

##### Паттерн А — обычная таблица (списки, фильтры)

Применяется для: `/hiring/list/`, `/siz/mass-generation/` (вкладка «Массовая генерация»)

Требуется **добавить `data-label`** ко всем `<td>` в HTML:
```html
<td data-label="Сотрудник">{{ emp.full_name }}</td>
<td data-label="Должность">{{ emp.position }}</td>
```

CSS:
```css
@media (max-width: 767px) {
    .XXX-topbar { flex-direction: column; align-items: stretch; gap: 10px; }
    .XXX-topbar input, .XXX-topbar select { width: 100%; box-sizing: border-box; }

    .XXX-table thead { display: none; }
    .XXX-table tbody tr { display: block; border-bottom: 1px solid #eee; padding: 8px 0; }
    .XXX-table td {
        display: flex; justify-content: space-between; align-items: center;
        padding: 4px 12px; border: none; font-size: 0.82rem;
    }
    .XXX-table td::before {
        content: attr(data-label);
        font-size: 0.7rem; color: #999; font-weight: 600;
        margin-right: 8px; flex-shrink: 0;
    }
    /* Ячейки с кнопками — без метки, выровнять вправо */
    .XXX-table td.td-acts { justify-content: flex-end; }
    .XXX-table td.td-acts::before { content: none; }
}
```

##### Паттерн Б — tree-таблица с toggle (дерево Орг→Под→Отдел→Сотрудник)

Применяется для: `/ot-card/mass-generation/`, `/documents/instruction-journal/`

**Нельзя делать `display: block` на строках** — ломается логика `tree_view.js` (скрытие/показ дочерних строк по `data-parent-id`). Вместо этого: скрывать второстепенные колонки + уменьшать отступы + горизонтальный скролл как fallback.

```css
@media (max-width: 767px) {
    /* Панели управления */
    .XXX-topbar { flex-direction: column; align-items: stretch; gap: 10px; }
    .XXX-topbar input, .XXX-topbar select { width: 100%; box-sizing: border-box; }
    .XXX-actionbar { flex-direction: column; align-items: stretch; gap: 6px; }
    .XXX-actionbar .btn { width: 100%; text-align: center; }
    .XXX-selected-info { margin-left: 0; text-align: center; }
    .XXX-treebar { flex-direction: column; align-items: stretch; gap: 6px; }
    .XXX-treebar input[type="text"] { max-width: 100%; width: 100%; }
    .XXX-treebar .btn { width: 100%; }

    /* Таблица: скрыть второстепенные колонки (оставить чекбокс + имя) */
    #result_list th:nth-child(3), #result_list td:nth-child(3),
    #result_list th:nth-child(4), #result_list td:nth-child(4) { display: none; }

    /* Уменьшить шрифт и padding */
    #result_list { font-size: 0.82rem; }
    #result_list th, #result_list td { padding: 6px 8px; }

    /* Уменьшить отступы уровней дерева (~вдвое от desktop) */
    .tree-row[data-level="0"] .field-name { padding-left: 4px; }
    .tree-row[data-level="1"] .field-name { padding-left: 14px; }
    .tree-row[data-level="2"] .field-name { padding-left: 24px; }
    .tree-row[data-level="3"] .field-name { padding-left: 34px; }

    /* Кнопки внутри строк дерева — компактнее */
    .group-generate-btn { font-size: 0.68rem; padding: 1px 5px; }
    .tree-row[data-node-id] .btn { font-size: 0.7rem; padding: 2px 6px; }
}
```

##### Паттерн В — flexbox-дерево (без таблицы)

Применяется для: `/siz/mass-generation/` (вкладка «По сотрудникам»), иерархические карточки

```css
@media (max-width: 767px) {
    /* Уменьшить отступы заголовков уровней */
    .org-header { padding: 10px 14px; }
    .sub-header { padding: 8px 14px 8px 18px; }
    .dept-header { padding: 6px 14px 6px 24px; }
    /* Строки элементов — уменьшить отступ и разрешить перенос */
    .emp-row { padding-left: 28px; flex-wrap: wrap; gap: 4px; }
    /* Вкладки переносятся */
    .XXX-tabs { flex-wrap: wrap; }
    .XXX-tab-btn { flex: 1; text-align: center; }
}
```

##### Правило единой карточки для панелей (actionbar + treebar + table)

Когда три блока стоят друг за другом — обернуть в единый контейнер:
```html
<div class="XXX-card">          <!-- border-radius: 10px; overflow: hidden; box-shadow -->
    <div class="XXX-actionbar"> <!-- border-bottom: 1px solid #dee2e6 -->
    <div class="XXX-treebar">   <!-- border-bottom: 1px solid #dee2e6 -->
    <div class="XXX-tree-wrap"> <!-- просто overflow: hidden -->
</div>
```
Это гарантирует скругление углов у шапки таблицы и нижнего края — без отдельных `border-radius` на каждом блоке.

### Размещение стилей

Все кастомные стили размещать в `{% block extra_css %}<style>...</style>{% endblock %}` внутри шаблона. Общие переиспользуемые стили можно выносить в `static/css/`.

### Чего НЕ делать

- ❌ Не использовать Bootstrap 4 классы (`mr-`, `ml-`, `float-left` и т.д.) — только Bootstrap 5
- ❌ Не использовать `card-header bg-primary/bg-dark/bg-success` — только градиент
- ❌ Не использовать FontAwesome или любые иконочные шрифты
- ❌ Не использовать `table-striped`, `table-bordered`, `table-hover` из Bootstrap для основных таблиц
- ❌ Не использовать Bootstrap `pagination` компонент
- ❌ Не использовать Bootstrap `nav-tabs` / `nav-pills` для вкладок
- ❌ Не использовать inline `style="color: blue"` для брендовых цветов — только CSS-классы
- ❌ **Не удалять и не урезать блок `@media (max-width: 767px)`** при переработке шаблона
- ❌ **Не делать `display: block` на строках tree-таблицы** (с `data-parent-id` / `tree_view.js`) — ломает логику сворачивания дерева
- ❌ **Не оставлять `margin-left: auto`** у элементов внутри flex-контейнера на мобильном — прижимает к правому краю
- ❌ **Не забывать `data-label`** на `<td>` при использовании паттерна А (иначе `::before` покажет пустую строку)
