#!/bin/bash
# Скрипт запуска Gunicorn для pot.by production
# ⚠️ КРИТИЧНО: Всегда использует settings_prod (DEBUG=False)

set -e

# Цвета для вывода
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}🚀 Запуск Gunicorn для pot.by${NC}"
echo -e "${GREEN}========================================${NC}"
echo

# 1. Переход в каталог проекта
cd /home/django/webapps/potby
echo -e "${GREEN}✓${NC} Каталог: $(pwd)"

# 2. Проверка виртуального окружения
if [ ! -d "venv" ]; then
    echo -e "${RED}✗${NC} Виртуальное окружение не найдено!"
    exit 1
fi
echo -e "${GREEN}✓${NC} Виртуальное окружение: venv/"

# 3. Проверка настроек
export DJANGO_SETTINGS_MODULE=settings_prod
source venv/bin/activate
DEBUG_STATUS=$(python -c "from django.conf import settings; print(settings.DEBUG)")

if [ "$DEBUG_STATUS" = "True" ]; then
    echo -e "${RED}✗ КРИТИЧНО: DEBUG=True!${NC}"
    echo -e "${RED}  Production запрещён с включённым DEBUG!${NC}"
    exit 1
fi
echo -e "${GREEN}✓${NC} DEBUG = False"

# 4. Проверка логов
mkdir -p logs
echo -e "${GREEN}✓${NC} Каталог логов: logs/"

# 5. Остановка старых процессов
if pgrep -f "gunicorn.*potby" > /dev/null; then
    echo -e "${YELLOW}⚠${NC}  Найдены запущенные процессы Gunicorn"
    echo -n "   Остановка..."
    pkill -f "gunicorn.*potby" || true
    sleep 2
    echo -e " ${GREEN}✓${NC}"
fi

# 6. Запуск Gunicorn
echo
echo -e "${GREEN}Запуск Gunicorn...${NC}"
echo "  Workers: 3"
echo "  Bind: 192.168.37.10:8020"
echo "  Timeout: 120s"
echo "  Settings: settings_prod (DEBUG=False)"
echo

DJANGO_SETTINGS_MODULE=settings_prod \
venv/bin/gunicorn \
    --workers 3 \
    --bind 192.168.37.10:8020 \
    --timeout 120 \
    --access-logfile logs/gunicorn.access.log \
    --error-logfile logs/gunicorn.error.log \
    --daemon \
    wsgi:application

# 7. Проверка запуска
sleep 2
if pgrep -f "gunicorn.*potby" > /dev/null; then
    PID=$(pgrep -f "gunicorn.*potby" | head -1)
    echo -e "${GREEN}✓ Gunicorn запущен (PID: $PID)${NC}"
    echo
    echo "Логи:"
    echo "  Access: tail -f logs/gunicorn.access.log"
    echo "  Error:  tail -f logs/gunicorn.error.log"
    echo
    echo -e "${GREEN}========================================${NC}"
    echo -e "${GREEN}✓ Запуск завершён успешно${NC}"
    echo -e "${GREEN}========================================${NC}"
else
    echo -e "${RED}✗ Ошибка запуска!${NC}"
    echo "Проверьте логи: tail logs/gunicorn.error.log"
    exit 1
fi
