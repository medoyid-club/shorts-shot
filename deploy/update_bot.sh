#!/bin/bash
# Скрипт автообновления Telegram-to-YouTube Shorts бота

set -e

# Цвета для вывода
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Функция для логирования
log() {
    echo -e "${BLUE}[$(date '+%Y-%m-%d %H:%M:%S')]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[$(date '+%Y-%m-%d %H:%M:%S')] ✅${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[$(date '+%Y-%m-%d %H:%M:%S')] ⚠️${NC} $1"
}

log_error() {
    echo -e "${RED}[$(date '+%Y-%m-%d %H:%M:%S')] ❌${NC} $1"
}

# Конфигурация
BOT_DIR="/home/dzianis/shorts-shot"
SERVICE_NAME="telegram-shorts.service"
BACKUP_DIR="/home/dzianis/bot_backups"
VENV_PATH="$BOT_DIR/.venv"

# Функция помощи
show_help() {
    echo "🤖 Инструмент автообновления Telegram-to-YouTube Shorts бота"
    echo ""
    echo "Использование:"
    echo "  $0 update    - Обновить бота с git и перезапустить"
    echo "  $0 restart   - Перезапустить сервис"
    echo "  $0 status    - Показать статус сервиса"
    echo "  $0 logs      - Показать логи"
    echo "  $0 backup    - Создать бэкап"
    echo "  $0 rollback  - Откатиться к последнему бэкапу"
    echo ""
}

# Проверка что мы в правильной директории
check_directory() {
    if [ ! -d "$BOT_DIR" ]; then
        log_error "Директория бота не найдена: $BOT_DIR"
        exit 1
    fi
    
    if [ ! -f "$BOT_DIR/main_script.py" ]; then
        log_error "main_script.py не найден в $BOT_DIR"
        exit 1
    fi
}

# Создание бэкапа
create_backup() {
    log "📦 Создание бэкапа..."
    
    mkdir -p "$BACKUP_DIR"
    
    BACKUP_NAME="backup_$(date +%Y%m%d_%H%M%S)"
    BACKUP_PATH="$BACKUP_DIR/$BACKUP_NAME"
    
    # Создаем бэкап (исключая .git, logs, outputs, venv)
    rsync -av --exclude='.git' --exclude='logs' --exclude='outputs' --exclude='.venv' \
          --exclude='__pycache__' --exclude='*.pyc' --exclude='state' \
          "$BOT_DIR/" "$BACKUP_PATH/"
    
    log_success "Бэкап создан: $BACKUP_PATH"
    
    # Оставляем только последние 10 бэкапов
    (cd "$BACKUP_DIR" && ls -t | tail -n +11 | xargs -r rm -rf)
    
    echo "$BACKUP_NAME" > "$BACKUP_DIR/latest_backup"
}

# Откат к бэкапу
rollback() {
    log "🔄 Откат к последнему бэкапу..."
    
    if [ ! -f "$BACKUP_DIR/latest_backup" ]; then
        log_error "Файл последнего бэкапа не найден"
        exit 1
    fi
    
    LATEST_BACKUP=$(cat "$BACKUP_DIR/latest_backup")
    BACKUP_PATH="$BACKUP_DIR/$LATEST_BACKUP"
    
    if [ ! -d "$BACKUP_PATH" ]; then
        log_error "Бэкап не найден: $BACKUP_PATH"
        exit 1
    fi
    
    # Останавливаем сервис
    log "🛑 Остановка сервиса..."
    sudo systemctl stop "$SERVICE_NAME" || true
    
    # Восстанавливаем файлы (кроме .env, token.json, logs, .git)
    log "📁 Восстановление файлов..."
    rsync -av --exclude='.env' --exclude='token.json' --exclude='logs' \
          --exclude='outputs' --exclude='state' --exclude='.git' \
          "$BACKUP_PATH/" "$BOT_DIR/"
    
    # Перезапускаем сервис
    log "🚀 Запуск сервиса..."
    sudo systemctl start "$SERVICE_NAME"
    
    log_success "Откат завершен"
}

# Обновление с git
update_from_git() {
    log "🔄 Обновление бота с Git..."
    
    cd "$BOT_DIR"
    
    # Проверяем git статус
    if [ ! -d ".git" ]; then
        log_error "Не найдена git директория"
        exit 1
    fi
    
    # Сохраняем текущий commit
    CURRENT_COMMIT=$(git rev-parse HEAD)
    log "📍 Текущий commit: ${CURRENT_COMMIT:0:8}"
    
    # Получаем изменения
    log "📥 Получение обновлений..."
    git fetch origin
    
    # Проверяем есть ли обновления
    REMOTE_COMMIT=$(git rev-parse origin/main)
    if [ "$CURRENT_COMMIT" = "$REMOTE_COMMIT" ]; then
        log_success "Бот уже последней версии"
        return 0
    fi
    
    log "📋 Новые изменения доступны:"
    git log --oneline "$CURRENT_COMMIT..$REMOTE_COMMIT"
    
    # Создаем бэкап перед обновлением
    create_backup
    
    # Возвращаемся в правильную директорию после backup
    cd "$BOT_DIR"
    log "📂 Вернулись в директорию бота: $(pwd)"
    
    # Останавливаем сервис
    log "🛑 Остановка сервиса..."
    sudo systemctl stop "$SERVICE_NAME" || true
    
    # Применяем обновления
    log "⚡ Применение обновлений..."
    
    # Диагностика перед git reset
    log "🔍 Проверка .git директории перед обновлением..."
    if [ -d ".git" ]; then
        log "✅ .git директория существует"
    else
        log "❌ .git директория отсутствует!"
        exit 1
    fi
    
    # Проверяем PWD
    log "📂 Текущая директория: $(pwd)"
    
    git reset --hard origin/main
    
    # Проверяем requirements.txt на изменения
    if git diff --name-only "$CURRENT_COMMIT" HEAD | grep -q "requirements.txt"; then
        log "📦 Обновление Python зависимостей..."
        source "$VENV_PATH/bin/activate"
        pip install -r requirements.txt
    fi
    
    NEW_COMMIT=$(git rev-parse HEAD)
    log "✅ Обновлено до commit: ${NEW_COMMIT:0:8}"
    
    # Перезапускаем сервис
    log "🚀 Запуск сервиса..."
    sudo systemctl start "$SERVICE_NAME"
    
    # Проверяем статус
    sleep 3
    if sudo systemctl is-active --quiet "$SERVICE_NAME"; then
        log_success "Сервис успешно запущен"
    else
        log_error "Проблема с запуском сервиса"
        sudo systemctl status "$SERVICE_NAME" --no-pager
        return 1
    fi
}

# Показать статус
show_status() {
    log "📊 Статус бота:"
    echo ""
    
    # Статус сервиса
    if sudo systemctl is-active --quiet "$SERVICE_NAME"; then
        log_success "Сервис: активен"
    else
        log_error "Сервис: неактивен"
    fi
    
    # Git информация
    cd "$BOT_DIR"
    if [ -d ".git" ]; then
        CURRENT_COMMIT=$(git rev-parse HEAD)
        BRANCH=$(git branch --show-current)
        echo "📍 Git branch: $BRANCH"
        echo "📍 Commit: ${CURRENT_COMMIT:0:8}"
        
        # Проверяем обновления
        git fetch origin --quiet
        REMOTE_COMMIT=$(git rev-parse origin/main)
        if [ "$CURRENT_COMMIT" != "$REMOTE_COMMIT" ]; then
            log_warning "Доступны обновления"
        else
            log_success "Последняя версия"
        fi
    fi
    
    # Логи сервиса
    echo ""
    echo "📋 Последние логи:"
    sudo journalctl -u "$SERVICE_NAME" --lines=5 --no-pager || true
}

# Показать логи
show_logs() {
    echo "📋 Логи сервиса (Ctrl+C для выхода):"
    sudo journalctl -u "$SERVICE_NAME" -f
}

# Перезапуск сервиса
restart_service() {
    log "🔄 Перезапуск сервиса..."
    sudo systemctl restart "$SERVICE_NAME"
    
    sleep 3
    if sudo systemctl is-active --quiet "$SERVICE_NAME"; then
        log_success "Сервис успешно перезапущен"
    else
        log_error "Проблема с перезапуском сервиса"
        sudo systemctl status "$SERVICE_NAME" --no-pager
        return 1
    fi
}

# Основная логика
main() {
    check_directory
    
    case "$1" in
        "update")
            update_from_git
            ;;
        "restart")
            restart_service
            ;;
        "status")
            show_status
            ;;
        "logs")
            show_logs
            ;;
        "backup")
            create_backup
            ;;
        "rollback")
            rollback
            ;;
        *)
            show_help
            ;;
    esac
}

# Запуск
main "$@"
