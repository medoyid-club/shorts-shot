#!/usr/bin/env python3
"""
Простейший тест для проверки что конфигурация загружается без ошибок
"""

import sys
from pathlib import Path

# Добавляем текущую директорию в путь
sys.path.insert(0, str(Path(__file__).parent))

def test_config_only():
    """Тестирует только загрузку конфигурации"""
    print("🧪 Тестируем загрузку конфигурации...")
    
    try:
        from services.config_loader import load_config
        
        project_root = Path(__file__).parent
        config = load_config(project_root)
        print("✅ Конфигурация загружена успешно")
        
        # Проверим что это обычный dict
        print(f"   Тип config: {type(config)}")
        
        if 'TWITTER' in config:
            twitter_config = config['TWITTER'] 
            print(f"   Тип TWITTER секции: {type(twitter_config)}")
            
            enabled = twitter_config.get('enabled', 'false')
            print(f"   enabled значение: '{enabled}' (тип: {type(enabled)})")
            
            # Проверим что .lower() работает
            result = str(enabled).lower() == 'true'
            print(f"   ✅ Результат обработки: {result}")
        
        return True
        
    except Exception as e:
        print(f"❌ Ошибка: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_twitter_init():
    """Тестирует инициализацию TwitterUploader"""
    print("\n🐦 Тестируем инициализацию TwitterUploader...")
    
    try:
        from services.config_loader import load_config
        from services.twitter_uploader import TwitterUploader
        
        project_root = Path(__file__).parent
        config = load_config(project_root)
        
        twitter = TwitterUploader(config)
        print(f"✅ TwitterUploader создан, enabled: {twitter.enabled}")
        
        return True
        
    except Exception as e:
        print(f"❌ Ошибка: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    success = True
    
    if not test_config_only():
        success = False
        
    if not test_twitter_init():
        success = False
    
    if success:
        print("\n🎉 Все тесты прошли успешно!")
        return 0
    else:
        print("\n💥 Есть проблемы")
        return 1

if __name__ == "__main__":
    exit(main())
