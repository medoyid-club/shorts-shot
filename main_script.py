import asyncio
import logging
import os
from pathlib import Path

from services.config_loader import load_config
from services.video_factory import create_video_generator, create_llm_provider
from services.telegram_monitor import start_telegram_watcher
from services.youtube_uploader import YouTubeUploader
from services.twitter_uploader import TwitterUploader
from services.telegram_publisher import TelegramPublisher
from services.storage import ensure_directories
from services.logger_config import setup_logging, log_system_info, log_config_info, create_log_viewer_script
logger = logging.getLogger("main")


async def process_message(text: str | None, media_path: str | None, config: dict, uploader: YouTubeUploader, composer, twitter: TwitterUploader = None, telegram_publisher: TelegramPublisher = None):
    if not text:
        logger.info("Message has no text. Using default text for video.")
        text = "Новини"  # Fallback текст

    llm = create_llm_provider(config)
    
    # Проверяем версию генератора для выбора формата LLM
    generator_version = config['VIDEO'].get('generator_version', 'v1').lower()
    
    # Сбрасываем состояние API ключей для нового сообщения (только для V1)
    if hasattr(llm, 'reset_for_new_message'):
        llm.reset_for_new_message()

    # Task 2: ЕДИНЫЙ запрос к LLM — получаем весь пакет (контент + SEO)
    try:
        source_url = config['VIDEO'].get('source_text', '')
        source_name = config['TELEGRAM'].get('channel', '')
        pkg = await llm.generate_video_package(text, source_name=source_name, source_url=source_url)
        video_content = pkg.get('video_content', {}) if isinstance(pkg, dict) else {}
        seo_pkg = pkg.get('seo_package', {}) if isinstance(pkg, dict) else {}

        # short_text для компоновки V2
        short_text = {
            'title': video_content.get('title', text[:120] if text else 'Новини'),
            'brief': video_content.get('summary', '')
        }

        # SEO для YouTube
        title = (seo_pkg.get('youtube_title') or video_content.get('title') or '').strip() or (text[:70] + '...' if len(text) > 70 else text)
        description = (seo_pkg.get('youtube_description') or '').strip()
        tags = seo_pkg.get('tags') or []
        if isinstance(tags, str):
            tags = [t.strip() for t in tags.split(',') if t.strip()]
        # Минимум 5, максимум 15
        base_tags = ['новини', 'news', 'shorts']
        tags = list(dict.fromkeys([*tags, *base_tags]))[:15]
        if len(tags) < 5:
            tags += ['updates', 'video', 'world']
            tags = tags[:15]
        seo = {'title': title, 'description': description, 'tags': tags}
        logger.info("SEO package (1-call) ready: title='%s'", seo['title'][:60])
    except Exception as e:
        logger.error("LLM package generation failed: %s. Falling back.", e)
        # Fallback short_text
        short_text = text[:200] + "..." if len(text) > 200 else text
        # Fallback SEO
        text_lower = (text or "").lower()
        if "путін" in text_lower or "putin" in text_lower:
            title_base = "Путін та геополітика"
        elif "трамп" in text_lower or "trump" in text_lower:
            title_base = "Трамп та американська політика"
        elif "україн" in text_lower or "ukrain" in text_lower:
            title_base = "Новини України"
        elif "алясці" in text_lower or "alaska" in text_lower:
            title_base = "Готелі на Алясці підняли ціни"
        elif "готел" in text_lower or "hotel" in text_lower:
            title_base = "Готельний бізнес та ціни"
        else:
            title_base = "Новини: " + (text[:40] if text else "Останні події")
        seo = {
            'title': title_base[:65],
            'description': '',
            'tags': ['новини', 'україна', 'політика', 'світ', 'news', 'ukraine', 'politics', 'world', 'shorts', 'відео', 'готелі', 'аляска']
        }

    # Step 3: Video generation
    output_dir = Path(config['PATHS']['outputs_dir'])
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"short_{int(asyncio.get_event_loop().time()*1000)}.mp4"

    video_path = await composer.compose(
        short_text=short_text,
        media_path=media_path,
        output_path=str(output_path),
        source_text=config['VIDEO'].get('source_text', 't.me/source')
    )
    logger.info("Video composed: %s", video_path)

    # Step 4: Upload to YouTube or Telegram
    upload_to_telegram = config.get('GENERAL', {}).get('upload_to_telegram', False)

    if upload_to_telegram and telegram_publisher and telegram_publisher.is_available():
        # Публикация в Telegram
        logger.info("📢 Публикуем в Telegram канал...")
        telegram_success = await telegram_publisher.upload_video(
            video_path=str(video_path),
            title=seo.get('title', 'News Update'),
            description=seo.get('description', ''),
            tags=seo.get('tags', [])
        )
        if telegram_success:
            logger.info("✅ Telegram публикация завершена")
        else:
            logger.error("❌ Ошибка публикации в Telegram")
    else:
        # Публикация на YouTube
        logger.info("📺 Публикуем на YouTube...")
        uploader.upload_video(
            video_file=str(video_path),
            title=seo.get('title', 'News Update'),
            description=seo.get('description', ''),
            tags=seo.get('tags', []),
            category_id=config['YOUTUBE'].get('category_id', '25'),
            privacy_status=config['YOUTUBE'].get('privacy_status', 'public')
        )
        logger.info("✅ YouTube загрузка завершена")
    
    # Step 5: Upload to Twitter (если включено)
    if twitter and twitter.enabled:
        try:
            twitter_success = twitter.upload_post(
                title=seo.get('title', 'News Update'),
                description=seo.get('description', ''),
                tags=seo.get('tags', []),
                video_path=str(video_path)
            )
            if twitter_success:
                logger.info("Twitter upload complete")
            else:
                logger.warning("Twitter upload failed")
        except Exception as e:
            logger.error(f"Twitter upload error: {e}")
    else:
        logger.info("Twitter upload skipped (disabled or not configured)")
        
    logger.info("All uploads complete")


async def main():
    project_root = Path(__file__).parent
    os.chdir(project_root)
    
    # Настройка логирования
    setup_logging(log_dir="logs", log_level="INFO")
    create_log_viewer_script()
    
    # Логируем информацию о системе
    log_system_info()
    
    config = load_config(project_root)
    
    # Логируем конфигурацию
    log_config_info(config)
    
    ensure_directories(config)

    # Создаем генератор видео через фабрику (автоматически выбирает V1 или V2)
    composer = create_video_generator(config)
    uploader = YouTubeUploader(config)

    # Инициализируем Telegram Publisher
    try:
        telegram_publisher = TelegramPublisher(config)
        if telegram_publisher.is_available():
            logger.info("✅ Telegram Publisher инициализирован")
        else:
            logger.warning("⚠️ Telegram Publisher недоступен")
            telegram_publisher = None
    except Exception as e:
        logger.warning(f"⚠️ Ошибка инициализации Telegram Publisher: {e}. Продолжаем без Telegram.")
        telegram_publisher = None

    # Инициализируем Twitter с обработкой ошибок
    try:
        twitter = TwitterUploader(config)
    except Exception as e:
        logger.warning(f"⚠️ Ошибка инициализации Twitter: {e}. Продолжаем без Twitter.")
        twitter = None

    logger.info("🚀 Starting Telegram watcher...")

    message_queue: asyncio.Queue[tuple[str | None, str | None]] = asyncio.Queue()

    async def queue_worker():
        while True:
            text, media_path = await message_queue.get()
            try:
                logger.info("🧵 Processing queued message. Queue size=%s", message_queue.qsize())
                await process_message(text, media_path, config, uploader, composer, twitter, telegram_publisher)
            except Exception as e:
                logger.exception("❌ Failed to process queued message: %s", e)
            finally:
                message_queue.task_done()

    asyncio.create_task(queue_worker())

    async def handler(text: str | None, media_path: str | None):
        await message_queue.put((text, media_path))
        logger.info("📥 Message queued. Queue size=%s", message_queue.qsize())

    await start_telegram_watcher(config, handler)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("🛑 Stopped by user")
    except Exception as e:
        logger.exception("💥 Fatal error: %s", e)

