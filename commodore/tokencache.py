import json
import os

from pathlib import Path
from typing import Optional

from xdg.BaseDirectory import xdg_cache_home

cache_name = Path(xdg_cache_home) / "commodore" / "token"


def save(lieutenant: str, token: str):
    try:
        with open(cache_name, "r", encoding="utf-8") as f:
            cache = json.load(f)
    except (IOError, FileNotFoundError):
        cache = {}

    cache[lieutenant] = token

    os.makedirs(os.path.dirname(cache_name), exist_ok=True)
    with open(cache_name, "w", encoding="utf-8") as f:
        f.write(json.dumps(cache, indent=1))


def get(lieutenant: str) -> Optional[str]:
    try:
        with open(cache_name, "r", encoding="utf-8") as f:
            cache = json.load(f)
    except (IOError, FileNotFoundError):
        return None
    return cache.get(lieutenant)
