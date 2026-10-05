"""Sanity-check docker-compose.yml before deploying to a remote machine.

Finding a typo here costs seconds; finding it after a ten-minute ARM
build on a server you just provisioned does not.
"""

import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]

REQUIRED_SERVICES = ("postgres:", "web:", "scheduler:", "caddy:")
REQUIRED_VOLUMES = ("pgdata", "archive", "caddy_data", "caddy_config", "caddy_logs")
REQUIRED_ENV = ("POSTGRES_PASSWORD", "CONTACT_EMAIL", "CONTACT_URL", "SITE_ADDRESS")

failures = 0


def check(label: str, ok: bool, detail: str = "") -> None:
    global failures
    if not ok:
        failures += 1
    print(f"  [{'PASS' if ok else 'FAIL'}] {label}{'  ' + detail if detail else ''}")


def main() -> None:
    compose = (ROOT / "docker-compose.yml").read_text("utf-8")
    caddyfile = (ROOT / "Caddyfile").read_text("utf-8")

    print("services")
    for service in REQUIRED_SERVICES:
        check(service.rstrip(":"), service in compose)

    print("\nvolumes declared and used")
    for volume in REQUIRED_VOLUMES:
        check(volume, compose.count(volume) >= 2)

    print("\nrequired settings are mandatory, not silently defaulted")
    for name in REQUIRED_ENV:
        check(name, f"${{{name}:?" in compose or f"${{{name}}}" in compose)

    print("\nthe app is not exposed directly")
    check(
        "web has no host port mapping",
        '"8000:8000"' not in compose,
        "Caddy should be the only way in",
    )
    check("caddy publishes 80 and 443", '"80:80"' in compose and '"443:443"' in compose)

    print("\nreverse proxy")
    check("proxies to the web service", "reverse_proxy web:8000" in caddyfile)
    check("uses SITE_ADDRESS", "{$SITE_ADDRESS}" in caddyfile)
    check("certificates persist", "caddy_data:/data" in compose)

    print("\nimages are multi-arch (Oracle's free machines are ARM)")
    for image in ("postgres:17-alpine", "caddy:2-alpine"):
        check(image, image in compose)
    check(
        "python:3.12-slim",
        "python:3.12-slim" in (ROOT / "Dockerfile").read_text("utf-8"),
    )

    print()
    if failures:
        print(f"{failures} check(s) failed")
        sys.exit(1)
    print("Compose configuration looks deployable.")


if __name__ == "__main__":
    main()
