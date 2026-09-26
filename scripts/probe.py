"""Dump every JSON object found in a page's Next.js flight payload."""

import json
import re
import sys

import httpx

UA = {"User-Agent": ("AuctionPortalBot/0.1 (+https://example.com/bot; rishabh.raj1209@gmail.com)")}
FLIGHT = re.compile(r"self\.__next_f\.push\(\[\d+,\s*(\".*?\")\]\)", re.DOTALL)


def payload_of(html: str) -> str:
    parts = []
    for raw in FLIGHT.findall(html):
        try:
            parts.append(json.loads(raw))
        except json.JSONDecodeError:
            continue
    return "".join(parts)


def objects_in(payload: str, min_fields: int = 4) -> list[dict]:
    """Scan for balanced {...} regions and keep those that parse as objects."""
    results, index, length = [], 0, len(payload)
    while index < length:
        if payload[index] != "{":
            index += 1
            continue
        depth, in_string, escape = 0, False, False
        end = index
        for position in range(index, min(index + 60000, length)):
            char = payload[position]
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
                    end = position
                    break
        else:
            index += 1
            continue

        try:
            obj = json.loads(payload[index : end + 1])
        except json.JSONDecodeError:
            index += 1
            continue

        if isinstance(obj, dict) and len(obj) >= min_fields:
            results.append(obj)
            index = end + 1
        else:
            index += 1
    return results


def main(url: str) -> None:
    html = httpx.get(url, headers=UA, follow_redirects=True, timeout=60).text
    payload = payload_of(html)
    print(f"{url}\n  payload: {len(payload):,} chars\n")

    for number, obj in enumerate(objects_in(payload), start=1):
        keys = list(obj)
        print(f"--- object {number}: {len(keys)} fields ---")
        print("  " + ", ".join(keys[:40]))
        if any(k in obj for k in ("reservePrice", "propertyId", "stateName", "bankName")):
            print(json.dumps(obj, indent=2, ensure_ascii=False)[:2500])
        print()


if __name__ == "__main__":
    main(sys.argv[1])
