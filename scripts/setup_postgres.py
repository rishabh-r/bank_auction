"""Set up a project-local PostgreSQL server on Windows.

Downloads the official portable PostgreSQL binaries, initialises a data
directory inside the project, and starts the server on a non-default port.

Why portable rather than the normal installer:
  - no administrator rights and no Windows service
  - completely contained in .pgsql/, so deleting that folder resets everything
  - cannot collide with any other PostgreSQL on the machine (port 5433)

Everything it creates is git-ignored. Safe to delete and re-run.

    python scripts/setup_postgres.py            # download, init, start
    python scripts/setup_postgres.py --start    # start an existing cluster
    python scripts/setup_postgres.py --stop
    python scripts/setup_postgres.py --status
"""

import argparse
import os
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

import httpx

PROJECT_ROOT = Path(__file__).resolve().parents[1]
PG_ROOT = PROJECT_ROOT / ".pgsql"
PG_BIN = PG_ROOT / "pgsql" / "bin"
PG_DATA = PG_ROOT / "data"
PG_LOG = PG_ROOT / "server.log"
ARCHIVE = PG_ROOT / "postgresql-binaries.zip"

PG_VERSION = "17.11-4"
DOWNLOAD_URL = (
    f"https://get.enterprisedb.com/postgresql/postgresql-{PG_VERSION}-windows-x64-binaries.zip"
)

# EnterpriseDB rejects non-browser user agents with HTTP 403.
BROWSER_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/140.0 Safari/537.36"
)

PORT = 5433
SUPERUSER = "postgres"
PASSWORD = "devpassword"  # local development only; never used in production
APP_DATABASE = "auction_portal"
TEST_DATABASE = "auction_portal_test"


def download() -> None:
    if (PG_BIN / "pg_ctl.exe").exists():
        print("[skip] binaries already present")
        return

    PG_ROOT.mkdir(parents=True, exist_ok=True)

    if not ARCHIVE.exists():
        print(f"[1/2] downloading PostgreSQL {PG_VERSION} (~362 MB)")
        with httpx.stream(
            "GET",
            DOWNLOAD_URL,
            headers={"User-Agent": BROWSER_UA},
            follow_redirects=True,
            timeout=120.0,
        ) as response:
            response.raise_for_status()
            total = int(response.headers.get("content-length", 0))
            written = 0
            tmp = ARCHIVE.with_suffix(".part")
            with tmp.open("wb") as handle:
                for chunk in response.iter_bytes(chunk_size=1 << 20):
                    handle.write(chunk)
                    written += len(chunk)
                    if total:
                        pct = written * 100 // total
                        print(f"\r      {pct:3d}%  {written / 1048576:6.0f} MB", end="")
            print()
            tmp.replace(ARCHIVE)

    print("[2/2] extracting")
    with zipfile.ZipFile(ARCHIVE) as archive:
        archive.extractall(PG_ROOT)
    ARCHIVE.unlink(missing_ok=True)


def initdb() -> None:
    if (PG_DATA / "PG_VERSION").exists():
        print("[skip] data directory already initialised")
        return

    print("[init] creating data directory")
    PG_DATA.mkdir(parents=True, exist_ok=True)

    pwfile = PG_ROOT / "pw.txt"
    pwfile.write_text(PASSWORD, encoding="utf-8")
    try:
        run(
            [
                PG_BIN / "initdb.exe",
                "-D",
                PG_DATA,
                "-U",
                SUPERUSER,
                f"--pwfile={pwfile}",
                "-E",
                "UTF8",
                "--locale=C",
            ]
        )
    finally:
        pwfile.unlink(missing_ok=True)

    # Listen only on loopback. This server is for local development.
    conf = PG_DATA / "postgresql.conf"
    conf.write_text(
        conf.read_text(encoding="utf-8")
        + f"\n# project settings\nport = {PORT}\nlisten_addresses = 'localhost'\n",
        encoding="utf-8",
    )


def start() -> None:
    if is_running():
        print("[skip] server already running")
        return
    print(f"[start] starting server on port {PORT}")
    run([PG_BIN / "pg_ctl.exe", "-D", PG_DATA, "-l", PG_LOG, "-w", "start"])


def stop() -> None:
    if not is_running():
        print("[skip] server not running")
        return
    print("[stop] stopping server")
    run([PG_BIN / "pg_ctl.exe", "-D", PG_DATA, "-m", "fast", "-w", "stop"])


def is_running() -> bool:
    if not (PG_BIN / "pg_isready.exe").exists():
        return False
    result = subprocess.run(
        [str(PG_BIN / "pg_isready.exe"), "-p", str(PORT), "-h", "localhost"],
        capture_output=True,
    )
    return result.returncode == 0


def create_databases() -> None:
    env = {**os.environ, "PGPASSWORD": PASSWORD}
    for name in (APP_DATABASE, TEST_DATABASE):
        exists = subprocess.run(
            [
                str(PG_BIN / "psql.exe"),
                "-U",
                SUPERUSER,
                "-p",
                str(PORT),
                "-h",
                "localhost",
                "-d",
                "postgres",
                "-tAc",
                f"SELECT 1 FROM pg_database WHERE datname='{name}'",
            ],
            capture_output=True,
            text=True,
            env=env,
        )
        if exists.stdout.strip() == "1":
            print(f"[skip] database {name} exists")
            continue
        print(f"[db]   creating {name}")
        run(
            [
                PG_BIN / "createdb.exe",
                "-U",
                SUPERUSER,
                "-p",
                str(PORT),
                "-h",
                "localhost",
                name,
            ],
            env=env,
        )


def run(cmd: list, env: dict | None = None) -> None:
    result = subprocess.run([str(part) for part in cmd], capture_output=True, text=True, env=env)
    if result.returncode != 0:
        sys.exit(f"command failed: {' '.join(str(c) for c in cmd)}\n{result.stderr}")


def status() -> None:
    running = is_running()
    print(f"  binaries : {'present' if (PG_BIN / 'pg_ctl.exe').exists() else 'missing'}")
    print(f"  data dir : {'initialised' if (PG_DATA / 'PG_VERSION').exists() else 'missing'}")
    print(f"  server   : {'running' if running else 'stopped'} (port {PORT})")
    if running:
        print()
        print("  DATABASE_URL for .env:")
        print(f"    postgresql+psycopg://{SUPERUSER}:{PASSWORD}@localhost:{PORT}/{APP_DATABASE}")


def reset() -> None:
    """Delete everything. The whole point of a project-local server."""
    stop()
    shutil.rmtree(PG_ROOT, ignore_errors=True)
    print("[reset] removed .pgsql/")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--start", action="store_true")
    group.add_argument("--stop", action="store_true")
    group.add_argument("--status", action="store_true")
    group.add_argument("--reset", action="store_true")
    args = parser.parse_args()

    if args.status:
        status()
    elif args.stop:
        stop()
    elif args.reset:
        reset()
    elif args.start:
        start()
        status()
    else:
        download()
        initdb()
        start()
        create_databases()
        print()
        status()


if __name__ == "__main__":
    main()
