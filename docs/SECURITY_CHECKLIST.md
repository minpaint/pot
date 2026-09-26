# 🔐 Чеклист безопасности OT_online

Практический чеклист для ревью кода и периодических проверок. Составлен по факту устройства
проекта (Django 5.0, монолитное приложение `directory`, продакшен за CWP-прокси). Не общая
теория — только то, что применимо здесь и сейчас.

**Как использовать:** при код-ревью или перед релизом пройтись по разделам, которые затрагивает
диф. Полный прогон — раз в квартал или перед крупным релизом.

---

## 0. Базовые принципы

- **Валидация на границах** — пользовательский ввод (формы, admin-импорт, GET/POST), внешние
  файлы. Внутренним данным (уже провалидированным моделью) — доверяем повторно не проверяем.
- **Экранирование вывода** — Django-шаблоны экранируют по умолчанию (`{{ }}`), но `|safe` и
  `mark_safe()` — точки риска. Любое использование — повод присмотреться отдельно.
- **CSRF на каждой POST-форме** — `{% csrf_token %}` обязателен. Особое внимание — AJAX-запросы
  (`fetch`/`$.ajax`), которым нужно вручную передавать `X-CSRFToken`.
- **Доступ только через организацию (multi-tenancy)** — почти все модели содержат `organization`
  FK. Любая `UpdateView`/`DeleteView`/AJAX-эндпоинт, принимающий `pk`/`id` из URL, обязан
  фильтровать по организациям, доступным пользователю (см. `AccessControlObjectMixin`,
  `directory/mixins.py`), иначе — IDOR между организациями.
- **DEBUG всегда False в проде** — жёстко зашито в `settings.py`/`settings_prod.py`. Проверяется
  `utility_scripts/check_debug_status.py` перед деплоем.
- **Секреты — только в `.env`** — `DJANGO_SECRET_KEY` и т.п. никогда не коммитить.

### Быстрые grep-проверки
```bash
grep -rn "|safe\|mark_safe(" templates/ directory/templates/ directory/**/*.py
grep -rn "csrf_exempt" directory/
grep -rln "class.*View" directory/views/ | xargs grep -L "AccessControl\|organization"
```

---

## 1. Аутентификация и сессии

**Текущее состояние:**
- Login/logout/reset-password — стандартные Django `auth_views` (`directory/urls.py`), пароли
  хешируются штатным Django hasher'ом (PBKDF2), кастомного хеширования нет.
- Регистрация (`UserRegistrationView`, `directory/views/auth.py`) использует
  `sensitive_post_parameters()` — пароли не попадают в error-репорты.
- **2FA не реализована.**
- **Rate-limiting на login/reset отсутствует на уровне Django** (нет `django-axes`/
  `django-ratelimit`). По CLAUDE.md брутфорс-защита ожидается на уровне CWP-прокси —
  **это нужно явно подтвердить**, иначе это дыра, а не «защищено на другом уровне».
- `SESSION_COOKIE_SECURE = True`, `CSRF_COOKIE_SECURE = True` (settings_prod.py) — ок.
- `SESSION_COOKIE_HTTPONLY` и `SESSION_COOKIE_SAMESITE` — используются дефолты Django
  (`True` / `Lax`), явно нигде не переопределены. Стоит зафиксировать явно в settings_prod.py,
  чтобы не зависеть от дефолтов будущих версий Django.

**Что проверять:**
- [ ] Любой новый auth-эндпоинт: не открыт ли случайно на `exam.*` поддомене
      (`ExamSubdomainMiddleware` должен блокировать всё, кроме quiz-URL).
- [ ] Сообщения об ошибке логина не должны различать «неверный email» / «неверный пароль»
      (проверить текущий `LoginView` — используется ли стандартный generic-текст Django).
- [ ] Действительно ли CWP закрывает brute-force по `/login/`, `/password_reset/` — если нет,
      завести `django-axes` или rate-limit на уровне Django.

---

## 2. Изоляция exam-поддомена

**Реализовано** (`directory/middleware/exam_subdomain.py`):
- На хостах `exam.*` доступны только quiz-URL; всё остальное блокируется.
- Доступ — только через `QuizAccessToken`, флаг в сессии `quiz_token_mode`.
- Добавляются CSP / X-Frame-Options / Cache-Control; блокировки логируются в `exam_security`.
- `AntiIndexationMiddleware` — X-Robots-Tag, кастомный robots.txt, 410 для мусорных query-параметров.

**Что проверять при любых правках quiz/exam:**
- [ ] Новый quiz-URL добавлен в allowlist `ExamSubdomainMiddleware`, а не оставлен «работать
      по умолчанию».
- [ ] Middleware стоит достаточно рано в `MIDDLEWARE` (до `AuthenticationMiddleware`), порядок
      не нарушен новыми правками `settings.py`.
- [ ] Токен (`QuizAccessToken`) проверяется на expiry и лимит попыток при каждом обращении,
      а не только при первом входе.

---

## 3. Загрузка файлов

**Известные точки:**
| Поле | Валидация |
|---|---|
| `EmployeeMedicalExamination.medical_certificate` | `FileExtensionValidator(['pdf','jpg','jpeg','png'])` ✅ |
| `Question.image` (quiz) | `ImageField` — Pillow проверяет, что это реально изображение ✅ |
| Формы импорта (medical/quiz/registry/global) | Расширение (xls/xlsx/csv) + лимит размера (10–50 МБ) ✅ |
| `DocumentTemplate.template_file` | **Нет валидатора расширения/типа** — доступно только в admin суперпользователям, но всё равно стоит добавить `FileExtensionValidator(['docx'])`, чтобы исключить загрузку произвольного файла под видом шаблона |

**Общий пробел:** проверка везде идёт **по расширению**, не по реальному содержимому файла
(magic bytes / content-type). Для мест, куда могут попасть файлы от не-суперпользователей
(медицинские справки, вопросы квиза с картинками, если роль редактора шире, чем предполагается) —
стоит рассмотреть проверку сигнатуры файла, а не только `FileExtensionValidator`.

**Что проверять:**
- [ ] Любое новое `FileField`/`ImageField` — есть `FileExtensionValidator` + разумный размер
      (через `clean()` формы, Django сам не ограничивает размер файла).
- [ ] Хранение — не берём имя файла от пользователя напрямую в путь (Django `FileField` сам
      генерирует безопасный путь через `upload_to`, но кастомные `get_upload_path()` — проверять).

---

## 4. Генерация документов (docxtpl) и раздача media

**Реализовано корректно:**
- Путь сохранения (`generated_documents/%Y/%m/%d/`) строится Django FileField по дате, не из
  пользовательского ввода — path traversal через `upload_to` исключён.
- Имя файла собирается программно (`f"{doc_type_name}_{employee_initials}.docx"`,
  `directory/document_generators/base.py`) — не берётся из запроса.
- Отдача сгенерированных/загруженных файлов идёт через `protected_media()`
  (`urls.py`) + `can_access_media()` (`directory/utils/media_access.py`), который **явно
  проверяет организацию-владельца документа** перед отдачей — это защита от IDOR/утечки
  персональных данных между организациями. Важно не терять этот паттерн при рефакторинге media-раздачи.

**Что проверять:**
- [ ] Любой новый генератор документов не собирает имя файла/путь из значений, которые могут
      содержать `/`, `..` (ФИО с экзотическими символами, названия должностей и т.п. —
      теоретический риск, но дешёво проверить один раз через `slugify`/санитайзер).
- [ ] Новые media-эндпоинты обязательно идут через `can_access_media()`, а не напрямую отдают
      `MEDIA_URL` без проверки прав.

---

## 5. Настройки production (`settings_prod.py`)

| Параметр | Статус |
|---|---|
| `DEBUG` | `False`, жёстко ✅ |
| `ALLOWED_HOSTS` | `pot.by,www.pot.by` (+ должны быть внутренние IP CWP/Django из архитектуры) |
| `CSRF_TRUSTED_ORIGINS` | `https://pot.by,https://www.pot.by` ✅ |
| `SECURE_SSL_REDIRECT` | `False` — редирект делегирован на CWP-прокси (осознанно, см. `docs/CWP_ARCHITECTURE.md`) |
| `SESSION_COOKIE_SECURE` / `CSRF_COOKIE_SECURE` | `True` ✅ |
| `SECURE_PROXY_SSL_HEADER` | настроен на `X-Forwarded-Proto` — доверие CWP-прокси корректно, **но убедиться, что порт 8020 Django-сервера действительно не достижим напрямую извне** (иначе заголовок можно подделать в обход CWP) |
| HSTS (`SECURE_HSTS_SECONDS` и т.д.) | не задан в Django — по документации выставляется на CWP. **Стоит физически проверить `curl -I https://pot.by`**, что заголовок `Strict-Transport-Security` реально приходит, а не только предполагается |

**Что проверять раз в релиз:**
- [ ] `venv/bin/python utility_scripts/check_debug_status.py` перед каждым деплоем.
- [ ] `curl -I https://pot.by` — реально ли отдаются HSTS/X-Frame-Options/CSP с CWP, а не
      только «должны быть по документации».
- [ ] `ALLOWED_HOSTS` не содержит `*` и не расширен «на всякий случай».

---

## 6. Admin-панель

- Стандартный `/admin/`, URL не переименован/не скрыт, IP-ограничение — только на уровне CWP
  (не в Django-коде). Если CWP когда-либо отключат/переконфигурируют — Django-админка окажется
  полностью открытой без доп. защиты (кроме логина/пароля).
- `django-import-export` активно используется (оборудование, медосмотры, глобальный импорт) —
  импорт CSV/XLSX идёт через `dry_run=True` предпросмотр перед реальным импортом ✅. Доступно
  только персоналу с правами в admin — приемлемо, но при добавлении новых Resource-классов
  проверять, что импорт не даёт возможность мгновенно применить изменения без предпросмотра.

**Что проверять:**
- [ ] Каждый новый `ModelAdmin` не открывает `list_editable`/`actions` на поля, которые должны
      быть защищены (например, `is_superuser`, `is_staff`, флаги ролей).
- [ ] Новые Import/Export Resource-классы сохраняют `dry_run`-предпросмотр, а не сразу пишут в БД.

---

## 7. IDOR / контроль доступа по организациям

Архитектура multi-tenant: почти каждая модель имеет `organization` FK, доступ пользователя к
организациям кешируется в `AccessCacheMiddleware`. Это главный вектор риска в проекте —
**любой забытый org-фильтр = утечка данных между организациями-клиентами.**

**Что проверять для каждого нового/изменённого view:**
- [ ] `UpdateView`/`DeleteView`/`DetailView` с `pk`/`id` из URL — фильтрует queryset по
      организациям, доступным `request.user` (через `AccessControlObjectMixin` или
      эквивалентный паттерн из `directory/mixins.py`), а не просто `Model.objects.get(pk=...)`.
- [ ] AJAX/autocomplete-эндпоинты (`directory/autocomplete_views.py`) — форвардные поля
      (forward fields) не позволяют затребовать данные чужой организации через подмену параметра.
- [ ] Любая ссылка на генерацию/скачивание документа проверяет владельца через
      `can_access_media()` (см. §4), а не только факт аутентификации.

---

## 8. API / внешние интеграции

- **DRF не используется** — подтверждено (grep по `rest_framework` пуст). Всё взаимодействие —
  традиционные Django views + AJAX + `django-autocomplete-light`.
- Если в будущем появится REST API — заново применить сюда принципы из общего OWASP-чеклиста
  (аутентификация токеном, ограничение полей на запись, не отдавать внутренние ID без нужды).

---

## 9. Логирование

- Ручной grep по `password|token|secret` рядом с `logger.*` в текущем коде утечек не выявил.
- `UserRegistrationView` использует `sensitive_post_parameters()` — пароли исключены из
  Django error-репортов/трейсбеков.
- **Правило на будущее:** новые `logger.info/error/warning` рядом с формами не должны включать
  `request.POST` целиком (там могут быть пароли/токены quiz-доступа) — логировать только
  конкретные безопасные поля.

---

## 10. Rate limiting / защита от перебора

- Внутри Django **нет** `django-ratelimit`/`django-axes` ни для login, ни для попыток прохождения
  квиза, ни для autocomplete-эндпоинтов. Вся защита от брутфорса/DoS вынесена на CWP-прокси
  (rate limiting по IP на фронтальном уровне).
- **Риск:** если CWP rate-limit настроен грубо (по IP) или временно отключат/перенастроят
  прокси — Django-уровень ничем не защищён от перебора `/login/`, `QuizAccessToken` (UUID,
  но всё равно) или медленного перебора паролей.

**Рекомендация (не блокирующая, на заметку):** для `LoginView` и `quiz/access/<uuid>/` имеет
смысл добавить `django-ratelimit` как defence-in-depth, не полагаясь только на CWP.

---

## Итоговая таблица «что делать при касании модуля»

| Трогаете... | Проверить |
|---|---|
| Любую форму с `<form method="post">` | `{% csrf_token %}` присутствует |
| Любой `UpdateView`/`DeleteView`/AJAX с `pk` из URL | org-фильтр доступа (§7) |
| Новое `FileField`/`ImageField` | `FileExtensionValidator` + лимит размера (§3) |
| `document_generators/*.py` | имя файла/путь не собирается из «сырых» пользовательских строк (§4) |
| `exam_subdomain.py` / quiz views | URL в allowlist middleware, токен проверяется на expiry (§2) |
| `settings_prod.py` | DEBUG/ALLOWED_HOSTS/cookie-флаги не ослаблены (§5) |
| Новый `ModelAdmin` / Import-Export Resource | нет privileged-полей в `list_editable`, `dry_run` сохранён (§6) |
| Логи (`logger.*`) | не пишем `request.POST` целиком, пароли/токены не попадают в лог (§9) |
