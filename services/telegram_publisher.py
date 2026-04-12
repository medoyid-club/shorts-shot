#!/usr/bin/env python3
"""
Telegram Publisher для публикации Shorts
Заменяет YouTube публикацию на Telegram
"""

from __future__ import annotations

import os
import sys
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger("telegram_publisher")


def _resolve_shorts_news_root(config: dict) -> Optional[Path]:
    """Корень репозитория shorts_news: .env TELEGRAM_SHORTS_NEWS_PATH, затем [GENERAL].telegram_shorts_news_path."""
    raw = (os.environ.get("TELEGRAM_SHORTS_NEWS_PATH") or "").strip()
    if not raw:
        raw = (config.get("GENERAL", {}) or {}).get("telegram_shorts_news_path", "") or ""
    raw = str(raw).strip()
    if not raw:
        return None
    p = Path(raw).expanduser()
    return p if p.is_dir() else None


class TelegramPublisher:
    """Простой Telegram Publisher для замены YouTube"""

    def __init__(self, config: dict):
        self.config = config
        self.publisher = None

        root = _resolve_shorts_news_root(config)
        if root is not None:
            scripts = root / "scripts"
            if scripts.is_dir():
                sp = str(scripts.resolve())
                if sp not in sys.path:
                    sys.path.insert(0, sp)
                try:
                    from telegram_publisher import TelegramPublisher as BaseTelegramPublisher

                    cfg_yaml = root / "config" / "config.yaml"
                    if cfg_yaml.is_file():
                        self.publisher = BaseTelegramPublisher(str(cfg_yaml))
                        logger.info("🚀 Используем улучшенный Telegram Publisher (%s)", root)
                    else:
                        logger.warning(
                            "⚠️ shorts_news: нет %s — расширенный publisher не создан",
                            cfg_yaml,
                        )
                except ImportError as e:
                    logger.warning("Enhanced Telegram Publisher unavailable: %s", e)
                except Exception as e:
                    logger.error("❌ Ошибка создания улучшенного publisher: %s", e)
                    self.publisher = None
            else:
                logger.warning("⚠️ shorts_news scripts не найдены: %s", scripts)
        else:
            logger.info(
                "📝 Улучшенный publisher: задайте telegram_shorts_news_path или TELEGRAM_SHORTS_NEWS_PATH"
            )

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
