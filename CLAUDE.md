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

**Migration naming convention:** Use descriptive names with `--name` flag:
```bash
py manage.py makemigrations directory --name add_quiz_access_tokens
```

**Recent major migrations:**
- `0025_add_quiz_models` - Added entire quiz system
- `0029_*_quizaccesstoken` - Added token-based access
- `0034_remove_quiz_type` - Removed deprecated quiz_type field

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

**КРИТИЧНО:** На production сервере **НЕ ДЕЛАЮТСЯ коммиты кода!**

### Правильный workflow:

```
Development (локальный компьютер)
    ↓ git commit & push
GitHub Repository (origin)
    ↓ git pull
Production Server (192.168.37.10)
    ↓ deploy
pot.by (работающий сайт)
```

### Основные команды на production:

```bash
# Автоматический деплой (рекомендуется)
./deploy_from_git.sh

# Или вручную:
git fetch origin
git log HEAD..origin/main  # Посмотреть изменения
git pull origin main
python manage.py migrate --settings=settings_prod
python manage.py collectstatic --noinput --settings=settings_prod
./reload_gunicorn.sh
```

### Работа с локальными изменениями:

```bash
# Сохранить локальные изменения
git stash save "Production local changes"

# Получить обновления
git pull origin main

# Вернуть изменения (если нужно)
git stash pop
```

### Важные правила:

1. ❌ **НЕ коммитить** на production (кроме экстренных hotfix)
2. ❌ **НЕ делать** `git push --force`
3. ❌ **НЕ коммитить** .env файлы или секреты
4. ✅ Всегда проверять изменения перед pull: `git fetch && git log HEAD..origin/main`
5. ✅ Использовать `./deploy_from_git.sh` для автоматического деплоя
6. ✅ Делать backup базы перед большими обновлениями

### Скрипты управления:

- `./deploy_from_git.sh` - Полный автоматический деплой из Git
- `./start_gunicorn.sh` - Запуск Gunicorn с проверками
- `./reload_gunicorn.sh` - Graceful reload без даунтайма
- `./stop_gunicorn.sh` - Остановка Gunicorn
- `scripts/check_debug_status.py` - Проверка настроек безопасности

### Подробная документация:

- **GIT_QUICKSTART.md** - Быстрый старт по Git на production
- **docs/GIT_WORKFLOW.md** - Подробное руководство по Git workflow
- **docs/CWP_ARCHITECTURE.md** - Архитектура развёртывания
