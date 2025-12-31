#!/bin/bash
# Восстановление БД из бэкапа
# Использование: ./restore_db.sh backups/2025-12-31_15-30-00_ot_online.sql.gz

set -euo pipefail

# Цвета для вывода
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'  # No Color

DB_NAME="ot_online"
DB_USER="ot_user"
DB_HOST="localhost"
DB_PORT="5432"
BACKUP_DIR="/home/django/backups"

# Проверка параметров
if [ -z "${1:-}" ]; then
    echo -e "${YELLOW}Использование:${NC} ./restore_db.sh backups/pg-ot_online-YYYYMMDD_HHMMSS.sql.gz"
    echo ""
    echo -e "${GREEN}Доступные бэкапы (последние 10):${NC}"
    ls -lth "$BACKUP_DIR"/pg-${DB_NAME}-*.sql.gz 2>/dev/null | head -10 || echo "  (бэкапы не найдены)"
    exit 1
fi

BACKUP_FILE="$1"

# Проверка существования файла
if [ ! -f "$BACKUP_FILE" ]; then
    echo -e "${RED}✗ Ошибка: Файл бэкапа не найден: $BACKUP_FILE${NC}"
    exit 1
fi

echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}🔄 Восстановление БД из бэкапа${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""
echo -e "${YELLOW}⚠️  ВНИМАНИЕ:${NC} Все текущие данные БД будут заменены на данные из бэкапа!"
echo -e "${YELLOW}   Файл:${NC} $BACKUP_FILE"
echo ""
read -p "Продолжить? Введите 'yes' для подтверждения: " CONFIRM

if [ "$CONFIRM" != "yes" ]; then
    echo -e "${YELLOW}Отменено${NC}"
    exit 0
fi

echo ""
echo -e "${GREEN}[1/4]${NC} Остановка Gunicorn..."
if [ -f "./stop_gunicorn.sh" ]; then
    ./stop_gunicorn.sh > /dev/null 2>&1 || true
    echo -e "${GREEN}  ✓ Gunicorn остановлен${NC}"
else
    # Если скрипта нет, попытаться остановить напрямую
    pkill -f "gunicorn.*potby" || true
    echo -e "${GREEN}  ✓ Gunicorn остановлен${NC}"
fi

echo ""
echo -e "${GREEN}[2/4]${NC} Завершение активных соединений с БД..."
export PGPASSFILE="/home/django/.pgpass"
psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d postgres -c "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = '$DB_NAME' AND pid <> pg_backend_pid();" > /dev/null 2>&1 || true
echo -e "${GREEN}  ✓ Соединения завершены${NC}"

echo ""
echo -e "${GREEN}[3/4]${NC} Восстановление БД из бэкапа..."
echo -e "${YELLOW}  Это может занять некоторое время...${NC}"

# Восстановление (сбрасываем существующую БД и восстанавливаем из дампа)
gunzip -c "$BACKUP_FILE" | psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" > /dev/null 2>&1

if [ $? -eq 0 ]; then
    echo -e "${GREEN}  ✓ БД восстановлена${NC}"
else
    echo -e "${RED}  ✗ Ошибка восстановления БД!${NC}"
    echo -e "${YELLOW}  Попытка запустить Gunicorn...${NC}"
    ./start_gunicorn.sh > /dev/null 2>&1 || true
    exit 1
fi

echo ""
echo -e "${GREEN}[4/4]${NC} Запуск Gunicorn..."
if [ -f "./start_gunicorn.sh" ]; then
    ./start_gunicorn.sh > /dev/null 2>&1
    echo -e "${GREEN}  ✓ Gunicorn запущен${NC}"
else
    echo -e "${YELLOW}  ⚠ Скрипт start_gunicorn.sh не найден${NC}"
    echo -e "${YELLOW}  Запустите Gunicorn вручную!${NC}"
fi

echo ""
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}✅ Восстановление завершено успешно!${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""
echo -e "БД восстановлена из: ${GREEN}$BACKUP_FILE${NC}"
echo -e "Проверьте работу сайта: ${GREEN}https://pot.by${NC}"
echo ""
