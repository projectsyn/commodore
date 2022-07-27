from __future__ import annotations

import json
import os

from pathlib import Path
from typing import Any

import click
from xdg.BaseDirectory import xdg_cache_home

cache_name = Path(xdg_cache_home) / "commodore" / "token"


def save(lieutenant: str, token: dict[str, Any]):
    try:
        with open(cache_name, "r", encoding="utf-8") as f:
            cache = json.load(f)
    except (IOError, FileNotFoundError):
        cache = {}
    except json.JSONDecodeError:
        click.secho(" > Dropping invalid JSON for token cache", fg="yellow")
        cache = {}

    cache[lieutenant] = token

    os.makedirs(os.path.dirname(cache_name), exist_ok=True)
    with open(cache_name, "w", encoding="utf-8") as f:
        f.write(json.dumps(cache, indent=1))


def get(lieutenant: str) -> dict[str, Any]:
    try:
        with open(cache_name, "r", encoding="utf-8") as f:
            cache = json.load(f)
    except (IOError, FileNotFoundError, json.JSONDecodeError):
        return {}
    data = cache.get(lieutenant, {})
    if isinstance(data, str):
        data = {}
    return data
