from __future__ import annotations

import asyncio
import logging
from pathlib import Path
import os
from typing import Awaitable, Callable, List, Optional, Union

from telethon import TelegramClient, events
from telethon.tl.functions.messages import ImportChatInviteRequest

logger = logging.getLogger("telegram")

MediaPath = Union[str, List[str], None]
OnMessage = Callable[[Optional[str], MediaPath], Awaitable[None]]

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}
MAX_ALBUM_ITEMS = 8


def _twitter_media_enabled(config: dict) -> bool:
    section = config.get("TWITTER_MEDIA") or {}
    return str(section.get("enabled", "true")).strip().lower() in ("1", "true", "yes", "on")


def _has_media(media_path: MediaPath) -> bool:
    if not media_path:
        return False
    if isinstance(media_path, list):
        return len(media_path) > 0
    return True


async def _maybe_ingest_twitter(
    text: str | None,
    media_path: MediaPath,
    config: dict,
) -> tuple[str | None, MediaPath]:
    """
    X/Twitter status link in Telegram → download tweet media (if no attachment)
    and enrich message text from the tweet body for the LLM.
    """
    if not _twitter_media_enabled(config):
        return text, media_path
    try:
        from services.twitter_media_downloader import (
            extract_twitter_status_url,
            download_twitter_media,
            fetch_tweet_meta,
            merge_tweet_text_into_message,
        )
    except Exception as e:
        logger.warning("Twitter media module unavailable: %s", e)
        return text, media_path

    url = extract_twitter_status_url(text)
    if not url:
        return text, media_path

    section = config.get("TWITTER_MEDIA") or {}
    tmp_dir = config.get("PATHS", {}).get("tmp_dir", "resources/tmp")
    max_dur = float(section.get("max_duration_seconds", 600) or 600)
    cookies = (section.get("cookies_file") or "").strip() or None

    if _has_media(media_path):
        ingest = await asyncio.to_thread(fetch_tweet_meta, url, cookies)
        if ingest.tweet_text:
            logger.info("🐦 Текст твита добавлен (медиа уже из Telegram)")
        return merge_tweet_text_into_message(text, ingest), media_path

    ingest = await asyncio.to_thread(
        download_twitter_media,
        url,
        tmp_dir,
        max_duration_sec=max_dur,
        cookies_file=cookies,
    )
    new_text = merge_tweet_text_into_message(text, ingest)
    if ingest.media_path:
        logger.info("🐦 Медиа из X/Twitter: %s", ingest.media_path)
    else:
        logger.warning("🐦 Ссылка на X найдена, медиа не скачалось (проверьте yt-dlp)")
    return new_text, ingest.media_path


def _tmp_dir(config: dict) -> Path:
    download_path = Path(config["PATHS"]["tmp_dir"])
    download_path.mkdir(parents=True, exist_ok=True)
    return download_path


async def _download_one(client, msg, download_path: Path) -> Optional[str]:
    if not msg or not (msg.photo or msg.video or msg.document):
        return None
    try:
        path = await client.download_media(msg, file=str(download_path))
        return str(path) if path else None
    except Exception as e:
        logger.warning("Failed to download media: %s", e)
        return None


async def _download_album(client, messages, download_path: Path) -> MediaPath:
    """Download album items (prefer images); return list or single path."""
    paths: List[str] = []
    for msg in sorted(messages, key=lambda m: m.id)[:MAX_ALBUM_ITEMS]:
        p = await _download_one(client, msg, download_path)
        if p:
            paths.append(p)
    if not paths:
        return None
    if len(paths) == 1:
        return paths[0]
    logger.info("🖼️ Альбом Telegram: %s файлов", len(paths))
    return paths


async def _collect_album_by_grouped_id(client, entity, grouped_id, seed_msg=None):
    """Gather all messages with the same grouped_id (for poll/backfill)."""
    found = []
    if seed_msg is not None:
        found.append(seed_msg)
    async for m in client.iter_messages(entity, limit=40):
        if m.grouped_id == grouped_id:
            if seed_msg is None or m.id != seed_msg.id:
                found.append(m)
    # unique by id
    by_id = {m.id: m for m in found}
    return sorted(by_id.values(), key=lambda m: m.id)


async def start_telegram_watcher(config: dict, on_message: OnMessage):
    api_id = int(config['TELEGRAM']['api_id'])
    api_hash = config['TELEGRAM']['api_hash']
    channel = config['TELEGRAM']['channel']

    bot_token = os.getenv('TELEGRAM_BOT_TOKEN', '').strip()
    custom_session = os.getenv('TELEGRAM_SESSION_NAME', '').strip()
    if custom_session:
        session_file = custom_session
    else:
        session_file = 'telethon_session_bot' if bot_token else 'telethon_session'
    session_name = str(Path(config['PATHS']['state_dir']) / session_file)
    client = TelegramClient(session_name, api_id, api_hash)

    if bot_token:
        await client.start(bot_token=bot_token)
        me = await client.get_me()
        bot_username = f"@{getattr(me, 'username', '')}".lower()
        logger.info("Connected to Telegram as bot %s", bot_username or "<unknown>")
    else:
        await client.start()
        logger.info("Connected to Telegram")

    if bot_token:
        try:
            me = await client.get_me()
            my_name = f"@{getattr(me, 'username', '')}".lower()
            if isinstance(channel, str) and channel.lower() == my_name:
                raise RuntimeError(
                    "TELEGRAM_CHANNEL указывает на имя бота. Укажите @username или ID канала, где бот добавлен (желательно админ)."
                )
        except Exception:
            pass

    if isinstance(channel, str) and ('t.me/+' in channel or 'https://t.me/+' in channel):
        invite_hash = channel.split('t.me/+', 1)[-1].replace('/', '').strip()
        try:
            if bot_token:
                raise RuntimeError(
                    "Bot accounts cannot join channels via invite links. Add the bot to the channel (preferably as admin) and set TELEGRAM_CHANNEL to @username or channel ID."
                )
            updates = await client(ImportChatInviteRequest(invite_hash))
            entity = updates.chats[0] if getattr(updates, 'chats', None) else await client.get_entity(channel)
        except Exception:
            entity = await client.get_entity(channel)
    else:
        try:
            chan_str = str(channel)

            if chan_str.lstrip('-').isdigit():
                channel_id = int(chan_str)
                logger.info("Resolving numeric channel ID: %s", channel_id)

                try:
                    entity = await client.get_entity(channel_id)
                    logger.info("✅ Direct resolution successful")
                except Exception as e_direct:
                    logger.warning("Direct resolution failed: %s", e_direct)
                    try:
                        entity = await client.get_entity(channel_id)
                        logger.info("✅ Fallback resolution successful")
                    except Exception as e_fallback:
                        logger.error("❌ Cannot resolve channel %s. Bot might not be properly added to the channel.", channel_id)
                        logger.error("Original error: %s", e_direct)
                        logger.error("Fallback error: %s", e_fallback)
                        logger.error("Ensure bot is added as admin with 'Read Messages' permission")
                        raise e_direct
            else:
                logger.info("Resolving username: %s", chan_str)
                entity = await client.get_entity(chan_str)
                logger.info("✅ Username resolution successful")

        except Exception as e:
            logger.error("Failed to resolve TELEGRAM_CHANNEL='%s': %s", channel, e)
            logger.error("For bots with private channels:")
            logger.error("1. Ensure bot is added as admin")
            logger.error("2. Grant 'Read Messages' permission")
            logger.error("3. Consider using @username instead of numeric ID")
            raise
    logger.info("Listening to channel: %s (resolved id=%s, title=%s)", channel, getattr(entity, 'id', '<unknown>'), getattr(entity, 'title', None))

    async def _emit(text: str | None, media_path: MediaPath):
        text, media_path = await _maybe_ingest_twitter(text, media_path, config)
        if text or _has_media(media_path):
            await on_message(text, media_path)

    # Startup backfill
    try:
        me = await client.get_me()
        try:
            perms = await client.get_permissions(entity, me)
            is_admin = bool(getattr(perms, 'is_admin', False))
            logger.info("Channel access: admin=%s", is_admin)
        except Exception:
            pass

        backfill = int(config.get('TELEGRAM', {}).get('startup_backfill', 1)) if isinstance(config, dict) else 1
        fetched_any = False
        async for msg in client.iter_messages(entity, limit=max(1, backfill)):
            text = msg.message or None
            media_path: MediaPath = None
            download_path = _tmp_dir(config)
            if msg and getattr(msg, 'grouped_id', None):
                album = await _collect_album_by_grouped_id(client, entity, msg.grouped_id, msg)
                text = next((m.message for m in album if m.message), text)
                media_path = await _download_album(client, album, download_path)
            elif msg and (msg.photo or msg.video or msg.document):
                media_path = await _download_one(client, msg, download_path)
                if media_path:
                    logger.info("Startup media saved: %s", media_path)
            if text or _has_media(media_path):
                await _emit(text, media_path)
                fetched_any = True
        if not fetched_any:
            logger.info("No messages found in the channel yet. Waiting for new posts...")
    except Exception as e:
        logger.debug("Startup preview failed: %s", e)

    @client.on(events.Album(chats=entity))
    async def album_handler(event):
        """Несколько фото/видео одним постом (media group)."""
        logger.info(
            "New album event: grouped_id=%s items=%s",
            getattr(event, 'grouped_id', None),
            len(event.messages),
        )
        text = event.text or None
        media_path = await _download_album(client, event.messages, _tmp_dir(config))
        await _emit(text, media_path)

    @client.on(events.NewMessage(chats=entity))
    async def handler(event):
        # Альбомы обрабатывает events.Album — не дублируем
        if event.message and getattr(event.message, 'grouped_id', None):
            return
        logger.info("New message event received: id=%s", getattr(event.message, 'id', None))
        text = event.raw_text or None
        media_path = None
        if event.message and (event.message.photo or event.message.video or event.message.document):
            media_path = await _download_one(client, event.message, _tmp_dir(config))
            if media_path:
                logger.info("Media saved: %s", media_path)
        await _emit(text, media_path)

    async def poll_loop():
        last_id = None
        seen_groups: set = set()
        interval = int(config['TELEGRAM'].get('poll_interval_seconds', 10))
        while True:
            try:
                async for msg in client.iter_messages(entity, limit=1):
                    if last_id is None:
                        last_id = msg.id
                    elif msg.id != last_id:
                        last_id = msg.id
                        text = msg.message or None
                        media_path: MediaPath = None
                        download_path = _tmp_dir(config)
                        gid = getattr(msg, 'grouped_id', None)
                        if gid:
                            if gid in seen_groups:
                                break
                            seen_groups.add(gid)
                            if len(seen_groups) > 50:
                                seen_groups.clear()
                            album = await _collect_album_by_grouped_id(client, entity, gid, msg)
                            text = next((m.message for m in album if m.message), text)
                            media_path = await _download_album(client, album, download_path)
                        elif msg.photo or msg.video or msg.document:
                            media_path = await _download_one(client, msg, download_path)
                            if media_path:
                                logger.info("Polled media saved: %s", media_path)
                        await _emit(text, media_path)
                    break
            except Exception as e:
                logger.debug("Poll loop error: %s", e)
            await asyncio.sleep(interval)

    client.loop.create_task(poll_loop())

    logger.info("Watcher is running. Press Ctrl+C to stop.")
    await client.run_until_disconnected()
