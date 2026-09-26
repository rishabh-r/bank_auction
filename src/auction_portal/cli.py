"""Command line interface.

python -m auction_portal fetch <url> --source-id <id>
python -m auction_portal stats
python -m auction_portal config
"""

import argparse
import sys

from auction_portal.archiver import Archiver
from auction_portal.config import get_settings
from auction_portal.fetching.models import FetchOutcome
from auction_portal.logging_setup import configure_logging

_OUTCOME_LABEL = {
    FetchOutcome.NEW: "NEW        content archived",
    FetchOutcome.UNCHANGED: "UNCHANGED  identical to last fetch, nothing stored",
    FetchOutcome.NOT_MODIFIED: "304        server says unchanged, body not downloaded",
    FetchOutcome.BLOCKED_BY_ROBOTS: "BLOCKED    robots.txt disallows this URL",
    FetchOutcome.FAILED: "FAILED     see error below",
}


def _cmd_fetch(args: argparse.Namespace) -> int:
    settings = get_settings()
    settings.ensure_directories()

    with Archiver(settings) as archiver:
        result = archiver.archive(args.url, source_id=args.source_id)

    print()
    print(f"  url      : {result.url}")
    print(f"  outcome  : {_OUTCOME_LABEL[result.outcome]}")
    if result.document:
        print(f"  type     : {result.document.mime_type.split(';')[0]}")
        print(f"  size     : {result.document.size_bytes:,} bytes")
        print(f"  sha256   : {result.document.sha256}")
    if result.storage_key:
        print(f"  stored   : {settings.raw_dir / result.storage_key}")
    if result.error:
        print(f"  error    : {result.error}")
    print()

    return 0 if result.outcome is not FetchOutcome.FAILED else 1


def _cmd_stats(args: argparse.Namespace) -> int:
    settings = get_settings()
    settings.ensure_directories()

    with Archiver(settings) as archiver:
        print()
        print(f"  archive      : {settings.raw_dir}")
        print(f"  documents    : {archiver.store.count():,}")
        print(f"  urls tracked : {len(archiver.state):,}")
        print()
    return 0


def _cmd_config(args: argparse.Namespace) -> int:
    s = get_settings()
    print()
    print(f"  environment    : {s.environment}")
    print(f"  data dir       : {s.data_dir}")
    print(f"  crawl delay    : {s.crawler_delay_seconds}s")
    print(f"  timeout        : {s.crawler_timeout_seconds}s")
    print(f"  max retries    : {s.crawler_max_retries}")
    print(f"  respect robots : {s.crawler_respect_robots}")
    print(f"  openai key set : {s.openai_api_key is not None}")
    print(f"  user agent     : {s.user_agent}")
    print()
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="auction_portal",
        description="Centralised search portal for Indian bank auction listings.",
    )
    parser.add_argument("-v", "--verbose", action="store_true", help="debug logging")
    sub = parser.add_subparsers(dest="command", required=True)

    fetch = sub.add_parser("fetch", help="fetch and archive one URL")
    fetch.add_argument("url")
    fetch.add_argument(
        "--source-id",
        default="manual",
        help="which source this belongs to, e.g. 'ibbi' (default: manual)",
    )
    fetch.set_defaults(func=_cmd_fetch)

    stats = sub.add_parser("stats", help="show archive statistics")
    stats.set_defaults(func=_cmd_stats)

    config = sub.add_parser("config", help="show loaded configuration")
    config.set_defaults(func=_cmd_config)

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    configure_logging("DEBUG" if args.verbose else None)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
