"""Reading server-rendered data out of Next.js pages.

Next.js App Router streams the data a page was rendered from to the browser
as a sequence of `self.__next_f.push([1, "<json fragment>"])` calls.
Concatenating the fragments recovers the original payload, which contains
the same structured records the page displays.

This is preferable to scraping the rendered HTML: we read the source data
rather than reverse-engineering its presentation, so a visual redesign does
not break the adapter.
"""

import json
import re
from typing import Any

_FLIGHT_PUSH = re.compile(r"self\.__next_f\.push\(\[\d+,\s*(\".*?\")\]\)", re.DOTALL)

# An object larger than this is not a record we care about, and scanning it
# is wasted work.
_MAX_OBJECT_CHARS = 200_000


def extract_payload(html: str) -> str:
    """Concatenate the streamed fragments back into one string."""
    fragments = []
    for raw in _FLIGHT_PUSH.findall(html):
        try:
            fragments.append(json.loads(raw))
        except json.JSONDecodeError:
            continue  # a fragment we cannot decode is not fatal
    return "".join(fragments)


def find_objects(payload: str, required_key: str) -> list[dict[str, Any]]:
    """Return every JSON object in the payload containing `required_key`.

    Works by locating the key, walking back to the enclosing '{', then
    forward counting brace depth while respecting string literals and
    escapes. Slower than a real parser but robust to the payload being a
    concatenation of fragments rather than one valid document.
    """
    results: list[dict[str, Any]] = []
    seen_spans: set[tuple[int, int]] = set()

    for match in re.finditer(re.escape(f'"{required_key}"'), payload):
        start = _enclosing_object_start(payload, match.start())
        if start is None:
            continue
        end = _matching_brace(payload, start)
        if end is None or (start, end) in seen_spans:
            continue
        seen_spans.add((start, end))
        try:
            obj = json.loads(payload[start : end + 1])
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict) and required_key in obj:
            results.append(obj)

    return results


def _enclosing_object_start(payload: str, key_position: int) -> int | None:
    """Walk back to the '{' that opens the object holding this key."""
    depth = 0
    for index in range(key_position, max(-1, key_position - _MAX_OBJECT_CHARS), -1):
        char = payload[index]
        if char == "}":
            depth += 1
        elif char == "{":
            if depth == 0:
                return index
            depth -= 1
    return None


def _matching_brace(payload: str, start: int) -> int | None:
    depth, in_string, escape = 0, False, False
    for index in range(start, min(start + _MAX_OBJECT_CHARS, len(payload))):
        char = payload[index]
        if escape:
            escape = False
            continue
        if char == "\\":
            escape = True
            continue
        if char == '"':
            in_string = not in_string
            continue
        if in_string:
            continue
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return index
    return None


def largest_object(payload: str, required_key: str) -> dict[str, Any] | None:
    """The richest object containing the key - usually the full record."""
    objects = find_objects(payload, required_key)
    return max(objects, key=len) if objects else None
