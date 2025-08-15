"""
Twitter/X Upload Service
Публикация контента в Twitter/X через API v2

Требования:
1. Twitter Developer Account (бесплатно)
2. App credentials (API Key, Secret, Access Token)
3. tweepy библиотека

Функционал:
- Публикация текста с хештегами (FREE)
- Публикация изображений (FREE) 
- Публикация видео (Basic $100/мес)
"""

import logging
import os
from pathlib import Path
from typing import Optional
import tempfile

logger = logging.getLogger("twitter")

try:
    import tweepy
    TWEEPY_AVAILABLE = True
except ImportError:
    TWEEPY_AVAILABLE = False
    logger.warning("📦 tweepy не установлен. Используйте: pip install tweepy")


class TwitterUploader:
    """Загрузчик контента в Twitter/X."""
    
    def __init__(self, config: dict):
        self.config = config
        self.twitter_config = config.get('TWITTER', {})
        self.enabled = self.twitter_config.get('enabled', 'false').lower() == 'true'
        
        if not self.enabled:
            logger.info("📴 Twitter интеграция отключена")
            return
            
        if not TWEEPY_AVAILABLE:
            logger.error("❌ tweepy не установлен! Отключаем Twitter интеграцию")
            self.enabled = False
            return
            
        # Проверяем наличие ключей
        required_keys = ['api_key', 'api_secret', 'access_token', 'access_token_secret']
        missing_keys = [key for key in required_keys if not self.twitter_config.get(key)]
        
        if missing_keys:
            logger.error(f"❌ Отсутствуют Twitter ключи: {missing_keys}")
            self.enabled = False
            return
            
        try:
            # Инициализация Twitter API v2
            self.client = tweepy.Client(
                consumer_key=self.twitter_config['api_key'],
                consumer_secret=self.twitter_config['api_secret'],
                access_token=self.twitter_config['access_token'],
                access_token_secret=self.twitter_config['access_token_secret'],
                wait_on_rate_limit=True
            )
            
            # Для загрузки медиа нужен API v1.1
            auth = tweepy.OAuth1UserHandler(
                self.twitter_config['api_key'],
                self.twitter_config['api_secret'],
                self.twitter_config['access_token'],
                self.twitter_config['access_token_secret']
            )
            self.api_v1 = tweepy.API(auth, wait_on_rate_limit=True)
            
            # Проверяем подключение
            self._verify_credentials()
            logger.info("✅ Twitter API подключен успешно")
            
        except Exception as e:
            logger.error(f"❌ Ошибка подключения к Twitter API: {e}")
            self.enabled = False
    
    def _verify_credentials(self):
        """Проверяет валидность учетных данных."""
        try:
            user = self.client.get_me()
            logger.info(f"🐦 Подключен как: @{user.data.username}")
        except Exception as e:
            raise Exception(f"Неверные учетные данные Twitter: {e}")
    
    def _prepare_text(self, title: str, description: str, tags: list) -> str:
        """Подготавливает текст для Twitter (максимум 280 символов)."""
        # Конвертируем теги в хештеги
        hashtags = []
        for tag in tags[:5]:  # Максимум 5 хештегов
            clean_tag = ''.join(c for c in tag if c.isalnum() or c in 'абвгдеёжзийклмнопрстуфхцчшщъыьэюя')
            if clean_tag:
                hashtags.append(f"#{clean_tag}")
        
        hashtag_text = " ".join(hashtags)
        
        # Рассчитываем доступное место для основного текста
        available_length = 280 - len(hashtag_text) - 3  # 3 символа для пробелов
        
        # Используем title как основной текст
        main_text = title
        if len(main_text) > available_length:
            main_text = main_text[:available_length-3] + "..."
        
        # Собираем итоговый текст
        if hashtag_text:
            result = f"{main_text}\n\n{hashtag_text}"
        else:
            result = main_text
            
        logger.info(f"📝 Подготовлен текст для Twitter ({len(result)} символов)")
        return result
    
    def _extract_video_frame(self, video_path: str) -> Optional[str]:
        """Извлекает кадр из видео для использования как изображение."""
        try:
            from moviepy import VideoFileClip
            import tempfile
            
            with VideoFileClip(video_path) as video:
                # Берем кадр из середины видео
                frame_time = video.duration / 2
                frame = video.get_frame(frame_time)
                
                # Сохраняем как изображение
                from PIL import Image
                img = Image.fromarray(frame)
                
                # Создаем временный файл
                temp_file = tempfile.NamedTemporaryFile(suffix='.jpg', delete=False)
                img.save(temp_file.name, quality=90)
                temp_file.close()
                
                logger.info("🖼️ Извлечен кадр из видео для Twitter")
                return temp_file.name
                
        except Exception as e:
            logger.error(f"❌ Ошибка извлечения кадра: {e}")
            return None
    
    def upload_post(self, 
                   title: str, 
                   description: str = "", 
                   tags: list = None, 
                   video_path: str = None,
                   image_path: str = None) -> bool:
        """
        Публикует пост в Twitter.
        
        Args:
            title: Заголовок поста
            description: Описание (не используется из-за лимита символов)
            tags: Список тегов для хештегов
            video_path: Путь к видео (требует Basic план $100/мес)
            image_path: Путь к изображению (бесплатно)
        
        Returns:
            bool: True если успешно опубликовано
        """
        if not self.enabled:
            logger.warning("📴 Twitter загрузка отключена")
            return False
            
        try:
            tags = tags or []
            text = self._prepare_text(title, description, tags)
            
            media_ids = []
            temp_files = []
            
            # Определяем тип контента
            upload_mode = self.twitter_config.get('upload_mode', 'image')  # 'image', 'video', 'auto'
            
            if upload_mode == 'video' and video_path and Path(video_path).exists():
                # Загрузка видео (требует Basic план)
                try:
                    logger.info("🎬 Загружаем видео в Twitter...")
                    media = self.api_v1.media_upload(video_path, media_category='tweet_video')
                    media_ids.append(media.media_id)
                    logger.info("✅ Видео загружено")
                except Exception as e:
                    logger.error(f"❌ Ошибка загрузки видео: {e}")
                    logger.info("🔄 Переключаемся на изображение...")
                    # Извлекаем кадр как fallback
                    temp_image = self._extract_video_frame(video_path)
                    if temp_image:
                        temp_files.append(temp_image)
                        image_path = temp_image
                        
            if not media_ids and (upload_mode in ['image', 'auto'] or not video_path):
                # Загрузка изображения (бесплатно)
                target_image = image_path
                
                # Если нет изображения, но есть видео - извлекаем кадр
                if not target_image and video_path:
                    target_image = self._extract_video_frame(video_path)
                    if target_image:
                        temp_files.append(target_image)
                
                if target_image and Path(target_image).exists():
                    try:
                        logger.info("🖼️ Загружаем изображение в Twitter...")
                        media = self.api_v1.media_upload(target_image)
                        media_ids.append(media.media_id)
                        logger.info("✅ Изображение загружено")
                    except Exception as e:
                        logger.error(f"❌ Ошибка загрузки изображения: {e}")
            
            # Публикуем пост
            logger.info("📤 Публикуем пост в Twitter...")
            
            tweet_kwargs = {'text': text}
            if media_ids:
                tweet_kwargs['media_ids'] = media_ids
                
            response = self.client.create_tweet(**tweet_kwargs)
            
            if response.data:
                tweet_id = response.data['id']
                tweet_url = f"https://twitter.com/i/web/status/{tweet_id}"
                logger.info(f"✅ Пост опубликован: {tweet_url}")
                
                # Очищаем временные файлы
                for temp_file in temp_files:
                    try:
                        os.unlink(temp_file)
                    except:
                        pass
                        
                return True
            else:
                logger.error("❌ Ошибка публикации: нет данных в ответе")
                return False
                
        except Exception as e:
            logger.error(f"❌ Ошибка публикации в Twitter: {e}")
            
            # Очищаем временные файлы при ошибке
            for temp_file in temp_files:
                try:
                    os.unlink(temp_file)
                except:
                    pass
                    
            return False
    
    def get_account_info(self) -> dict:
        """Возвращает информацию об аккаунте Twitter."""
        if not self.enabled:
            return {'error': 'Twitter интеграция отключена'}
            
        try:
            user = self.client.get_me(user_fields=['public_metrics'])
            return {
                'username': user.data.username,
                'name': user.data.name,
                'followers': user.data.public_metrics['followers_count'],
                'following': user.data.public_metrics['following_count'],
                'tweets': user.data.public_metrics['tweet_count']
            }
        except Exception as e:
            return {'error': str(e)}
