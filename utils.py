from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from config import get_setting


def timezone_name() -> str:
    return get_setting("TIMEZONE", "Asia/Kolkata")


def local_now() -> datetime:
    return datetime.now(ZoneInfo(timezone_name()))


def local_today():
    return local_now().date()


def safe_filename(filename: str) -> str:
    suffix = Path(filename).suffix.lower()
    if suffix not in {".jpg", ".jpeg", ".png"}:
        suffix = ".jpg"
    stem = re.sub(r"[^a-zA-Z0-9_-]+", "-", Path(filename).stem).strip("-")[:50] or "image"
    return f"{stem}{suffix}"
