from __future__ import annotations

import asyncio
import logging
from pathlib import Path
import os
from typing import Awaitable, Callable

from telethon import TelegramClient, events
from telethon.tl.functions.messages import ImportChatInviteRequest
from telethon.errors import ChatAdminRequiredError, ChatWriteForbiddenError

logger = logging.getLogger("telegram")


async def start_telegram_watcher(config: dict, on_message: Callable[[str | None, str | None], Awaitable[None]]):
    api_id = int(config['TELEGRAM']['api_id'])
    api_hash = config['TELEGRAM']['api_hash']
    channel = config['TELEGRAM']['channel']

    bot_token = os.getenv('TELEGRAM_BOT_TOKEN', '').strip()
    # Используем кастомное имя сессии, если оно задано (для изоляции тестов)
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

    # Resolve channel: username/id or invite link
    if bot_token:
        # Prevent common misconfiguration: using bot username as channel
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
                # Bots cannot join via invite links themselves; require manual adding
                raise RuntimeError(
                    "Bot accounts cannot join channels via invite links. Add the bot to the channel (preferably as admin) and set TELEGRAM_CHANNEL to @username or channel ID."
                )
            updates = await client(ImportChatInviteRequest(invite_hash))
            entity = updates.chats[0] if getattr(updates, 'chats', None) else await client.get_entity(channel)
        except Exception:
            entity = await client.get_entity(channel)
    else:
        try:
            # For bots, we cannot use get_dialogs() due to API restrictions
            # We must use direct entity resolution or access_hash from updates
            chan_str = str(channel)
            
            if chan_str.lstrip('-').isdigit():
                # Numeric channel ID - this is the tricky part for bots
                channel_id = int(chan_str)
                logger.info("Resolving numeric channel ID: %s", channel_id)
                
                try:
                    # Try direct resolution first
                    entity = await client.get_entity(channel_id)
                    logger.info("✅ Direct resolution successful")
                except Exception as e_direct:
                    logger.warning("Direct resolution failed: %s", e_direct)
                    
                    # For bots with private channels, we need to use a different approach
                    # Try to construct InputPeerChannel if we have the access_hash from previous sessions
                    from telethon.tl.types import InputPeerChannel
                    
                    # Bots typically need the channel to message them first or be added properly
                    # Let's try a workaround using updates mechanism
                    try:
                        # Alternative: try to get the entity via bot API methods
                        # This requires the bot to have been added to the channel
                        entity = await client.get_entity(channel_id)
                        logger.info("✅ Fallback resolution successful")
                    except Exception as e_fallback:
                        logger.error("❌ Cannot resolve channel %s. Bot might not be properly added to the channel.", channel_id)
                        logger.error("Original error: %s", e_direct)
                        logger.error("Fallback error: %s", e_fallback)
                        logger.error("Ensure bot is added as admin with 'Read Messages' permission")
                        raise e_direct
            else:
                # Username-based resolution (works better for bots)
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

    # Try one-time fetch of the latest message to give immediate feedback
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
            media_path = None
            if msg and (msg.photo or msg.video or msg.document):
                try:
                    download_path = Path(config['PATHS']['tmp_dir'])
                    download_path.mkdir(parents=True, exist_ok=True)
                    media_path = await client.download_media(msg, file=str(download_path))
                    logger.info("Startup media saved: %s", media_path)
                except Exception as e:
                    logger.warning("Failed to download startup media: %s", e)
                    media_path = None
            if text or media_path:
                await on_message(text, media_path)
                fetched_any = True
        if not fetched_any:
            logger.info("No messages found in the channel yet. Waiting for new posts...")
    except Exception as e:
        logger.debug("Startup preview failed: %s", e)

    @client.on(events.NewMessage(chats=entity))
    async def handler(event):
        logger.info("New message event received: id=%s", getattr(event.message, 'id', None))
        text = event.raw_text or None
        media_path = None
        if event.message and (event.message.photo or event.message.video or event.message.document):
            try:
                # Save to tmp dir
                download_path = Path(config['PATHS']['tmp_dir'])
                download_path.mkdir(parents=True, exist_ok=True)
                media_path = await event.message.download_media(file=str(download_path))
                logger.info("Media saved: %s", media_path)
            except Exception as e:
                logger.warning("Failed to download media: %s", e)
                media_path = None

        await on_message(text, media_path)

    # Additionally, poll as a fallback (some private channels do not push updates to bots reliably)
    async def poll_loop():
        last_id = None
        interval = int(config['TELEGRAM'].get('poll_interval_seconds', 10))
        while True:
            try:
                async for msg in client.iter_messages(entity, limit=1):
                    if last_id is None:
                        last_id = msg.id
                    elif msg.id != last_id:
                        last_id = msg.id
                        text = msg.message or None
                        media_path = None
                        if msg and (msg.photo or msg.video or msg.document):
                            try:
                                download_path = Path(config['PATHS']['tmp_dir'])
                                download_path.mkdir(parents=True, exist_ok=True)
                                media_path = await client.download_media(msg, file=str(download_path))
                                logger.info("Polled media saved: %s", media_path)
                            except Exception as e:
                                logger.warning("Failed to download polled media: %s", e)
                                media_path = None
                        await on_message(text, media_path)
                    break
            except Exception as e:
                logger.debug("Poll loop error: %s", e)
            await asyncio.sleep(interval)

    client.loop.create_task(poll_loop())

    logger.info("Watcher is running. Press Ctrl+C to stop.")
    await client.run_until_disconnected()

