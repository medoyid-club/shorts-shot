#!/usr/bin/env python3
"""
Telegram Publisher для публикации Shorts
Заменяет YouTube публикацию на Telegram
"""

import os
import sys
import logging
from typing import Dict, Optional
from pathlib import Path

# Импортируем наш Telegram Publisher
sys.path.append(r'D:\work\shorts_news\scripts')

try:
    from telegram_publisher import TelegramPublisher as BaseTelegramPublisher
    ENHANCED_PUBLISHER_AVAILABLE = True
    print("✅ Улучшенный Telegram Publisher доступен")
except ImportError as e:
    ENHANCED_PUBLISHER_AVAILABLE = False
    print(f"⚠️ Улучшенный Telegram Publisher недоступен: {e}")

logger = logging.getLogger("telegram_publisher")

class TelegramPublisher:
    """Простой Telegram Publisher для замены YouTube"""

    def __init__(self, config: dict):
        self.config = config
        self.publisher = None

        if ENHANCED_PUBLISHER_AVAILABLE:
            try:
                self.publisher = BaseTelegramPublisher(r'D:\work\shorts_news\config\config.yaml')
                logger.info("🚀 Используем улучшенный Telegram Publisher")
            except Exception as e:
                logger.error(f"❌ Ошибка создания улучшенного publisher: {e}")
                self.publisher = None
        else:
            logger.info("📝 Улучшенный publisher недоступен, используем базовый")

    async def upload_video(self, video_path: str, title: str, description: str,
                          tags: list = None, privacy: str = "public") -> bool:
        """Загружает видео в Telegram канал"""

        if not self.publisher:
            logger.error("❌ Telegram Publisher не инициализирован")
            return False

        if not os.path.exists(video_path):
            logger.error(f"❌ Видео файл не найден: {video_path}")
            return False

        try:
            # Форматируем описание для Telegram
            caption = f"🎬 {title}\n\n"
            if description:
                caption += f"{description[:800]}...\n\n"  # Ограничение Telegram

            # Добавляем теги
            if tags and len(tags) > 0:
                hashtags = [f"#{tag.replace(' ', '')}" for tag in tags[:5]]  # Первые 5 тегов
                caption += " ".join(hashtags)

            # Подготавливаем данные для публикации
            publish_data = {
                'title': title,
                'short_text': description,
                'description': description,
                'source': 'Telegram Shorts',
                'published': '',
                'url': '',
                'video_path': video_path,
                'images': [],
                'fact_verification': {}
            }

            # Публикуем
            success = await self.publisher.publish_news(publish_data)

            if success:
                logger.info(f"✅ Видео опубликовано в Telegram: {os.path.basename(video_path)}")
                return True
            else:
                logger.error(f"❌ Ошибка публикации в Telegram: {os.path.basename(video_path)}")
                return False

        except Exception as e:
            logger.error(f"❌ Ошибка загрузки видео: {e}")
            return False

    def is_available(self) -> bool:
        """Проверяет доступность publisher"""
        return self.publisher is not None and self.publisher.is_available()
