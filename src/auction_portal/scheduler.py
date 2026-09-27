"""The scheduler: what makes the portal maintain itself.

Jobs, and why each exists:

  crawl-sources       every 6 hours   pick up new and changed listings
  refresh-imminent    hourly          auctions within 7 days move and get
                                      cancelled at short notice, and that
                                      is exactly when a user relies on us
  advance-statuses    every 15 min    upcoming -> live -> closed on time
  expire-old          daily 03:30     stop publishing concluded auctions
  health-check        every 2 hours   shout when a source looks broken

Why APScheduler rather than Celery: this is one machine running a handful
of periodic jobs, and APScheduler needs no message broker. The moment
crawling has to be spread across several machines, Celery plus Redis is
the upgrade - the job functions below would not have to change.

Two settings matter for correctness:
  coalesce         if the process was down, run a missed job once, not
                   once for every interval that elapsed
  max_instances=1  a slow crawl must never overlap with the next one
"""

import logging
import time
from datetime import UTC, datetime, timedelta

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from sqlalchemy import select

from auction_portal.config import Settings, get_settings
from auction_portal.crawler import Crawler
from auction_portal.db.models import Listing
from auction_portal.db.session import get_sessionmaker
from auction_portal.fetching.client import Fetcher
from auction_portal.maintenance import (
    advance_statuses,
    check_health,
    expire_old,
    record_health,
)
from auction_portal.sources import REGISTRY

log = logging.getLogger(__name__)

IST = "Asia/Kolkata"

#: Listings auctioning within this window are re-checked hourly.
IMMINENT_DAYS = 7


def build_adapter(source_id: str, fetcher: Fetcher):
    def fetch_text(url: str) -> str:
        result = fetcher.fetch(url, source_id=source_id)
        if result.document is None:
            raise RuntimeError(f"could not fetch {url}: {result.error or result.outcome}")
        return result.document.content.decode("utf-8", errors="replace")

    return REGISTRY[source_id](fetch_text=fetch_text)


def crawl_source(source_id: str, limit: int | None = None) -> None:
    """Crawl one source and record how it went."""
    settings = get_settings()
    settings.ensure_directories()
    limit = limit or settings.crawl_batch_size
    sessions = get_sessionmaker()

    started = time.monotonic()
    fetcher = Fetcher(settings)
    try:
        adapter = build_adapter(source_id, fetcher)
        with Crawler(adapter, settings=settings, session_factory=sessions) as crawler:
            report = crawler.run(limit=limit)
    except Exception:
        log.exception("crawl of %s failed", source_id)
        raise
    finally:
        fetcher.close()

    with sessions.begin() as session:
        record_health(session, report, duration_seconds=round(time.monotonic() - started, 2))

    log.info("crawl complete - %s", report.summary())


def refresh_imminent() -> None:
    """Re-check auctions happening soon.

    Cheap - there are rarely more than a few hundred - and it is what
    stops someone travelling to an inspection that was cancelled.
    """
    settings = get_settings()
    sessions = get_sessionmaker()
    horizon = datetime.now(UTC) + timedelta(days=IMMINENT_DAYS)

    with sessions() as session:
        rows = session.execute(
            select(Listing.source_id, Listing.canonical_url).where(
                Listing.status.in_(("upcoming", "live")),
                Listing.auction_start_at.is_not(None),
                Listing.auction_start_at <= horizon,
            )
        ).all()

    if not rows:
        log.info("no imminent auctions to refresh")
        return

    by_source: dict[str, list[str]] = {}
    for source_id, url in rows:
        by_source.setdefault(source_id, []).append(url)

    fetcher = Fetcher(settings)
    try:
        for source_id, urls in by_source.items():
            if source_id not in REGISTRY:
                continue
            adapter = build_adapter(source_id, fetcher)
            with Crawler(adapter, settings=settings, session_factory=sessions) as crawler:
                report = crawler.run_urls(urls)
            log.info(
                "refreshed %d imminent %s listings - %s", len(urls), source_id, report.summary()
            )
    finally:
        fetcher.close()


def run_advance_statuses() -> None:
    with get_sessionmaker().begin() as session:
        advance_statuses(session)


def run_expire_old() -> None:
    with get_sessionmaker().begin() as session:
        expire_old(session)


def run_health_check() -> None:
    with get_sessionmaker()() as session:
        verdicts = check_health(session, sorted(REGISTRY))
    unhealthy = [v for v in verdicts if not v.ok]
    if unhealthy:
        # In production this is where an email or webhook goes out.
        # Logging at ERROR is enough for Sentry or a log alert to pick up.
        for verdict in unhealthy:
            log.error("ALERT %s: %s", verdict.source_id, verdict.reason)
    else:
        log.info("all %d sources healthy", len(verdicts))


def build_scheduler(settings: Settings | None = None) -> BlockingScheduler:
    settings = settings or get_settings()

    scheduler = BlockingScheduler(
        timezone=IST,
        job_defaults={
            # After downtime, run a missed job once rather than once per
            # interval that passed.
            "coalesce": True,
            # A slow crawl must never overlap the next run.
            "max_instances": 1,
            "misfire_grace_time": 3600,
        },
    )

    for source_id in sorted(REGISTRY):
        scheduler.add_job(
            crawl_source,
            CronTrigger(hour="2,8,14,20", minute=0, timezone=IST),
            args=[source_id],
            id=f"crawl-{source_id}",
            name=f"Crawl {source_id}",
        )

    scheduler.add_job(
        refresh_imminent,
        CronTrigger(minute=15, timezone=IST),
        id="refresh-imminent",
        name="Refresh imminent auctions",
    )
    scheduler.add_job(
        run_advance_statuses,
        IntervalTrigger(minutes=15),
        id="advance-statuses",
        name="Advance listing statuses",
    )
    scheduler.add_job(
        run_expire_old,
        CronTrigger(hour=3, minute=30, timezone=IST),
        id="expire-old",
        name="Expire concluded listings",
    )
    scheduler.add_job(
        run_health_check,
        IntervalTrigger(hours=2),
        id="health-check",
        name="Check source health",
    )

    return scheduler


def describe(scheduler: BlockingScheduler) -> list[str]:
    return [
        f"{job.id:<28} {job.name:<32} next: {job.next_run_time}" for job in scheduler.get_jobs()
    ]
