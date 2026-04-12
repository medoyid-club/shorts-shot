"""
Один локальный ролик в outputs/ (учитывает LOCAL_ONLY и v2_sandbox_template_path).
Запуск из корня проекта: python local_test_short.py
"""
from __future__ import annotations

import asyncio
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent
os.chdir(ROOT)

from services.config_loader import load_config
from services.logger_config import setup_logging
from services.video_factory import create_video_generator
from main_script import process_message, _is_local_only


SAMPLE_TEXT = (
    "Тестовий короткий випуск: місцеві власті повідомили про оновлення тарифів "
    "на електроенергію для малого бізнесу з наступного кварталу."
)


async def main() -> None:
    setup_logging(log_dir="logs", log_level="INFO")
    config = load_config(ROOT)
    composer = create_video_generator(config)
    uploader = None
    if not _is_local_only(config):
        from services.youtube_uploader import YouTubeUploader

        uploader = YouTubeUploader(config)
    await process_message(SAMPLE_TEXT, None, config, uploader, composer, None, None)


if __name__ == "__main__":
    asyncio.run(main())
