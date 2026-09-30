"""Tests for the unattended maintenance jobs."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from auction_portal.crawler import CrawlReport
from auction_portal.db.listing_repository import ListingRepository
from auction_portal.db.models import Listing
from auction_portal.maintenance import (
    STALE_SOURCE_HOURS,
    advance_statuses,
    check_health,
    count_stale_statuses,
    expire_old,
    record_health,
)
from auction_portal.sources.base import ParsedListing

NOW = datetime(2026, 6, 1, 12, 0, tzinfo=UTC)


def parsed(external_id: str, **overrides) -> ParsedListing:
    values = {
        "source_id": "baanknet",
        "external_id": external_id,
        "canonical_url": f"https://x.test/{external_id}",
        "asset_class": "property",
        "city": "Mumbai",
        "state": "Maharashtra",
        "reserve_price": Decimal("5000000.00"),
        "status": "upcoming",
    }
    values.update(overrides)
    return ParsedListing(**values)


def store(session, *listings) -> None:
    repo = ListingRepository(session)
    for item in listings:
        repo.upsert(item)
    session.flush()


def status_of(session, external_id: str) -> str:
    return ListingRepository(session).get("baanknet", external_id).status


# --- status lifecycle -----------------------------------------------------


def test_started_auction_becomes_live(db_session):
    store(db_session, parsed("1", auction_start_at=NOW - timedelta(hours=2)))

    advance_statuses(db_session, now=NOW)

    assert status_of(db_session, "1") == "live"


def test_future_auction_stays_upcoming(db_session):
    store(db_session, parsed("1", auction_start_at=NOW + timedelta(days=5)))

    advance_statuses(db_session, now=NOW)

    assert status_of(db_session, "1") == "upcoming"


def test_finished_auction_becomes_closed(db_session):
    store(
        db_session,
        parsed(
            "1",
            auction_start_at=NOW - timedelta(days=2),
            auction_end_at=NOW - timedelta(days=1),
        ),
    )

    advance_statuses(db_session, now=NOW)

    assert status_of(db_session, "1") == "closed"


def test_live_auction_without_an_end_time_does_not_stay_live_forever(db_session):
    """Otherwise a listing sits at 'live' indefinitely and a user turns up
    to an auction that ended weeks ago."""
    store(db_session, parsed("1", status="live", auction_start_at=NOW - timedelta(days=10)))

    advance_statuses(db_session, now=NOW)

    assert status_of(db_session, "1") == "closed"


def test_unscheduled_listings_are_left_alone(db_session):
    store(db_session, parsed("1", status="unscheduled", auction_start_at=None))

    advance_statuses(db_session, now=NOW)

    assert status_of(db_session, "1") == "unscheduled"


def test_displayed_status_is_right_even_when_the_job_has_not_run(db_session):
    """The bug this guards against: 439 finished auctions shown as
    'upcoming' because the maintenance job had not run since a reboot.

    Pages derive status from the clock, so a stalled job degrades
    filtering rather than lying to a reader.
    """
    store(db_session, parsed("1", auction_start_at=NOW - timedelta(days=2)))
    listing = ListingRepository(db_session).get("baanknet", "1")

    assert listing.status == "upcoming"  # stored value is stale
    assert listing.effective_status == "closed"  # what a reader sees
    assert listing.status_is_stale is True


def test_displayed_status_matches_stored_once_the_job_runs(db_session):
    store(db_session, parsed("1", auction_start_at=NOW - timedelta(days=2)))
    advance_statuses(db_session, now=NOW)
    db_session.flush()

    listing = ListingRepository(db_session).get("baanknet", "1")
    assert listing.status_is_stale is False


def test_a_cancelled_auction_is_not_revived_by_the_clock(db_session):
    """Time cannot un-cancel an auction."""
    store(
        db_session,
        parsed("1", status="cancelled", auction_start_at=NOW + timedelta(days=5)),
    )
    listing = ListingRepository(db_session).get("baanknet", "1")

    assert listing.effective_status == "cancelled"


def test_unscheduled_listings_have_no_derived_status(db_session):
    store(db_session, parsed("1", status="unscheduled", auction_start_at=None))
    listing = ListingRepository(db_session).get("baanknet", "1")

    assert listing.effective_status == "unscheduled"


def test_stale_statuses_are_countable_for_alerting(db_session):
    store(
        db_session,
        parsed("1", auction_start_at=NOW - timedelta(days=2)),
        parsed("2", auction_start_at=NOW - timedelta(days=5)),
        parsed("3", auction_start_at=NOW + timedelta(days=5)),  # genuinely upcoming
    )

    assert count_stale_statuses(db_session, now=NOW) == 2

    advance_statuses(db_session, now=NOW)
    db_session.flush()
    assert count_stale_statuses(db_session, now=NOW) == 0


def test_advancing_statuses_twice_changes_nothing_the_second_time(db_session):
    """Every scheduled job must be safe to re-run."""
    store(db_session, parsed("1", auction_start_at=NOW - timedelta(hours=2)))

    first = advance_statuses(db_session, now=NOW)
    second = advance_statuses(db_session, now=NOW)

    assert first["upcoming_to_live"] == 1
    assert second["upcoming_to_live"] == 0


# --- retention ------------------------------------------------------------


def test_old_concluded_auctions_stop_being_published(db_session):
    """Publishing someone's default forever is not supported by the
    obligation the bank had to publish it once."""
    store(
        db_session,
        parsed(
            "1",
            status="closed",
            auction_start_at=NOW - timedelta(days=200),
            auction_end_at=NOW - timedelta(days=200),
        ),
    )

    count = expire_old(db_session, now=NOW)
    db_session.flush()

    assert count == 1
    assert ListingRepository(db_session).get("baanknet", "1").is_published is False


def test_recently_concluded_auctions_remain_published(db_session):
    store(
        db_session,
        parsed("1", status="closed", auction_start_at=NOW - timedelta(days=10)),
    )

    assert expire_old(db_session, now=NOW) == 0


def test_upcoming_auctions_are_never_expired(db_session):
    store(db_session, parsed("1", auction_start_at=NOW - timedelta(days=400)))

    assert expire_old(db_session, now=NOW) == 0


def test_expiry_keeps_the_row_for_history(db_session):
    """Unpublished, not deleted: the price history stays useful."""
    store(
        db_session,
        parsed("1", status="closed", auction_start_at=NOW - timedelta(days=200)),
    )
    expire_old(db_session, now=NOW)
    db_session.flush()

    assert db_session.query(Listing).count() == 1


def test_expiry_is_idempotent(db_session):
    store(
        db_session,
        parsed("1", status="closed", auction_start_at=NOW - timedelta(days=200)),
    )
    assert expire_old(db_session, now=NOW) == 1
    assert expire_old(db_session, now=NOW) == 0


# --- source health --------------------------------------------------------


def report(**overrides) -> CrawlReport:
    values = {
        "source_id": "baanknet",
        "discovered": 100,
        "fetched": 40,
        "listings_created": 12,
    }
    values.update(overrides)
    return CrawlReport(**values)


def test_a_normal_run_is_recorded_as_healthy(db_session):
    row = record_health(db_session, report(), duration_seconds=12.5)
    db_session.flush()

    assert row.ok is True
    assert row.listings_created == 12


def test_discovering_nothing_is_recorded_as_a_failure(db_session):
    """The classic silent failure: a changed selector returns zero
    results without raising anything."""
    row = record_health(db_session, report(discovered=0, fetched=0))
    db_session.flush()

    assert row.ok is False


def test_fetching_pages_but_parsing_none_is_a_failure(db_session):
    row = record_health(db_session, report(fetched=20, parse_failures=20))
    db_session.flush()

    assert row.ok is False


def test_mostly_failing_fetches_is_a_failure(db_session):
    row = record_health(db_session, report(fetched=2, failed=20))
    db_session.flush()

    assert row.ok is False


def test_a_source_never_run_is_not_reported_as_broken(db_session):
    verdicts = check_health(db_session, ["baanknet"], now=NOW)
    assert verdicts[0].ok is True
    assert verdicts[0].reason == "never run"


def test_a_healthy_source_passes(db_session):
    row = record_health(db_session, report())
    row.ran_at = NOW - timedelta(hours=1)
    db_session.flush()

    assert check_health(db_session, ["baanknet"], now=NOW)[0].ok is True


def test_a_source_producing_nothing_at_all_is_flagged(db_session):
    """This is the check that catches a quietly broken scraper."""
    row = record_health(db_session, report(listings_created=12))
    row.ran_at = NOW - timedelta(hours=STALE_SOURCE_HOURS + 10)
    db_session.flush()

    verdict = check_health(db_session, ["baanknet"], now=NOW)[0]
    assert verdict.ok is False
    assert "produced no listings" in verdict.reason


def test_a_run_that_only_finds_unchanged_listings_is_healthy(db_session):
    """Once a source is established, most runs create nothing new. That
    is normal, not a failure, and must not trigger an alert."""
    row = record_health(
        db_session,
        report(listings_created=0, listings_updated=0, listings_unchanged=40),
    )
    row.ran_at = NOW - timedelta(hours=1)
    db_session.flush()

    verdict = check_health(db_session, ["baanknet"], now=NOW)[0]
    assert verdict.ok is True


def test_a_run_that_parses_nothing_is_unhealthy(db_session):
    """Fetched pages but produced no listings at all: the parser broke."""
    row = record_health(
        db_session,
        report(fetched=40, listings_created=0, listings_updated=0, listings_unchanged=0),
    )
    row.ran_at = NOW - timedelta(hours=STALE_SOURCE_HOURS + 5)
    db_session.flush()

    assert check_health(db_session, ["baanknet"], now=NOW)[0].ok is False


def test_a_failed_last_run_is_flagged(db_session):
    good = record_health(db_session, report())
    good.ran_at = NOW - timedelta(hours=5)
    bad = record_health(db_session, report(discovered=0, fetched=0))
    bad.ran_at = NOW - timedelta(hours=1)
    db_session.flush()

    verdict = check_health(db_session, ["baanknet"], now=NOW)[0]
    assert verdict.ok is False
    assert "failed" in verdict.reason
