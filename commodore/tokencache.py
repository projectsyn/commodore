import os
from typing import Optional
from pathlib import Path
import json

cache_name = "{home}/.cache/commodore/token".format(home=Path.home())


def save(lieutenant: str, token: str):
    try:
        with open(cache_name, "r") as f:
            cache = json.load(f)
    except (IOError, FileNotFoundError):
        cache = {}

    cache[lieutenant] = token

    os.makedirs(os.path.dirname(cache_name), exist_ok=True)
    with open(cache_name, "w") as f:
        f.write(json.dumps(cache, indent=1))


def get(lieutenant: str) -> Optional[str]:
    try:
        with open(cache_name, "r") as f:
            cache = json.load(f)
    except (IOError, FileNotFoundError):
        return
    return cache[lieutenant]
