#!/usr/bin/env python3
"""
Тестовый скрипт для проверки загрузки конфигурации
"""

import sys
from pathlib import Path

# Добавляем текущую директорию в путь
sys.path.insert(0, str(Path(__file__).parent))

from services.config_loader import load_config
from services.twitter_uploader import TwitterUploader
from services.video_generator import VideoComposer
from services.youtube_uploader import YouTubeUploader

def main():
    print("🧪 Тестируем загрузку конфигурации...")
    
    try:
        project_root = Path(__file__).parent
        config = load_config(project_root)
        print("✅ Конфигурация загружена успешно")
        
        # Тестируем Twitter
        print("\n🐦 Тестируем TwitterUploader...")
        twitter = TwitterUploader(config)
        print(f"   Включен: {twitter.enabled}")
        
        # Тестируем VideoComposer
        print("\n🎬 Тестируем VideoComposer...")
        composer = VideoComposer(config)
        print(f"   Heartbeat включен: {composer.heartbeat_enabled}")
        
        print("\n✅ Все тесты прошли успешно!")
        
    except Exception as e:
        print(f"❌ Ошибка: {e}")
        import traceback
        traceback.print_exc()
        return 1
    
    return 0

if __name__ == "__main__":
    exit(main())
