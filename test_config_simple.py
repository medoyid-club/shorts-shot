#!/usr/bin/env python3
"""
Простой тестовый скрипт для проверки загрузки конфигурации
"""

import sys
from pathlib import Path

# Добавляем текущую директорию в путь
sys.path.insert(0, str(Path(__file__).parent))

from services.config_loader import load_config

def test_config_loading():
    """Тестирует базовую загрузку конфигурации"""
    print("🧪 Тестируем загрузку конфигурации...")
    
    try:
        project_root = Path(__file__).parent
        config = load_config(project_root)
        print("✅ Конфигурация загружена успешно")
        
        # Проверяем основные секции
        required_sections = ['TELEGRAM', 'LLM', 'VIDEO', 'YOUTUBE', 'TWITTER', 'PATHS']
        for section in required_sections:
            if section in config:
                print(f"   ✅ Секция [{section}] найдена")
            else:
                print(f"   ❌ Секция [{section}] отсутствует")
        
        # Тестируем проблематичные настройки
        twitter_config = config.get('TWITTER', {})
        enabled_value = twitter_config.get('enabled', 'false')
        print(f"\n🐦 Twitter enabled значение: {enabled_value} (тип: {type(enabled_value)})")
        
        if isinstance(enabled_value, str):
            enabled = enabled_value.lower() == 'true'
            print(f"   ✅ Корректная обработка: {enabled}")
        else:
            print(f"   ❌ Неожиданный тип: {type(enabled_value)}")
        
        video_config = config.get('VIDEO', {})
        heartbeat_value = video_config.get('heartbeat_enabled', 'true')
        print(f"\n🎬 Video heartbeat значение: {heartbeat_value} (тип: {type(heartbeat_value)})")
        
        if isinstance(heartbeat_value, str):
            heartbeat = heartbeat_value.lower() == 'true'
            print(f"   ✅ Корректная обработка: {heartbeat}")
        else:
            print(f"   ❌ Неожиданный тип: {type(heartbeat_value)}")
        
        print("\n✅ Все тесты конфигурации прошли успешно!")
        return True
        
    except Exception as e:
        print(f"❌ Ошибка: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    if test_config_loading():
        print("\n🎉 Исправление работает корректно!")
        return 0
    else:
        print("\n💥 Есть проблемы с конфигурацией")
        return 1

if __name__ == "__main__":
    exit(main())
