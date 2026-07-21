"""
Ingest media from X/Twitter status links (for Telegram → Shorts → YouTube).

Not related to TwitterUploader (outbound posting). Uses yt-dlp like shorts_news.
"""

from __future__ import annotations

import json
import logging
import re
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

logger = logging.getLogger("twitter_media")

# status URLs only (not profile / home)
TWITTER_STATUS_RE = re.compile(
    r"https?://(?:www\.|mobile\.)?(?:twitter\.com|x\.com)/[^/\s]+/status/(\d+)",
    re.IGNORECASE,
)
# strip trailing punctuation from chat paste
_TRAIL_PUNCT_RE = re.compile(r"[)\],.;!?»\"']+$")


@dataclass
class TwitterIngestResult:
    media_path: Optional[str]
    tweet_text: Optional[str]
    tweet_url: str
    uploader: Optional[str] = None


def is_twitter_media_enabled(config: dict) -> bool:
    section = config.get("TWITTER_MEDIA") or {}
    return str(section.get("enabled", "true")).strip().lower() in ("1", "true", "yes", "on")


def extract_twitter_status_url(text: str | None) -> Optional[str]:
    if not text:
        return None
    m = TWITTER_STATUS_RE.search(text)
    if not m:
        return None
    raw = m.group(0)
    raw = _TRAIL_PUNCT_RE.sub("", raw)
    # Normalize to x.com https
    tweet_id = m.group(1)
    user = re.search(r"(?:twitter\.com|x\.com)/([^/\s]+)/status/", raw, re.I)
    handle = user.group(1) if user else "i"
    return f"https://x.com/{handle}/status/{tweet_id}"


def _ytdlp_base_cmd(cookies_file: str | None = None) -> list[str]:
    cmd = [
        "yt-dlp",
        "--no-playlist",
        "--socket-timeout", "60",
        "--retries", "2",
        "--no-check-certificate",
        "--user-agent",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "--extractor-args", "twitter:api=syndication",
    ]
    if cookies_file and Path(cookies_file).is_file():
        cmd.extend(["--cookies", cookies_file])
    return cmd


def _dump_tweet_info(tweet_url: str, cookies_file: str | None = None) -> Optional[dict]:
    cmd = _ytdlp_base_cmd(cookies_file) + ["--dump-json", tweet_url]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=45)
    except FileNotFoundError:
        logger.error("❌ yt-dlp не найден. Установите: pip install yt-dlp")
        return None
    except subprocess.TimeoutExpired:
        logger.warning("⚠️ yt-dlp --dump-json timeout")
        return None
    if result.returncode != 0:
        logger.warning("⚠️ yt-dlp dump-json failed: %s", (result.stderr or "")[:300])
        return None
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError:
        logger.warning("⚠️ yt-dlp dump-json: невалидный JSON")
        return None


def _pick_tweet_text(info: dict) -> Optional[str]:
    for key in ("description", "fulltitle", "title", "alt_title"):
        val = (info.get(key) or "").strip()
        if val and val.lower() not in ("x", "twitter", "video by"):
            # Drop generic "X" / username-only titles when description exists later
            if key == "title" and len(val) < 8:
                continue
            return val
    return None


def download_twitter_media(
    tweet_url: str,
    out_dir: str | Path,
    *,
    max_duration_sec: float = 600.0,
    cookies_file: str | None = None,
) -> TwitterIngestResult:
    """
    Download best video (or image) from a tweet status URL into out_dir.
    """
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)

    info = _dump_tweet_info(tweet_url, cookies_file)
    tweet_text = _pick_tweet_text(info) if info else None
    uploader = (info.get("uploader") or info.get("channel") or None) if info else None

    if info:
        duration = float(info.get("duration") or 0)
        if duration > max_duration_sec:
            logger.warning("⚠️ Twitter видео слишком длинное (%.1fs), пропускаем", duration)
            return TwitterIngestResult(None, tweet_text, tweet_url, uploader)

    stamp = int(time.time() * 1000)
    # Let yt-dlp choose extension (mp4 / webm / jpg…)
    out_tmpl = str(out / f"twitter_{stamp}.%(ext)s")

    cmd = _ytdlp_base_cmd(cookies_file) + [
        "--format", "bv*+ba/b",
        "--merge-output-format", "mp4",
        "-o", out_tmpl,
        tweet_url,
    ]
    logger.info("🎬 Скачиваем медиа из X/Twitter: %s", tweet_url)

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
    except FileNotFoundError:
        logger.error("❌ yt-dlp не найден. Установите: pip install yt-dlp")
        return TwitterIngestResult(None, tweet_text, tweet_url, uploader)
    except subprocess.TimeoutExpired:
        logger.error("❌ yt-dlp timeout при скачивании %s", tweet_url)
        return TwitterIngestResult(None, tweet_text, tweet_url, uploader)

    # Find newest twitter_{stamp}.* in out_dir
    matches = sorted(out.glob(f"twitter_{stamp}.*"), key=lambda p: p.stat().st_mtime, reverse=True)
    # Ignore .part leftovers
    matches = [p for p in matches if p.suffix.lower() != ".part" and p.is_file()]

    if not matches:
        # Sometimes format merge names differently — take any recent twitter_* 
        logger.warning(
            "⚠️ yt-dlp не сохранил файл (code=%s): %s",
            result.returncode,
            (result.stderr or result.stdout or "")[:400],
        )
        return TwitterIngestResult(None, tweet_text, tweet_url, uploader)

    media_path = str(matches[0])
    logger.info("✅ Twitter медиа сохранено: %s", media_path)
    if tweet_text:
        logger.info("📝 Текст твита: %s…", tweet_text[:80].replace("\n", " "))
    return TwitterIngestResult(media_path, tweet_text, tweet_url, uploader)


def fetch_tweet_meta(tweet_url: str, cookies_file: str | None = None) -> TwitterIngestResult:
    """Metadata only (no media download) — for when Telegram already has an attachment."""
    info = _dump_tweet_info(tweet_url, cookies_file)
    tweet_text = _pick_tweet_text(info) if info else None
    uploader = (info.get("uploader") or info.get("channel") or None) if info else None
    return TwitterIngestResult(None, tweet_text, tweet_url, uploader)


def resolve_twitter_from_telegram_text(
    text: str | None,
    config: dict,
) -> Optional[TwitterIngestResult]:
    """If TWITTER_MEDIA enabled and text has a status URL — download media + tweet body."""
    if not is_twitter_media_enabled(config):
        return None
    url = extract_twitter_status_url(text)
    if not url:
        return None

    section = config.get("TWITTER_MEDIA") or {}
    tmp_dir = config.get("PATHS", {}).get("tmp_dir", "resources/tmp")
    max_dur = float(section.get("max_duration_seconds", 600) or 600)
    cookies = (section.get("cookies_file") or "").strip() or None

    return download_twitter_media(
        url,
        tmp_dir,
        max_duration_sec=max_dur,
        cookies_file=cookies,
    )


def merge_tweet_text_into_message(telegram_text: str | None, ingest: TwitterIngestResult) -> str:
    """Prefer tweet body for LLM; keep Telegram caption if it adds context."""
    tg = (telegram_text or "").strip()
    tweet = (ingest.tweet_text or "").strip()
    parts: list[str] = []
    if tweet:
        who = f"@{ingest.uploader}" if ingest.uploader else "X/Twitter"
        parts.append(f"{who}: {tweet}")
    # Keep non-URL telegram caption lines
    if tg:
        cleaned = TWITTER_STATUS_RE.sub("", tg).strip()
        cleaned = re.sub(r"\s+", " ", cleaned).strip(" -—\n")
        if cleaned and cleaned not in (tweet or ""):
            parts.append(cleaned)
    if not parts:
        return tg or ingest.tweet_url
    return "\n\n".join(parts)
