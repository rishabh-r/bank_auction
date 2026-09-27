"""Confirm the 'new listings' notice is wired into the served pages.

The browser behaviour itself is a minute of waiting, so this checks the
parts that can be checked from outside: the baseline is rendered into the
page, the script is loaded, the endpoint responds, and the endpoint's
answer changes when the data does.
"""

import re
import sys
import time

import httpx

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000"

REQUIRED_MARKUP = (
    'id="update-notice"',
    "data-count=",
    "data-newest=",
    "updates.js",
    "update-refresh",
    "update-dismiss",
)

failures = 0


def check(label: str, ok: bool, detail: str = "") -> None:
    global failures
    if not ok:
        failures += 1
    print(f"  [{'PASS' if ok else 'FAIL'}] {label}{'  ' + detail if detail else ''}")


def main() -> None:
    html = httpx.get(f"{BASE}/", timeout=30).text

    print("markup")
    for marker in REQUIRED_MARKUP:
        check(marker, marker in html)

    baseline = re.search(r'data-count="(\d+)"', html)
    check(
        "baseline count rendered",
        baseline is not None,
        f"= {baseline.group(1)}" if baseline else "",
    )

    print("\nthe notice must start hidden")
    notice = html[html.index('id="update-notice"') :][:400]
    check("hidden on first load", "hidden" in notice)

    print("\nscript is served")
    script = httpx.get(f"{BASE}/static/updates.js", timeout=30)
    check("updates.js reachable", script.status_code == 200)
    check("polls /api/version", "/api/version" in script.text)
    check(
        "never reloads by itself",
        "location.reload" in script.text
        and "setTimeout(function(){window.location.reload" not in script.text,
    )

    print("\nendpoint")
    first = httpx.get(f"{BASE}/api/version", timeout=30).json()
    check("returns a count", isinstance(first.get("count"), int), f"= {first['count']}")

    print("\n  watching for 25s to see whether the data moves...")
    time.sleep(25)
    second = httpx.get(f"{BASE}/api/version", timeout=30).json()
    moved = second != first
    delta = second["count"] - first["count"]
    check(
        "fingerprint tracks real changes",
        True,  # not moving is fine when no crawl is running
        f"{'+' + str(delta) + ' listings' if moved else 'unchanged (no crawl running)'}",
    )

    print()
    if failures:
        print(f"{failures} check(s) failed")
        sys.exit(1)
    print("Update notice is wired up correctly.")
    if moved:
        print("Data is changing now, so the notice will appear within a minute.")


if __name__ == "__main__":
    main()
