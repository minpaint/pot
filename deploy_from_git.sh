#!/bin/bash
# Автоматический деплой OT_online из Git
# Использование: ./deploy_from_git.sh

set -e

# Цвета
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}🚀 Деплой OT_online из Git${NC}"
echo -e "${GREEN}========================================${NC}"
echo

# 1. Проверка текущей ветки
BRANCH=$(git branch --show-current)
echo -e "${GREEN}📍 Текущая ветка:${NC} $BRANCH"

if [ "$BRANCH" != "main" ]; then
    echo -e "${YELLOW}⚠️  Вы не на ветке main!${NC}"
    read -p "Продолжить? (y/n) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
fi
echo

# 2. Сохранить локальные изменения
if [[ $(git status --porcelain) ]]; then
    echo -e "${YELLOW}💾 Обнаружены локальные изменения${NC}"
    echo "Сохраняю в stash..."
    STASH_NAME="auto-stash-before-deploy-$(date +%Y%m%d_%H%M%S)"
    git stash save "$STASH_NAME"
    echo -e "${GREEN}✓ Сохранено в stash: $STASH_NAME${NC}"
    STASHED=true
else
    echo -e "${GREEN}✓ Нет локальных изменений${NC}"
    STASHED=false
fi
echo

# 3. Получить обновления
echo -e "${GREEN}📥 Получение изменений из Git...${NC}"
git fetch origin

# 4. Показать изменения
CHANGES=$(git log HEAD..origin/$BRANCH --oneline)
if [ -z "$CHANGES" ]; then
    echo -e "${GREEN}✓ Нет новых изменений для применения${NC}"

    # Вернуть stash если был
    if [ "$STASHED" = true ]; then
        echo "Восстанавливаю локальные изменения..."
        git stash pop
    fi

    echo
    echo -e "${GREEN}========================================${NC}"
    echo -e "${GREEN}✅ Уже на последней версии${NC}"
    echo -e "${GREEN}========================================${NC}"
    exit 0
fi

echo
echo -e "${GREEN}📋 Изменения для применения:${NC}"
echo "$CHANGES"
echo
read -p "Применить эти изменения? (y/n) " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "Отменено"
    if [ "$STASHED" = true ]; then
        git stash pop
    fi
    exit 0
fi

# 5. Применить обновления
echo -e "${GREEN}⬇️  Применение обновлений...${NC}"
git pull origin $BRANCH

# 6. Вернуть локальные изменения
if [ "$STASHED" = true ]; then
    echo -e "${GREEN}♻️  Восстановление локальных изменений...${NC}"
    if git stash pop; then
        echo -e "${GREEN}✓ Локальные изменения восстановлены${NC}"
    else
        echo -e "${RED}⚠️  Конфликт при восстановлении!${NC}"
        echo "Проверьте файлы вручную:"
        git status
        read -p "Нажмите Enter для продолжения..."
    fi
fi
echo

# 7. Виртуальное окружение и зависимости
echo -e "${GREEN}🐍 Проверка зависимостей...${NC}"
source venv/bin/activate
if pip install -r requirements.txt -q; then
    echo -e "${GREEN}✓ Зависимости обновлены${NC}"
else
    echo -e "${YELLOW}⚠️  Некоторые зависимости не установились${NC}"
fi
echo

# 8. Миграции базы данных
echo -e "${GREEN}🗄️  Проверка миграций...${NC}"
if python manage.py migrate --settings=settings_prod --no-input; then
    echo -e "${GREEN}✓ Миграции применены${NC}"
else
    echo -e "${RED}✗ Ошибка применения миграций!${NC}"
    echo "Проверьте логи и исправьте вручную"
    exit 1
fi
echo

# 9. Сборка статики
echo -e "${GREEN}📦 Сборка статических файлов...${NC}"
if python manage.py collectstatic --noinput --settings=settings_prod > /dev/null; then
    echo -e "${GREEN}✓ Статика собрана${NC}"
else
    echo -e "${YELLOW}⚠️  Ошибка сборки статики${NC}"
fi
echo

# 10. Проверка безопасности
echo -e "${GREEN}🔒 Проверка настроек безопасности...${NC}"
if DJANGO_SETTINGS_MODULE=settings_prod venv/bin/python scripts/check_debug_status.py > /dev/null 2>&1; then
    echo -e "${GREEN}✓ Настройки безопасности в порядке${NC}"
else
    echo -e "${YELLOW}⚠️  Проверьте настройки безопасности вручную${NC}"
fi
echo

# 11. Перезапуск сервера
echo -e "${GREEN}🔄 Перезапуск Gunicorn...${NC}"
if [ -f "./reload_gunicorn.sh" ]; then
    if ./reload_gunicorn.sh > /dev/null 2>&1; then
        echo -e "${GREEN}✓ Сервер перезапущен${NC}"
    else
        echo -e "${RED}✗ Ошибка перезапуска!${NC}"
        echo "Попробуйте вручную: ./reload_gunicorn.sh"
    fi
else
    echo -e "${YELLOW}⚠️  Скрипт reload_gunicorn.sh не найден${NC}"
    echo "Перезапустите сервер вручную"
fi
echo

# 12. Итоговый статус
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}✅ Деплой завершён успешно!${NC}"
echo -e "${GREEN}========================================${NC}"
echo
echo "Текущая версия:"
git log -1 --oneline
echo
echo "Проверьте работу сайта: https://pot.by"
echo
