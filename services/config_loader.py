from __future__ import annotations

import os
from pathlib import Path
import configparser
from dotenv import load_dotenv


def _parse_rgb(rgb_str: str) -> tuple[int, int, int]:
    parts = [p.strip() for p in rgb_str.split(',') if p.strip()]
    if len(parts) != 3:
        return 0, 0, 0
    return tuple(int(p) for p in parts)  # type: ignore[return-value]


def _clean_external_env() -> None:
    # Ensure we don't inherit host-level keys; rely solely on .env
    for var in (
        'GEMINI_API_KEY',
        'GOOGLE_API_KEY',
        'GOOGLE_GENAI_USE_VERTEXAI',
    ):
        if var in os.environ:
            os.environ.pop(var, None)


def _find_client_secret_file(project_root: Path) -> str | None:
    # Prefer exact value from env; otherwise, try to auto-detect a client_secret_*.json in root
    for pattern in (
        'client_secret.json',
        'client_secret_*.json',
        '*client_secret*.json',
    ):
        for p in project_root.glob(pattern):
            if p.is_file():
                return str(p)
    return None


def load_config(project_root: Path) -> dict:
    env_path = project_root / '.env'
    _clean_external_env()
    if env_path.exists():
        # Force .env to override any pre-existing values
        load_dotenv(env_path, override=True)

    config = configparser.ConfigParser(interpolation=configparser.ExtendedInterpolation())
    config.read(project_root / 'config.ini', encoding='utf-8')

    # Overlay environment overrides
    # Telegram
    if os.getenv('TELEGRAM_API_ID'):
        config['TELEGRAM']['api_id'] = os.environ['TELEGRAM_API_ID']
    if os.getenv('TELEGRAM_API_HASH'):
        config['TELEGRAM']['api_hash'] = os.environ['TELEGRAM_API_HASH']
    if os.getenv('TELEGRAM_CHANNEL'):
        config['TELEGRAM']['channel'] = os.environ['TELEGRAM_CHANNEL']

    # LLM
    if os.getenv('GEMINI_API_KEY'):
        # Stored in env only
        pass

    # YouTube
    if os.getenv('YOUTUBE_CLIENT_SECRET_FILE'):
        config['YOUTUBE']['client_secret_file'] = os.environ['YOUTUBE_CLIENT_SECRET_FILE']
    if os.getenv('YOUTUBE_PRIVACY_STATUS'):
        config['YOUTUBE']['privacy_status'] = os.environ['YOUTUBE_PRIVACY_STATUS']

    # Video
    if os.getenv('VIDEO_DURATION_SECONDS'):
        config['VIDEO']['duration_seconds'] = os.environ['VIDEO_DURATION_SECONDS']

    # Derived helpers
    config['VIDEO']['width'] = config['VIDEO'].get('width', '1080')
    config['VIDEO']['height'] = config['VIDEO'].get('height', '1920')

    # Attach parsed items
    config._parsed = {  # type: ignore[attr-defined]
        'VIDEO': {
            'middle_bg_rgb': _parse_rgb(config['VIDEO'].get('middle_bg_rgb', '40,40,40')),
            'footer_bg_rgb': _parse_rgb(config['VIDEO'].get('footer_bg_rgb', '0,0,0')),
            'middle_red_rgb': _parse_rgb(config['VIDEO'].get('middle_red_rgb', '220,20,20')),
        }
    }

    # Finalize critical paths
    client_secret = config['YOUTUBE'].get('client_secret_file', '').strip()
    if not client_secret or client_secret.startswith('${'):
        auto = _find_client_secret_file(project_root)
        if auto:
            config['YOUTUBE']['client_secret_file'] = auto
        else:
            raise RuntimeError(
                "YouTube client secret file is not configured. Set YOUTUBE_CLIENT_SECRET_FILE in .env or "
                "update [YOUTUBE].client_secret_file in config.ini."
            )

    # Конвертируем ConfigParser в обычный dict для удобства использования
    result = {}
    for section_name in config.sections():
        section_dict = {}
        for key in config[section_name]:
            try:
                # Пытаемся получить значение с интерполяцией
                value = config[section_name][key]
                section_dict[key] = value
            except configparser.InterpolationMissingOptionError:
                # Если переменная не найдена, используем raw значение
                value = config[section_name].get(key, fallback='', raw=True)
                section_dict[key] = value
        result[section_name] = section_dict
    
    # Добавляем parsed данные
    result['_parsed'] = config._parsed  # type: ignore[attr-defined]
    
    return result

