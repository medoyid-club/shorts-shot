"""
Конфигурация логирования для Telegram-to-YouTube Shorts бота
"""
import logging
import logging.handlers
import os
from datetime import datetime
from pathlib import Path


def setup_logging(log_dir: str = "logs", log_level: str = "INFO") -> None:
    """
    Настройка логирования с ротацией файлов
    
    Args:
        log_dir: Директория для логов
        log_level: Уровень логирования (DEBUG, INFO, WARNING, ERROR)
    """
    
    # Создаем директорию для логов
    log_path = Path(log_dir)
    log_path.mkdir(exist_ok=True)
    
    # Настройка уровня логирования
    numeric_level = getattr(logging, log_level.upper(), logging.INFO)
    
    # Создаем форматтер
    formatter = logging.Formatter(
        fmt='[%(asctime)s] %(levelname)s %(name)s: %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    # Основной лог файл с ротацией (максимум 10MB, хранить 30 файлов)
    main_log_file = log_path / "bot.log"
    main_handler = logging.handlers.RotatingFileHandler(
        main_log_file,
        maxBytes=10*1024*1024,  # 10MB
        backupCount=30,
        encoding='utf-8'
    )
    main_handler.setFormatter(formatter)
    main_handler.setLevel(numeric_level)
    
    # Лог только ошибок
    error_log_file = log_path / "errors.log"
    error_handler = logging.handlers.RotatingFileHandler(
        error_log_file,
        maxBytes=5*1024*1024,   # 5MB
        backupCount=10,
        encoding='utf-8'
    )
    error_handler.setFormatter(formatter)
    error_handler.setLevel(logging.ERROR)
    
    # Консольный вывод (для systemd)
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    console_handler.setLevel(numeric_level)
    
    # Настройка root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(numeric_level)
    
    # Очищаем предыдущие handlers
    root_logger.handlers.clear()
    
    # Добавляем handlers
    root_logger.addHandler(main_handler)
    root_logger.addHandler(error_handler)
    root_logger.addHandler(console_handler)
    
    # Настройка специфичных логгеров
    loggers_config = {
        'httpx': logging.WARNING,           # Снижаем verbose HTTP логи
        'telethon': logging.INFO,
        'googleapiclient': logging.WARNING,
        'moviepy': logging.WARNING,
        'PIL': logging.WARNING,
    }
    
    for logger_name, level in loggers_config.items():
        logger = logging.getLogger(logger_name)
        logger.setLevel(level)
    
    # Логируем успешную настройку
    logger = logging.getLogger("logger_config")
    logger.info(f"✅ Логирование настроено: уровень={log_level}, директория={log_path.absolute()}")
    logger.info(f"📄 Основной лог: {main_log_file}")
    logger.info(f"🚨 Лог ошибок: {error_log_file}")


def log_system_info():
    """Логируем информацию о системе при запуске"""
    logger = logging.getLogger("system")
    
    try:
        import platform
        import psutil
        
        logger.info("🖥️ Системная информация:")
        logger.info(f"   OS: {platform.system()} {platform.release()}")
        logger.info(f"   Python: {platform.python_version()}")
        logger.info(f"   CPU: {psutil.cpu_count()} ядер")
        logger.info(f"   RAM: {psutil.virtual_memory().total // (1024**3)} GB")
        logger.info(f"   Диск: {psutil.disk_usage('/').free // (1024**3)} GB свободно")
        
    except ImportError:
        logger.info("🖥️ Системная информация недоступна (psutil не установлен)")
    except Exception as e:
        logger.warning(f"⚠️ Ошибка получения системной информации: {e}")


def log_config_info(config: dict):
    """Логируем основные настройки бота (без чувствительных данных)"""
    logger = logging.getLogger("config")
    
    logger.info("⚙️ Конфигурация бота:")
    
    # Безопасное получение значений из ConfigParser
    try:
        llm_model = config['LLM']['gemini_model'] if 'LLM' in config and 'gemini_model' in config['LLM'] else 'N/A'
        video_duration = config['VIDEO']['duration_seconds'] if 'VIDEO' in config and 'duration_seconds' in config['VIDEO'] else 'N/A'
        video_width = config['VIDEO']['width'] if 'VIDEO' in config and 'width' in config['VIDEO'] else 'N/A'
        video_height = config['VIDEO']['height'] if 'VIDEO' in config and 'height' in config['VIDEO'] else 'N/A'
        youtube_category = config['YOUTUBE']['category_id'] if 'YOUTUBE' in config and 'category_id' in config['YOUTUBE'] else 'N/A'
        youtube_privacy = config['YOUTUBE']['privacy_status'] if 'YOUTUBE' in config and 'privacy_status' in config['YOUTUBE'] else 'N/A'
        
        logger.info(f"   Модель LLM: {llm_model}")
        logger.info(f"   Длительность видео: {video_duration}с")
        logger.info(f"   Размер видео: {video_width}x{video_height}")
        logger.info(f"   YouTube категория: {youtube_category}")
        logger.info(f"   YouTube статус: {youtube_privacy}")
        
    except Exception as e:
        logger.warning(f"⚠️ Ошибка чтения конфигурации для лога: {e}")


def create_log_viewer_script():
    """Создает скрипт для удобного просмотра логов"""
    script_content = '''#!/bin/bash
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
'''
    
    with open('view_logs.sh', 'w', encoding='utf-8') as f:
        f.write(script_content)
    
    # Делаем скрипт исполняемым
    os.chmod('view_logs.sh', 0o755)
    
    logger = logging.getLogger("logger_config")
    logger.info("📜 Создан скрипт просмотра логов: ./view_logs.sh")
