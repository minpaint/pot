"""
Middleware для мониторинга производительности admin страниц
"""
import time
import logging
from django.db import connection
from django.conf import settings

logger = logging.getLogger(__name__)


class AdminPerformanceMiddleware:
    """
    Мониторинг производительности admin страниц.

    Логирует медленные страницы (>2 секунд) и страницы с большим количеством SQL-запросов (>50).
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # Мониторим только admin страницы
        if not request.path.startswith('/admin/'):
            return self.get_response(request)

        # Засечь время начала
        start_time = time.time()

        # Засечь количество запросов (только в DEBUG режиме)
        start_queries = len(connection.queries) if settings.DEBUG else 0

        # Выполнить запрос
        response = self.get_response(request)

        # Посчитать метрики
        duration = time.time() - start_time
        num_queries = (len(connection.queries) - start_queries) if settings.DEBUG else 0

        # Логировать медленные или затратные страницы
        if duration > 2.0 or num_queries > 50:
            user_info = getattr(request.user, 'username', 'anonymous') if hasattr(request, 'user') else 'unknown'

            logger.warning(
                f"Slow admin page detected: "
                f"path={request.path} | "
                f"duration={duration:.2f}s | "
                f"queries={num_queries} | "
                f"user={user_info} | "
                f"method={request.method}"
            )

            # В DEBUG режиме выводим детали
            if settings.DEBUG and num_queries > 0:
                # Сгруппировать похожие запросы
                query_counts = {}
                for query in connection.queries[start_queries:]:
                    sql = query['sql'][:100]  # Первые 100 символов
                    query_counts[sql] = query_counts.get(sql, 0) + 1

                # Показать топ-5 самых частых запросов
                sorted_queries = sorted(query_counts.items(), key=lambda x: x[1], reverse=True)[:5]
                logger.debug("Top 5 most frequent queries:")
                for sql, count in sorted_queries:
                    logger.debug(f"  [{count}x] {sql}...")

        return response
