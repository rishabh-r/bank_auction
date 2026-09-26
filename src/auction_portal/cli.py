"""Command line interface.

Running it
    serve          run the web portal
    schedule       run crawls and maintenance automatically

Collecting
    crawl <src>    fetch and parse a source
    reparse <src>  re-parse archived documents, no network access
    fetch <url>    archive a single document

Inspecting
    listings       browse stored listings
    stats          archive statistics
    health         report on source health
    dedup          report duplicates and re-auctions
    config         show loaded configuration
    db             check database connectivity

Maintenance
    maintain       advance statuses and apply retention, once
"""

import argparse
import sys
import time

from sqlalchemy import select, text

from auction_portal.archiver import Archiver
from auction_portal.config import get_settings
from auction_portal.crawler import Crawler
from auction_portal.db.listing_repository import ListingRepository
from auction_portal.db.models import Listing, SourceHealth
from auction_portal.db.repository import DocumentRepository
from auction_portal.db.session import session_scope
from auction_portal.dedup import DuplicateFinder
from auction_portal.fetching.client import Fetcher
from auction_portal.fetching.models import FetchOutcome
from auction_portal.logging_setup import configure_logging
from auction_portal.maintenance import (
    advance_statuses,
    check_health,
    expire_old,
    record_health,
)
from auction_portal.normalise.dates import to_ist
from auction_portal.normalise.money import format_inr
from auction_portal.scheduler import build_scheduler
from auction_portal.sources import REGISTRY

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

    with session_scope() as session:
        repo = DocumentRepository(session)
        per_source = repo.documents_per_source()
        recent = repo.recent_documents(limit=5)

        print()
        print(f"  archive      : {settings.raw_dir}")
        print(f"  database     : {settings.safe_database_url}")
        print(f"  documents    : {repo.count_documents():,}")
        print(f"  urls tracked : {repo.count_urls():,}")

        if per_source:
            print()
            print("  by source:")
            for source_id, count in per_source.items():
                print(f"    {source_id:<20} {count:>6,}")

        if recent:
            print()
            print("  most recent:")
            for doc in recent:
                print(
                    f"    {doc.fetched_at:%Y-%m-%d %H:%M}  {doc.source_id:<12} "
                    f"{doc.content_sha256[:12]}  {doc.source_url[:58]}"
                )
        print()
    return 0


def _cmd_db(args: argparse.Namespace) -> int:
    """Check database connectivity and migration state."""
    settings = get_settings()
    try:
        with session_scope() as session:
            version = session.execute(text("SELECT version()")).scalar_one()
            revision = session.execute(
                text("SELECT version_num FROM alembic_version")
            ).scalar_one_or_none()
            tables = session.execute(
                text(
                    "SELECT table_name FROM information_schema.tables "
                    "WHERE table_schema = 'public' ORDER BY table_name"
                )
            ).scalars()

            print()
            print(f"  url       : {settings.safe_database_url}")
            print(f"  server    : {version.split(',')[0]}")
            print(f"  migration : {revision or 'none applied'}")
            print(f"  tables    : {', '.join(tables)}")
            print()
    except Exception as exc:
        print()
        print(f"  cannot connect: {type(exc).__name__}: {exc}")
        print()
        print("  Is the local server running?")
        print("    python scripts/setup_postgres.py --status")
        print("    python scripts/setup_postgres.py --start")
        print()
        return 1
    return 0


def _cmd_config(args: argparse.Namespace) -> int:
    s = get_settings()
    print()
    print(f"  environment    : {s.environment}")
    print(f"  data dir       : {s.data_dir}")
    print(f"  database       : {s.safe_database_url}")
    print(f"  crawl delay    : {s.crawler_delay_seconds}s")
    print(f"  timeout        : {s.crawler_timeout_seconds}s")
    print(f"  max retries    : {s.crawler_max_retries}")
    print(f"  respect robots : {s.crawler_respect_robots}")
    print(f"  openai key set : {s.openai_api_key is not None}")
    print(f"  user agent     : {s.user_agent}")
    print()
    return 0


def _cmd_crawl(args: argparse.Namespace) -> int:
    settings = get_settings()
    settings.ensure_directories()

    fetcher = Fetcher(settings)

    def fetch_text(url: str) -> str:
        result = fetcher.fetch(url, source_id=args.source)
        if result.document is None:
            raise RuntimeError(f"could not fetch {url}: {result.error or result.outcome}")
        return result.document.content.decode("utf-8", errors="replace")

    adapter = REGISTRY[args.source](fetch_text=fetch_text)

    print(f"\n  crawling {adapter.display_name}, limit {args.limit}\n")
    started = time.monotonic()
    with Crawler(adapter, settings=settings) as crawler:
        report = crawler.run(limit=args.limit)
    fetcher.close()

    # Recorded here as well as in the scheduler, so a manual crawl counts
    # towards source health rather than looking like a gap.
    with session_scope() as session:
        record_health(session, report, duration_seconds=round(time.monotonic() - started, 2))

    print()
    print(f"  discovered        : {report.discovered:,}")
    print(f"  fetched           : {report.fetched:,}")
    print(f"  unchanged         : {report.unchanged:,}")
    print(f"  listings created  : {report.listings_created:,}")
    print(f"  listings updated  : {report.listings_updated:,}")
    print(f"  listings unchanged: {report.listings_unchanged:,}")
    if report.parse_failures:
        print(f"  parse failures    : {report.parse_failures:,}")
    if report.failed:
        print(f"  fetch failures    : {report.failed:,}")
    for error in report.errors[:5]:
        print(f"    {error[:110]}")
    print()
    return 0


def _cmd_reparse(args: argparse.Namespace) -> int:
    settings = get_settings()
    adapter = REGISTRY[args.source]()

    print(f"\n  reparsing archived {adapter.display_name} documents (offline)\n")
    with Crawler(adapter, settings=settings) as crawler:
        report = crawler.reparse(limit=args.limit)

    print()
    print(f"  documents read    : {report.discovered:,}")
    print(f"  parsed            : {report.fetched:,}")
    print(f"  listings created  : {report.listings_created:,}")
    print(f"  listings updated  : {report.listings_updated:,}")
    print(f"  listings unchanged: {report.listings_unchanged:,}")
    if report.parse_failures:
        print(f"  parse failures    : {report.parse_failures:,}")
    print()
    return 0


def _cmd_schedule(args: argparse.Namespace) -> int:
    scheduler = build_scheduler()

    print("\n  scheduled jobs:\n")
    for job in scheduler.get_jobs():
        print(f"    {job.id:<26} {job.name}")
    print()

    if args.dry_run:
        print("  dry run: nothing started\n")
        return 0

    print("  running. press Ctrl+C to stop.\n")
    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        print("\n  stopped\n")
    return 0


def _cmd_health(args: argparse.Namespace) -> int:
    with session_scope() as session:
        verdicts = check_health(session, sorted(REGISTRY))

        print()
        for verdict in verdicts:
            mark = "ok  " if verdict.ok else "FAIL"
            last = verdict.last_run.strftime("%d %b %H:%M") if verdict.last_run else "never"
            print(f"  [{mark}] {verdict.source_id:<20} {verdict.reason:<38} last run {last}")

        recent = session.scalars(
            select(SourceHealth).order_by(SourceHealth.ran_at.desc()).limit(8)
        ).all()
        if recent:
            print()
            print("  recent runs:")
            for row in recent:
                print(
                    f"    {row.ran_at:%d %b %H:%M}  {row.source_id:<18} "
                    f"found {row.discovered:>4}  fetched {row.fetched:>4}  "
                    f"new {row.listings_created:>4}  "
                    f"{'ok' if row.ok else 'FAILED'}"
                )
        print()

    return 0 if all(v.ok for v in verdicts) else 1


def _cmd_dedup(args: argparse.Namespace) -> int:
    with session_scope() as session:
        tally = DuplicateFinder(session).scan(limit=args.limit)

    print()
    print(f"  pairs examined     : {tally['compared']:,}")
    print(f"  likely duplicates  : {tally['duplicate']:,}")
    print(f"  re-auctions        : {tally['reauction']:,}")
    print(f"  needs review       : {tally['review']:,}")
    print()
    print("  Reported, not merged. A wrong merge destroys two listings and")
    print("  is far harder to notice than a missed one.")
    print()
    return 0


def _cmd_maintain(args: argparse.Namespace) -> int:
    with session_scope() as session:
        moved = advance_statuses(session)
        expired = expire_old(session)

    print()
    print(f"  upcoming -> live   : {moved['upcoming_to_live']:,}")
    print(f"  -> closed          : {moved['to_closed']:,}")
    print(f"  unpublished (aged) : {expired:,}")
    print()
    return 0


def _cmd_serve(args: argparse.Namespace) -> int:
    import uvicorn

    print(f"\n  portal running at http://{args.host}:{args.port}")
    print(f"  api docs at        http://{args.host}:{args.port}/api/docs")
    print("  press Ctrl+C to stop\n")

    uvicorn.run(
        "auction_portal.web.app:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
        log_level="info",
    )
    return 0


def _cmd_listings(args: argparse.Namespace) -> int:
    with session_scope() as session:
        repo = ListingRepository(session)
        stmt = select(Listing).order_by(Listing.auction_start_at.asc().nulls_last())
        if not args.all:
            stmt = stmt.where(Listing.is_published.is_(True))
        if args.state:
            stmt = stmt.where(Listing.state.ilike(f"%{args.state}%"))
        if args.city:
            stmt = stmt.where(Listing.city.ilike(f"%{args.city}%"))

        rows = list(session.scalars(stmt.limit(args.limit)))

        print()
        print(f"  total stored : {repo.count():,}")
        print(f"  published    : {repo.count(published_only=True):,}")
        print()

        if not rows:
            print("  no listings match")
            print()
            return 0

        for listing in rows:
            when = (
                to_ist(listing.auction_start_at).strftime("%d %b %Y %H:%M")
                if listing.auction_start_at
                else "date unknown"
            )
            print(f"  [{listing.external_id}] {listing.title or '(untitled)'}")
            print(
                f"      {listing.city or '?'}, {listing.state or '?'}"
                f"   {format_inr(listing.reserve_price)}"
                f"   EMD {format_inr(listing.emd_amount)}"
            )
            print(
                f"      auction {when}   {listing.possession_type or '?'} possession"
                f"   {listing.bank_name or 'bank unknown'}"
            )
            if listing.quality_flags:
                print(f"      flags: {', '.join(listing.quality_flags)}")
            print(f"      {listing.canonical_url}")
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

    db = sub.add_parser("db", help="check database connectivity and migrations")
    db.set_defaults(func=_cmd_db)

    crawl = sub.add_parser("crawl", help="run a source adapter end to end")
    crawl.add_argument("source", choices=sorted(REGISTRY), help="which source")
    crawl.add_argument("--limit", type=int, default=25, help="max URLs this run (default: 25)")
    crawl.set_defaults(func=_cmd_crawl)

    reparse = sub.add_parser(
        "reparse",
        help="re-run parsing over archived documents (no network access)",
    )
    reparse.add_argument("source", choices=sorted(REGISTRY))
    reparse.add_argument("--limit", type=int, default=None)
    reparse.set_defaults(func=_cmd_reparse)

    schedule = sub.add_parser(
        "schedule", help="run the scheduler; crawls and maintains automatically"
    )
    schedule.add_argument("--dry-run", action="store_true", help="list the jobs and exit")
    schedule.set_defaults(func=_cmd_schedule)

    health = sub.add_parser("health", help="report on source health")
    health.set_defaults(func=_cmd_health)

    dedup = sub.add_parser("dedup", help="report duplicate and re-auction relationships")
    dedup.add_argument("--limit", type=int, default=None)
    dedup.set_defaults(func=_cmd_dedup)

    maintain = sub.add_parser("maintain", help="run maintenance jobs once (statuses, retention)")
    maintain.set_defaults(func=_cmd_maintain)

    serve = sub.add_parser("serve", help="run the web portal")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8000)
    serve.add_argument("--reload", action="store_true", help="reload on code changes")
    serve.set_defaults(func=_cmd_serve)

    listings = sub.add_parser("listings", help="show stored auction listings")
    listings.add_argument("--limit", type=int, default=10)
    listings.add_argument("--state")
    listings.add_argument("--city")
    listings.add_argument("--all", action="store_true", help="include unpublished")
    listings.set_defaults(func=_cmd_listings)

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    configure_logging("DEBUG" if args.verbose else None)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
