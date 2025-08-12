from __future__ import annotations

import os
from pathlib import Path
import random


def ensure_directories(config: dict) -> None:
    for key in ('music_dir', 'backgrounds_dir', 'outputs_dir', 'tmp_dir', 'state_dir'):
        path = Path(config['PATHS'][key])
        path.mkdir(parents=True, exist_ok=True)


def random_file(directory: str, exts: tuple[str, ...]) -> str | None:
    d = Path(directory)
    if not d.exists():
        return None
    files = [p for p in d.iterdir() if p.is_file() and p.suffix.lower() in exts]
    if not files:
        return None
    return str(random.choice(files))


def build_temp_path(config: dict, filename: str) -> str:
    return str((Path(config['PATHS']['tmp_dir']) / filename).resolve())

