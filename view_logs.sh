#!/bin/bash
# Скрипт для просмотра логов бота

LOG_DIR="logs"

show_help() {
    echo "📋 Команды для просмотра логов:"
    echo "  ./view_logs.sh live    - Логи в реальном времени"
    echo "  ./view_logs.sh errors  - Только ошибки"
    echo "  ./view_logs.sh today   - Логи за сегодня"
    echo "  ./view_logs.sh last    - Последние 100 строк"
    echo "  ./view_logs.sh grep PATTERN - Поиск по паттерну"
    echo ""
}

case "$1" in
    "live")
        echo "📺 Логи в реальном времени (Ctrl+C для выхода):"
        tail -f $LOG_DIR/bot.log
        ;;
    "errors")
        echo "🚨 Ошибки:"
        cat $LOG_DIR/errors.log 2>/dev/null || echo "Файл ошибок не найден"
        ;;
    "today")
        echo "📅 Логи за сегодня:"
        TODAY=$(date +%Y-%m-%d)
        grep "$TODAY" $LOG_DIR/bot.log 2>/dev/null || echo "Логов за сегодня не найдено"
        ;;
    "last")
        echo "📜 Последние 100 строк:"
        tail -n 100 $LOG_DIR/bot.log 2>/dev/null || echo "Лог файл не найден"
        ;;
    "grep")
        if [ -z "$2" ]; then
            echo "❌ Укажите паттерн для поиска"
            exit 1
        fi
        echo "🔍 Поиск '$2' в логах:"
        grep -i "$2" $LOG_DIR/bot.log 2>/dev/null || echo "Совпадений не найдено"
        ;;
    *)
        show_help
        ;;
esac
