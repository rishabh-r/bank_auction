"""Scheduled maintenance jobs.

These run unattended and keep the portal honest without anyone touching
it:

  advance_statuses   move listings through upcoming -> live -> closed
  expire_old         stop publishing auctions that concluded long ago
  record_health      note the outcome of a crawl run
  check_health       decide whether any source looks broken

All of them are idempotent: running one twice does nothing the second
time, so a retried or overlapping schedule cannot cause damage.
"""

import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from auction_portal.crawler import CrawlReport
from auction_portal.db.models import Listing, SourceHealth

log = logging.getLogger(__name__)

#: How long after an auction concludes a listing stays publicly visible.
#: Notices contain personal data published under a statutory obligation;
#: indexing them indefinitely is not something that obligation supports.
#: See Part E of the project documentation.
PUBLIC_RETENTION_DAYS = 90

#: A source producing nothing new for this long is treated as broken.
STALE_SOURCE_HOURS = 48


@dataclass(frozen=True, slots=True)
class HealthVerdict:
    source_id: str
    ok: bool
    reason: str
    last_run: datetime | None = None
    hours_since_new: float | None = None


def advance_statuses(session: Session, now: datetime | None = None) -> dict[str, int]:
    """Move listings through their lifecycle based on the clock.

    Without this, a listing says 'upcoming' forever and a user turns up
    to an auction that finished last month.
    """
    now = now or datetime.now(UTC)
    changed: dict[str, int] = {}

    started = session.execute(
        update(Listing)
        .where(
            Listing.status == "upcoming",
            Listing.auction_start_at.is_not(None),
            Listing.auction_start_at <= now,
        )
        .values(status="live", updated_at=now)
    )
    changed["upcoming_to_live"] = started.rowcount or 0

    # Ended, where we know the end time.
    finished = session.execute(
        update(Listing)
        .where(
            Listing.status.in_(("upcoming", "live")),
            Listing.auction_end_at.is_not(None),
            Listing.auction_end_at < now,
        )
        .values(status="closed", updated_at=now)
    )
    changed["to_closed"] = finished.rowcount or 0

    # Started but no end time recorded: assume a single day, rather than
    # leaving it 'live' indefinitely.
    assumed = session.execute(
        update(Listing)
        .where(
            Listing.status == "live",
            Listing.auction_end_at.is_(None),
            Listing.auction_start_at < now - timedelta(days=1),
        )
        .values(status="closed", updated_at=now)
    )
    changed["to_closed"] += assumed.rowcount or 0

    if any(changed.values()):
        log.info("status changes: %s", changed)
    return changed


def expire_old(
    session: Session, now: datetime | None = None, retention_days: int = PUBLIC_RETENTION_DAYS
) -> int:
    """Unpublish auctions that concluded more than the retention period ago.

    The rows are kept - the history is useful and the archive is
    immutable - but they stop being publicly searchable.
    """
    now = now or datetime.now(UTC)
    cutoff = now - timedelta(days=retention_days)

    result = session.execute(
        update(Listing)
        .where(
            Listing.is_published.is_(True),
            Listing.status == "closed",
            Listing.auction_start_at.is_not(None),
            Listing.auction_start_at < cutoff,
        )
        .values(is_published=False, updated_at=now)
    )
    count = result.rowcount or 0
    if count:
        log.info("unpublished %d listings older than %d days", count, retention_days)
    return count


def record_health(
    session: Session, report: CrawlReport, duration_seconds: float | None = None
) -> SourceHealth:
    """Store the outcome of a crawl run."""
    row = SourceHealth(
        source_id=report.source_id,
        duration_seconds=duration_seconds,
        discovered=report.discovered,
        fetched=report.fetched,
        unchanged=report.unchanged,
        failed=report.failed,
        parse_failures=report.parse_failures,
        listings_created=report.listings_created,
        listings_updated=report.listings_updated,
        listings_seen=(
            report.listings_created + report.listings_updated + report.listings_unchanged
        ),
        ok=_run_looks_healthy(report),
        notes="; ".join(report.errors[:3]) or None,
    )
    session.add(row)
    return row


def _run_looks_healthy(report: CrawlReport) -> bool:
    if report.discovered == 0:
        return False  # discovery returning nothing means the source changed
    if report.fetched and report.parse_failures >= report.fetched:
        return False  # fetched pages but could not read any of them
    # More than half the fetch attempts failing means the source is
    # blocking us, is down, or has moved.
    attempted = report.fetched + report.failed
    return not (attempted and report.failed / attempted > 0.5)


def check_health(
    session: Session, source_ids: list[str], now: datetime | None = None
) -> list[HealthVerdict]:
    """Decide whether each source looks broken.

    The important check is not 'did it error' but 'has it produced
    anything new lately'. A scraper whose selector broke returns zero
    results perfectly happily.
    """
    now = now or datetime.now(UTC)
    verdicts: list[HealthVerdict] = []

    for source_id in source_ids:
        last_run = session.scalar(
            select(func.max(SourceHealth.ran_at)).where(SourceHealth.source_id == source_id)
        )
        if last_run is None:
            verdicts.append(HealthVerdict(source_id, True, "never run"))
            continue

        # "Produced listings", not "produced *new* listings". Once a source
        # is established most runs legitimately create nothing, because
        # nothing was republished. A run that yields no listings at all is
        # the real signal that a parser has quietly broken.
        last_new = session.scalar(
            select(func.max(SourceHealth.ran_at)).where(
                SourceHealth.source_id == source_id,
                SourceHealth.listings_seen > 0,
            )
        )
        hours_since_new = (now - last_new).total_seconds() / 3600 if last_new else None

        recent_failure = session.scalar(
            select(SourceHealth.ok)
            .where(SourceHealth.source_id == source_id)
            .order_by(SourceHealth.ran_at.desc())
            .limit(1)
        )

        if recent_failure is False:
            verdict = HealthVerdict(
                source_id, False, "last run failed its own checks", last_run, hours_since_new
            )
        elif hours_since_new is None:
            verdict = HealthVerdict(
                source_id, False, "has never produced a listing", last_run, None
            )
        elif hours_since_new > STALE_SOURCE_HOURS:
            verdict = HealthVerdict(
                source_id,
                False,
                f"produced no listings for {hours_since_new:.0f}h",
                last_run,
                hours_since_new,
            )
        else:
            verdict = HealthVerdict(source_id, True, "healthy", last_run, hours_since_new)

        verdicts.append(verdict)

        if not verdict.ok:
            log.error("SOURCE UNHEALTHY  %s: %s", source_id, verdict.reason)

    return verdicts
