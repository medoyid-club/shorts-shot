import asyncio
import logging
import os
from pathlib import Path

from services.config_loader import load_config
from services.llm_provider import create_llm_provider
from services.telegram_monitor import start_telegram_watcher
from services.video_generator import VideoComposer
from services.youtube_uploader import YouTubeUploader
from services.twitter_uploader import TwitterUploader
from services.storage import ensure_directories
from services.logger_config import setup_logging, log_system_info, log_config_info, create_log_viewer_script
logger = logging.getLogger("main")


async def process_message(text: str | None, media_path: str | None, config: dict, uploader: YouTubeUploader, composer: VideoComposer, twitter: TwitterUploader = None):
    if not text:
        logger.info("Message has no text. Using default text for video.")
        text = "Новини"  # Fallback текст

    llm = create_llm_provider(config)
    # Сбрасываем состояние API ключей для нового сообщения
    llm.reset_for_new_message()

    # Task 2.1: Summarize for middle text
    try:
        short_text = await llm.summarize_for_video(text)
        logger.info("Short text generated")
    except Exception as e:
        logger.error("LLM summarization failed: %s. Using original text.", e)
        # Обрезаем оригинальный текст до разумной длины
        short_text = text[:200] + "..." if len(text) > 200 else text

    # Task 2.2: SEO JSON package
    try:
        seo = await llm.generate_seo_package(text)
        # Пост-валидация
        title = (seo.get('title') or '').strip()
        if not title:
            title = (text[:70] + '...') if len(text) > 70 else text
        
        # Добавляем 3 хештега в конец заголовка
        tags_temp = seo.get('tags', [])
        if isinstance(tags_temp, str):
            tags_temp = [t.strip() for t in tags_temp.split(',') if t.strip()]
        
        if tags_temp:
            # Берем первые 3 тега для заголовка
            title_hashtags = [f"#{tag.replace(' ', '')}" for tag in tags_temp[:3]]
            title_with_hashtags = f"{title} {' '.join(title_hashtags)}"
            
            # Если превышает лимит, сокращаем основной заголовок
            if len(title_with_hashtags) > 90:
                max_title_len = 90 - len(' '.join(title_hashtags)) - 1
                title = title[:max_title_len].rstrip() + "..."
                title = f"{title} {' '.join(title_hashtags)}"
            else:
                title = title_with_hashtags
        elif len(title) > 70:
            title = title[:69].rstrip() + '…'

        # Описание — максимум 2 коротких речення або пусто
        description = (seo.get('description') or '').strip()
        # Если пусто — сформируем из тегов видимые хештеги как описание
        if not description:
            pass
        else:
            description = description.replace('\n\n', '\n').strip()
            if len(description) > 280:
                description = description[:279].rstrip() + '…'

        tags = seo.get('tags') or []
        if isinstance(tags, str):
            tags = [t.strip() for t in tags.split(',') if t.strip()]
        # Минимум 5, максимум 15
        base_tags = ['новини', 'news', 'shorts']
        tags = list(dict.fromkeys([*tags, *base_tags]))[:15]
        if len(tags) < 5:
            tags += ['updates', 'video', 'world']
            tags = tags[:15]

        # Если описания нет — добавим хештеги в description (5 штук)
        if not description:
            hash_tags = [f"#{t.replace(' ', '')}" for t in tags[:5]]
            description = " ".join(hash_tags)

        seo = {'title': title, 'description': description, 'tags': tags}
        logger.info("SEO package normalized: title='%s'", seo['title'][:60])
    except Exception as e:
        logger.error("LLM SEO generation failed: %s. Using fallback SEO data.", e)
        # Создаем более качественный fallback заголовок
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

    # Step 4: Upload to YouTube
    uploader.upload_video(
        video_file=str(video_path),
        title=seo.get('title', 'News Update'),
        description=seo.get('description', ''),
        tags=seo.get('tags', []),
        category_id=config['YOUTUBE'].get('category_id', '25'),
        privacy_status=config['YOUTUBE'].get('privacy_status', 'public')
    )
    logger.info("YouTube upload complete")
    
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

    composer = VideoComposer(config)
    uploader = YouTubeUploader(config)
    
    # Инициализируем Twitter с обработкой ошибок
    try:
        twitter = TwitterUploader(config)
    except Exception as e:
        logger.warning(f"⚠️ Ошибка инициализации Twitter: {e}. Продолжаем без Twitter.")
        twitter = None

    logger.info("🚀 Starting Telegram watcher...")

    async def handler(text: str | None, media_path: str | None):
        try:
            await process_message(text, media_path, config, uploader, composer, twitter)
        except Exception as e:
            logger.exception("❌ Failed to process message: %s", e)

    await start_telegram_watcher(config, handler)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("🛑 Stopped by user")
    except Exception as e:
        logger.exception("💥 Fatal error: %s", e)

