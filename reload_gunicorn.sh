#!/bin/bash
# Скрипт graceful reload Gunicorn (без даунтайма)

set -e

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}🔄 Перезагрузка Gunicorn (graceful)${NC}"
echo -e "${GREEN}========================================${NC}"
echo

if pgrep -f "gunicorn.*potby" > /dev/null; then
    MASTER_PID=$(pgrep -f "gunicorn.*potby.*master" 2>/dev/null || pgrep -f "gunicorn.*potby" | head -1)

    echo "Master PID: $MASTER_PID"
    echo -n "Отправка сигнала HUP..."
    kill -HUP $MASTER_PID
    echo -e " ${GREEN}✓${NC}"

    sleep 2

    echo "Новые worker процессы:"
    ps aux | grep "[g]unicorn.*potby" | grep -v master

    echo
    echo -e "${GREEN}✓ Перезагрузка завершена${NC}"
else
    echo -e "${RED}✗ Gunicorn не запущен${NC}"
    echo "Запустите: ./start_gunicorn.sh"
    exit 1
fi
