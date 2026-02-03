"""
Модуль для массовой отправки email с лучшими практиками:
- Connection pooling (переиспользование SMTP соединения)
- Rate limiting (задержка между письмами)
- Retry механизм с экспоненциальной задержкой
- Детальное логирование
"""
import time
import logging
from typing import List, Dict, Tuple, Optional
from decimal import Decimal
from django.core.mail import EmailMultiAlternatives
from django.core.mail.backends.smtp import EmailBackend

logger = logging.getLogger(__name__)


class BulkEmailSender:
    """
    Класс для массовой отправки email с оптимизациями.

    Особенности:
    - Использует одно SMTP соединение для всех писем (connection pooling)
    - Автоматическая задержка между письмами (rate limiting)
    - Повторные попытки при временных ошибках (retry с exponential backoff)
    - Детальное логирование каждой попытки

    Пример использования:
        sender = BulkEmailSender(
            email_settings=email_settings,
            delay_seconds=1.0,
            max_retries=3
        )

        with sender:
            for recipient_data in recipients_list:
                success, error = sender.send_email(
                    subject="Тема",
                    body_text="Текст",
                    body_html="<html>Текст</html>",
                    to_emails=["user@example.com"],
                    attachment_name="file.docx",
                    attachment_content=doc_bytes,
                    attachment_mimetype="application/vnd.openxmlformats..."
                )
                if not success:
                    logger.error(f"Ошибка: {error}")
    """

    def __init__(
        self,
        email_settings,
        delay_seconds: float = 1.0,
        max_retries: int = 3,
        connection_timeout: int = 30
    ):
        """
        Инициализация BulkEmailSender.

        Args:
            email_settings: EmailSettings объект с настройками SMTP
            delay_seconds: Задержка между отправками в секундах (по умолчанию 1.0)
            max_retries: Максимальное количество повторных попыток (по умолчанию 3)
            connection_timeout: Таймаут подключения к SMTP в секундах (по умолчанию 30)
        """
        self.email_settings = email_settings
        self.delay_seconds = float(delay_seconds)
        self.max_retries = max_retries
        self.connection_timeout = connection_timeout

        # SMTP соединение (будет создано при входе в context manager)
        self.connection: Optional[EmailBackend] = None

        # Статистика
        self.emails_sent = 0
        self.emails_failed = 0
        self.total_retries = 0

        # Время последней отправки (для rate limiting)
        self.last_send_time = None

        logger.info(
            f"BulkEmailSender инициализирован: "
            f"delay={self.delay_seconds}s, "
            f"max_retries={self.max_retries}, "
            f"timeout={self.connection_timeout}s"
        )

    def __enter__(self):
        """Вход в context manager - создание SMTP соединения."""
        try:
            self.connection = self.email_settings.get_connection()
            if not self.connection:
                raise Exception("Не удалось создать SMTP подключение")

            # Явно открываем соединение
            self.connection.open()
            logger.info("✅ SMTP соединение открыто")
            return self
        except Exception as e:
            logger.error(f"❌ Ошибка открытия SMTP соединения: {str(e)}", exc_info=True)
            raise

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Выход из context manager - закрытие SMTP соединения."""
        if self.connection:
            try:
                self.connection.close()
                logger.info(
                    f"✅ SMTP соединение закрыто. "
                    f"Статистика: отправлено={self.emails_sent}, "
                    f"ошибок={self.emails_failed}, "
                    f"повторов={self.total_retries}"
                )
            except Exception as e:
                logger.warning(f"⚠️ Ошибка при закрытии SMTP соединения: {str(e)}")

    def _apply_rate_limiting(self):
        """Применяет задержку между отправками для защиты от бана SMTP провайдера."""
        if self.last_send_time and self.delay_seconds > 0:
            elapsed = time.time() - self.last_send_time
            if elapsed < self.delay_seconds:
                sleep_time = self.delay_seconds - elapsed
                logger.debug(f"🕐 Rate limiting: пауза {sleep_time:.2f}s")
                time.sleep(sleep_time)

    def _send_with_retry(
        self,
        email_message: EmailMultiAlternatives,
        recipient_str: str
    ) -> Tuple[bool, Optional[str]]:
        """
        Отправляет email с повторными попытками при временных ошибках.

        Args:
            email_message: Подготовленное EmailMultiAlternatives сообщение
            recipient_str: Строковое представление получателей (для логирования)

        Returns:
            Tuple[success: bool, error_message: Optional[str]]
        """
        attempt = 0
        last_error = None

        while attempt <= self.max_retries:
            try:
                # Применяем rate limiting перед каждой попыткой
                if attempt > 0:
                    # Экспоненциальная задержка для retry: 2^attempt секунд
                    backoff_delay = 2 ** attempt
                    logger.info(
                        f"🔄 Повторная попытка #{attempt} через {backoff_delay}s "
                        f"для {recipient_str}"
                    )
                    time.sleep(backoff_delay)
                    self.total_retries += 1
                else:
                    # Обычный rate limiting для первой попытки
                    self._apply_rate_limiting()

                # Отправка
                email_message.send(fail_silently=False)

                # Успех
                self.last_send_time = time.time()
                self.emails_sent += 1

                if attempt > 0:
                    logger.info(f"✅ Успех после {attempt} повтор(ов) для {recipient_str}")

                return True, None

            except Exception as e:
                last_error = str(e)
                attempt += 1

                # Проверяем, является ли ошибка временной (можно повторить)
                is_retryable = self._is_retryable_error(e)

                if attempt <= self.max_retries and is_retryable:
                    logger.warning(
                        f"⚠️ Временная ошибка (попытка {attempt}/{self.max_retries + 1}) "
                        f"для {recipient_str}: {last_error}"
                    )
                else:
                    # Финальная ошибка
                    self.emails_failed += 1
                    logger.error(
                        f"❌ Финальная ошибка после {attempt} попыток "
                        f"для {recipient_str}: {last_error}",
                        exc_info=True
                    )
                    return False, last_error

        # Не должно дойти сюда, но на всякий случай
        return False, last_error

    def _is_retryable_error(self, exception: Exception) -> bool:
        """
        Определяет, является ли ошибка временной (можно повторить попытку).

        Временные ошибки:
        - Таймауты сети
        - Временная недоступность SMTP сервера
        - Превышение лимита соединений

        Постоянные ошибки (не повторять):
        - Неверный логин/пароль
        - Неверный формат email
        - Блокировка аккаунта
        """
        error_msg = str(exception).lower()

        # Временные ошибки (можно retry)
        retryable_patterns = [
            'timeout',
            'timed out',
            'connection refused',
            'connection reset',
            'temporarily unavailable',
            'too many connections',
            'server busy',
            'try again later',
        ]

        # Постоянные ошибки (не retry)
        permanent_patterns = [
            'authentication failed',
            'invalid login',
            'invalid credentials',
            'username and password not accepted',
            'mailbox unavailable',
            'user unknown',
            'relay access denied',
        ]

        # Проверяем на постоянные ошибки
        for pattern in permanent_patterns:
            if pattern in error_msg:
                logger.debug(f"Постоянная ошибка обнаружена: {pattern}")
                return False

        # Проверяем на временные ошибки
        for pattern in retryable_patterns:
            if pattern in error_msg:
                logger.debug(f"Временная ошибка обнаружена: {pattern}")
                return True

        # По умолчанию считаем ошибку временной (можно retry)
        # Это безопаснее, чем пропустить письмо
        return True

    def send_email(
        self,
        subject: str,
        body_text: str,
        to_emails: List[str],
        body_html: Optional[str] = None,
        attachment_name: Optional[str] = None,
        attachment_content: Optional[bytes] = None,
        attachment_mimetype: Optional[str] = None
    ) -> Tuple[bool, Optional[str]]:
        """
        Отправляет одно email письмо с использованием общего SMTP соединения.

        Args:
            subject: Тема письма
            body_text: Текстовая версия письма
            to_emails: Список email получателей
            body_html: HTML версия письма (опционально)
            attachment_name: Имя файла вложения (опционально)
            attachment_content: Содержимое вложения в байтах (опционально)
            attachment_mimetype: MIME тип вложения (опционально)

        Returns:
            Tuple[success: bool, error_message: Optional[str]]
        """
        if not self.connection:
            return False, "SMTP соединение не открыто. Используйте context manager (with sender:)"

        try:
            # Формируем email сообщение
            from_email = (
                self.email_settings.default_from_email or
                self.email_settings.email_host_user
            )

            email = EmailMultiAlternatives(
                subject=subject,
                body=body_text,
                from_email=from_email,
                to=to_emails,
                connection=self.connection
            )

            # Добавляем HTML версию если есть
            if body_html:
                email.attach_alternative(body_html, "text/html")

            # Добавляем вложение если есть
            if attachment_name and attachment_content and attachment_mimetype:
                email.attach(attachment_name, attachment_content, attachment_mimetype)

            # Отправляем с retry механизмом
            recipient_str = ', '.join(to_emails)
            return self._send_with_retry(email, recipient_str)

        except Exception as e:
            error_msg = f"Ошибка подготовки email: {str(e)}"
            logger.error(error_msg, exc_info=True)
            self.emails_failed += 1
            return False, error_msg

    def get_stats(self) -> Dict[str, int]:
        """
        Возвращает статистику отправки.

        Returns:
            Dict с ключами: sent, failed, retries
        """
        return {
            'sent': self.emails_sent,
            'failed': self.emails_failed,
            'retries': self.total_retries
        }
