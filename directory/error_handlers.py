from django.shortcuts import render
from django.conf import settings
import logging

logger = logging.getLogger(__name__)

def error_400(request, exception):
    """
    🔍 Обработчик ошибки 400 – Некорректный запрос.
    """
    # Логируем детали для разработчиков
    logger.warning(f"400 Error: {request.path} - {exception}")

    context = {
        'error_code': '400',
        'error_message': 'Некорректный запрос',
        # НЕ передаём exception в production - это небезопасно!
    }
    return render(request, 'errors/400.html', context, status=400)

def error_403(request, exception):
    """
    🔒 Обработчик ошибки 403 – Доступ запрещен.
    """
    # Логируем детали для разработчиков
    logger.warning(f"403 Error: {request.path} - {exception}")

    context = {
        'error_code': '403',
        'error_message': 'Доступ запрещен',
        # НЕ передаём exception в production - это небезопасно!
    }
    return render(request, 'errors/403.html', context, status=403)

def error_404(request, exception):
    """
    🔍 Обработчик ошибки 404 – Страница не найдена.
    """
    # Логируем детали для разработчиков
    logger.info(f"404 Error: {request.path}")

    context = {
        'error_code': '404',
        'error_message': 'Страница не найдена',
        # НЕ передаём exception в production - это раскрывает структуру URL!
        # Техническая информация: {'tried': [...], 'path': '...'} - небезопасно!
    }
    return render(request, 'errors/404.html', context, status=404)

def error_500(request):
    """
    ⚠️ Обработчик ошибки 500 – Внутренняя ошибка сервера.
    """
    # Логируем для разработчиков
    logger.error(f"500 Error: {request.path}")

    context = {
        'error_code': '500',
        'error_message': 'Внутренняя ошибка сервера'
        # Никаких деталей пользователю - только в логи!
    }
    return render(request, 'errors/500.html', context, status=500)
