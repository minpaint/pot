#!/bin/bash
# Скрипт остановки Gunicorn для pot.by

set -e

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo -e "${YELLOW}========================================${NC}"
echo -e "${YELLOW}⏹  Остановка Gunicorn для pot.by${NC}"
echo -e "${YELLOW}========================================${NC}"
echo

if pgrep -f "gunicorn.*potby" > /dev/null; then
    echo "Найдены процессы Gunicorn:"
    ps aux | grep "[g]unicorn.*potby" | head -5
    echo
    echo -n "Остановка..."
    pkill -f "gunicorn.*potby"
    sleep 2

    if pgrep -f "gunicorn.*potby" > /dev/null; then
        echo " не удалось (graceful), принудительная остановка..."
        pkill -9 -f "gunicorn.*potby"
        sleep 1
    fi

    echo -e " ${GREEN}✓${NC}"
    echo -e "${GREEN}Gunicorn остановлен${NC}"
else
    echo "Процессы Gunicorn не найдены"
fi
echo
