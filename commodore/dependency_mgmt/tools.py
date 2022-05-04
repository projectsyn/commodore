from __future__ import annotations

from collections.abc import Iterable
from typing import Callable


def format_component_list(
    components: Iterable[str], format_func: Callable[[str], str] = lambda c: f"'{c}'"
) -> str:
    formatted_list = list(map(format_func, sorted(components)))

    if len(formatted_list) == 0:
        return ""

    if len(formatted_list) == 1:
        return f"{formatted_list[0]}"

    formatted = ", ".join(formatted_list[:-1])

    # Use serial ("Oxford") comma when formatting lists of 3 or more items, cf.
    # https://en.wikipedia.org/wiki/Serial_comma
    serial_comma = ""
    if len(formatted_list) > 2:
        serial_comma = ","

    formatted += f"{serial_comma} and {formatted_list[-1]}"

    return formatted
