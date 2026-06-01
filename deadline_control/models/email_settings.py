# deadline_control/models/email_settings.py

from django.db import models
from django.core.validators import MinValueValidator, MaxValueValidator, validate_email
from django.core.exceptions import ValidationError
from django_ckeditor_5.fields import CKEditor5Field
import re
import socket
import logging

# Получаем logger
logger = logging.getLogger(__name__)

# ==========================================
# ВАЖНО: Патч для решения проблемы с IDNA
# ==========================================
# Переопределяем socket.getfqdn() глобально, чтобы избежать ошибки
# при некорректном имени компьютера (например, с двойными точками)
_original_getfqdn = socket.getfqdn

def _patched_getfqdn(host=''):
    """
    Безопасная версия socket.getfqdn() которая возвращает 'localhost'
    при некорректном имени компьютера (с двойными точками, точками в конце и т.д.)

    Args:
        host: опциональный аргумент - имя хоста (для совместимости с оригинальной функцией)
    """
    try:
        # Вызываем оригинальную функцию с аргументом или без
        fqdn = _original_getfqdn(host) if host else _original_getfqdn()
        # Проверяем на некорректные символы
        if '..' in fqdn or fqdn.endswith('.') or fqdn.startswith('.'):
            logger.warning(f"Некорректный FQDN компьютера: '{fqdn}'. Используем 'localhost'")
            return 'localhost'
        # Пытаемся закодировать в IDNA
        fqdn.encode('idna')
        return fqdn
    except Exception as e:
        logger.warning(f"Ошибка при получении FQDN: {str(e)}. Используем 'localhost'")
        return 'localhost'

# Применяем патч глобально
socket.getfqdn = _patched_getfqdn
# ==========================================


class EmailSettings(models.Model):
    """
    📧 Настройки SMTP для отправки email-уведомлений.

    Позволяет настроить параметры подключения к почтовому серверу
    для отправки уведомлений о медосмотрах и других событиях.
    """

    organization = models.OneToOneField(
        'directory.Organization',
        on_delete=models.CASCADE,
        verbose_name="Организация",
        help_text="Организация, для которой применяются настройки email",
        related_name='email_settings'
    )

    # SMTP настройки
    email_backend = models.CharField(
        max_length=255,
        default='django.core.mail.backends.smtp.EmailBackend',
        verbose_name="Email Backend",
        help_text="Бэкенд для отправки email (обычно не требует изменения)"
    )

    email_host = models.CharField(
        max_length=255,
        verbose_name="SMTP сервер",
        help_text="Адрес SMTP сервера (например: smtp.gmail.com, smtp.yandex.ru)",
        blank=True,
        default=''
    )

    email_port = models.PositiveIntegerField(
        default=587,
        validators=[MinValueValidator(1), MaxValueValidator(65535)],
        verbose_name="SMTP порт",
        help_text="Порт SMTP сервера (587 для TLS, 465 для SSL, 25 для обычного)"
    )

    email_use_tls = models.BooleanField(
        default=True,
        verbose_name="Использовать TLS",
        help_text="Использовать TLS шифрование (рекомендуется для порта 587)"
    )

    email_use_ssl = models.BooleanField(
        default=False,
        verbose_name="Использовать SSL",
        help_text="Использовать SSL шифрование (для порта 465)"
    )

    email_host_user = models.CharField(
        max_length=255,
        verbose_name="Email пользователь",
        help_text="Email адрес для отправки (логин на SMTP сервере)",
        blank=True,
        default=''
    )

    email_host_password = models.CharField(
        max_length=255,
        verbose_name="Пароль",
        help_text="Пароль от email (для Gmail - пароль приложения)",
        blank=True,
        default=''
    )

    default_from_email = models.EmailField(
        verbose_name="Email отправителя",
        help_text="Email адрес, который будет указан в поле 'От кого'",
        blank=True,
        default=''
    )

    # Настройки уведомлений
    is_active = models.BooleanField(
        default=True,
        verbose_name="Активно",
        help_text="Включить отправку email для этой организации"
    )

    test_mode = models.BooleanField(
        default=False,
        verbose_name="Тестовый режим",
        help_text="Все письма будут отправляться только на тестовый адрес, а не реальным получателям"
    )

    test_email = models.EmailField(
        verbose_name="Email для тестовых рассылок",
        help_text="Адрес, на который уходят все письма в тестовом режиме",
        blank=True,
        default=''
    )

    recipient_emails = models.TextField(
        verbose_name="Email получателей (общие)",
        help_text="Email адреса для общих уведомлений (медосмотры и т.д.). По одному на строку.",
        blank=True,
        default=''
    )

    instruction_journal_recipients = models.TextField(
        verbose_name="Email получателей (журналы инструктажей)",
        help_text="Email адреса для рассылки образцов журналов повторных инструктажей. "
                  "По одному на строку. Если пусто, используются ТОЛЬКО получатели из подразделений "
                  "(SubdivisionEmail + ответственные за ОТ), БЕЗ общих получателей.",
        blank=True,
        default=''
    )

    # Настройки массовой рассылки (Rate Limiting & Retry)
    email_delay_seconds = models.DecimalField(
        max_digits=4,
        decimal_places=1,
        default=1.0,
        validators=[MinValueValidator(0.0), MaxValueValidator(60.0)],
        verbose_name="Задержка между письмами (сек)",
        help_text="Пауза между отправкой писем при массовой рассылке. "
                  "Защита от блокировки SMTP провайдером. "
                  "Gmail/Yandex: рекомендуется 1-2 сек."
    )

    max_retry_attempts = models.PositiveSmallIntegerField(
        default=3,
        validators=[MinValueValidator(0), MaxValueValidator(10)],
        verbose_name="Макс. попыток повтора",
        help_text="Количество попыток повторной отправки при временных ошибках. "
                  "0 = без повторов, рекомендуется 3."
    )

    connection_timeout = models.PositiveSmallIntegerField(
        default=30,
        validators=[MinValueValidator(5), MaxValueValidator(300)],
        verbose_name="Таймаут соединения (сек)",
        help_text="Максимальное время ожидания ответа от SMTP сервера. "
                  "Рекомендуется 30 секунд."
    )

    # Метаданные
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Дата создания"
    )

    updated_at = models.DateTimeField(
        auto_now=True,
        verbose_name="Дата изменения"
    )

    class Meta:
        verbose_name = "⚙️ Настройки Email (SMTP)"
        verbose_name_plural = "⚙️ Настройки Email (SMTP)"
        ordering = ['organization__short_name_ru']

    def __str__(self):
        return f"Email настройки - {self.organization.short_name_ru}"

    def clean(self):
        """Валидация настроек"""
        super().clean()

        # Автоматически очищаем поля от лишних пробелов
        if self.email_host:
            self.email_host = self.email_host.strip()
        if self.email_host_user:
            self.email_host_user = self.email_host_user.strip()
        if self.default_from_email:
            self.default_from_email = self.default_from_email.strip()

        # Проверка: TLS и SSL не могут быть включены одновременно
        if self.email_use_tls and self.email_use_ssl:
            raise ValidationError({
                'email_use_tls': 'TLS и SSL не могут быть включены одновременно',
                'email_use_ssl': 'TLS и SSL не могут быть включены одновременно',
            })

        # Тестовый режим: требуем тестовый email
        if self.test_mode and not self.test_email:
            raise ValidationError({
                'test_email': 'Укажите email для тестовых рассылок'
            })

        # Если указан хост, требуем заполнить пользователя
        if self.email_host and not self.email_host_user:
            raise ValidationError({
                'email_host_user': 'Укажите email пользователя для SMTP сервера'
            })

        # Если указан пользователь, требуем пароль
        if self.email_host_user and not self.email_host_password:
            raise ValidationError({
                'email_host_password': 'Укажите пароль для SMTP сервера'
            })

        # Валидация SMTP хоста (проверка IDNA)
        if self.email_host:
            self._validate_hostname(self.email_host, 'email_host')

        # Валидация email адресов
        if self.email_host_user:
            self._validate_email_field(self.email_host_user, 'email_host_user')

        if self.default_from_email:
            self._validate_email_field(self.default_from_email, 'default_from_email')

        # Валидация получателей
        if self.recipient_emails:
            errors = self._validate_recipients()
            if errors:
                raise ValidationError({'recipient_emails': errors})

    def _validate_hostname(self, hostname, field_name):
        """
        Валидация hostname для SMTP на предмет IDNA ошибок
        """
        if not hostname:
            return

        # Проверка на двойные точки
        if '..' in hostname:
            raise ValidationError({
                field_name: f'Неверный формат hostname: найдены двойные точки (..) в "{hostname}"'
            })

        # Проверка на точку в начале/конце
        if hostname.startswith('.') or hostname.endswith('.'):
            raise ValidationError({
                field_name: f'Неверный формат hostname: не может начинаться или заканчиваться точкой "{hostname}"'
            })

        # Проверка на пустые метки (label)
        parts = hostname.split('.')
        for part in parts:
            if not part:
                raise ValidationError({
                    field_name: f'Неверный формат hostname: пустая метка в "{hostname}"'
                })

        # Попытка IDNA кодирования
        try:
            hostname.encode('idna')
        except Exception as e:
            raise ValidationError({
                field_name: f'Ошибка IDNA кодирования hostname "{hostname}": {str(e)}'
            })

    def _validate_email_field(self, email, field_name):
        """
        Валидация email адреса
        """
        if not email:
            return

        try:
            validate_email(email)
        except ValidationError:
            raise ValidationError({
                field_name: f'Неверный формат email адреса: "{email}"'
            })

        # Дополнительная проверка на двойные точки
        if '..' in email:
            raise ValidationError({
                field_name: f'Неверный формат email: найдены двойные точки (..) в "{email}"'
            })

        # Проверка домена на IDNA
        if '@' in email:
            _, domain = email.rsplit('@', 1)
            try:
                domain.encode('idna')
            except Exception as e:
                raise ValidationError({
                    field_name: f'Ошибка IDNA кодирования домена в "{email}": {str(e)}'
                })

    def _validate_recipients(self):
        """
        Валидация списка получателей
        Возвращает список ошибок или пустой список, если все ОК
        """
        errors = []
        recipient_list = self.get_recipient_list()

        for i, email in enumerate(recipient_list, 1):
            # Проверка на пробелы
            if email != email.strip():
                errors.append(f'Получатель #{i}: содержит пробелы в начале/конце: "{email}"')
                continue

            # Проверка на двойные точки
            if '..' in email:
                errors.append(f'Получатель #{i}: содержит двойные точки (..): "{email}"')
                continue

            # Проверка формата email
            try:
                validate_email(email)
            except ValidationError:
                errors.append(f'Получатель #{i}: неверный формат email: "{email}"')
                continue

            # Проверка IDNA кодирования домена
            if '@' in email:
                _, domain = email.rsplit('@', 1)
                try:
                    domain.encode('idna')
                except Exception as e:
                    errors.append(f'Получатель #{i}: ошибка IDNA кодирования в "{email}": {str(e)}')

        return errors

    def get_recipient_list(self):
        """
        Возвращает список email адресов получателей (общие уведомления).
        В тестовом режиме возвращает только тестовый адрес.
        """
        if self.test_mode and self.test_email:
            return [self.test_email]

        if not self.recipient_emails:
            return []

        # Разделяем по строкам и удаляем пробелы
        emails = [
            email.strip()
            for email in self.recipient_emails.strip().split('\n')
            if email.strip()
        ]
        return emails

    def get_instruction_journal_recipients(self):
        """
        Возвращает список email адресов для рассылки журналов инструктажей.

        Логика:
        1. Если instruction_journal_recipients заполнен - используем его
        2. Если пуст - возвращаем пустой список []

        В этом случае система будет использовать ТОЛЬКО получателей из:
        - SubdivisionEmail (email подразделений)
        - Employee.email (ответственные за охрану труда)

        Это предотвращает массовую отправку общим получателям (HR, директор)
        при рассылке образцов для множества подразделений.
        """
        if self.test_mode and self.test_email:
            return [self.test_email]

        # Если поле заполнено - используем его
        if self.instruction_journal_recipients and self.instruction_journal_recipients.strip():
            emails = [
                email.strip()
                for email in self.instruction_journal_recipients.strip().split('\n')
                if email.strip()
            ]
            return emails

        # Если пусто - возвращаем пустой список (БЕЗ fallback на общих получателей)
        return []

    def get_connection(self):
        """
        Возвращает Django email connection с настройками этой организации.
        Используется для отправки email с кастомными SMTP параметрами.

        Примечание: socket.getfqdn() уже пропатчен глобально в начале модуля
        для обхода проблемы с некорректным FQDN компьютера.
        """
        from django.core.mail import get_connection

        if not self.is_active or not self.email_host:
            return None

        # Создаём подключение
        connection = get_connection(
            backend=self.email_backend,
            host=self.email_host,
            port=self.email_port,
            username=self.email_host_user,
            password=self.email_host_password,
            use_tls=self.email_use_tls,
            use_ssl=self.email_use_ssl,
            fail_silently=False,
            timeout=30,  # Таймаут 30 секунд
        )

        return connection

    def send_email_safe(self, subject, message, recipient_list, html_message=None):
        """
        Безопасная отправка email с валидацией и обработкой ошибок.

        Args:
            subject (str): Тема письма
            message (str): Текст письма (plain text)
            recipient_list (list): Список email получателей
            html_message (str, optional): HTML версия письма

        Returns:
            tuple: (success: bool, error_message: str or None)

        Example:
            success, error = settings.send_email_safe(
                subject="Тест",
                message="Текст письма",
                recipient_list=["user@example.com"]
            )
            if not success:
                print(f"Ошибка: {error}")
        """
        from django.core.mail import send_mail

        # Проверка активности
        if not self.is_active:
            return False, "Email настройки отключены (is_active=False)"

        if not self.email_host:
            return False, "SMTP сервер не настроен (email_host пустой)"

        # Валидация получателей
        if not recipient_list:
            return False, "Список получателей пустой"

        # Проверка каждого получателя на IDNA
        for i, email in enumerate(recipient_list, 1):
            email = email.strip()

            # Проверка базового формата
            try:
                validate_email(email)
            except ValidationError as e:
                return False, f"Получатель #{i} '{email}': неверный формат email: {str(e)}"

            # Проверка IDNA кодирования
            if '@' in email:
                _, domain = email.rsplit('@', 1)
                try:
                    domain.encode('idna')
                except Exception as e:
                    return False, f"Получатель #{i} '{email}': ошибка IDNA кодирования домена: {str(e)}"

        # Получаем подключение
        try:
            connection = self.get_connection()
            if not connection:
                return False, "Не удалось создать SMTP подключение"
        except Exception as e:
            return False, f"Ошибка создания SMTP подключения: {str(e)}"

        # Отправка
        try:
            from_email = self.default_from_email or self.email_host_user

            effective_subject = f'[ТЕСТ] {subject}' if self.test_mode else subject

            send_mail(
                subject=effective_subject,
                message=message,
                from_email=from_email,
                recipient_list=recipient_list,
                connection=connection,
                html_message=html_message,
                fail_silently=False,
            )
            return True, None
        except Exception as e:
            return False, f"Ошибка отправки email: {str(e)}"

    def get_email_template(self, template_code):
        """
        Возвращает EmailTemplate для данной организации и типа шаблона.

        Каскадный поиск (по образцу DocumentTemplate.get_document_template):
        1. Ищем активный шаблон для организации (organization=self.organization)
        2. Если не найден - ищем эталонный шаблон (organization=NULL, is_default=True)
        3. Если не найден - возвращаем None

        Args:
            template_code (str): Код типа шаблона (например: 'medical_examination')

        Returns:
            tuple: (subject, body) или None если шаблон не настроен
        """
        from .email_template import EmailTemplate, EmailTemplateType

        # Получаем тип шаблона
        try:
            template_type = EmailTemplateType.objects.get(code=template_code, is_active=True)
        except EmailTemplateType.DoesNotExist:
            return None

        # Получаем все активные шаблоны данного типа
        templates = EmailTemplate.objects.filter(
            template_type=template_type,
            is_active=True
        )

        # Шаг 1: Ищем шаблон для организации
        org_template = templates.filter(organization=self.organization).first()
        if org_template:
            return (org_template.subject, org_template.body)

        # Шаг 2: Ищем эталонный шаблон
        default_template = templates.filter(
            organization__isnull=True,
            is_default=True
        ).first()
        if default_template:
            return (default_template.subject, default_template.body)

        # Шаг 3: Не найден ни организационный, ни эталонный
        return None

    @classmethod
    def get_settings(cls, organization):
        """
        Возвращает настройки email для указанной организации.
        Создает новые настройки с дефолтными значениями, если их еще нет.
        """
        settings, created = cls.objects.get_or_create(
            organization=organization,
            defaults={
                'is_active': False,  # По умолчанию выключено до настройки
                'email_backend': 'django.core.mail.backends.smtp.EmailBackend',
                'email_port': 587,
                'email_use_tls': True,
                'email_use_ssl': False,
                'email_delay_seconds': 1.0,  # 1 секунда между письмами
                'max_retry_attempts': 3,  # 3 попытки повтора
                'connection_timeout': 30,  # 30 секунд таймаут
            }
        )
        return settings
