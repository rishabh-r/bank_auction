"""End-to-end tests for fetch + archive + database, with a faked network.

These cover the behaviour the milestone exists for: fetch once, store once,
and do nothing at all when the content has not changed.
"""

import httpx

from auction_portal.archiver import Archiver
from auction_portal.db.repository import DocumentRepository
from auction_portal.fetching.client import Fetcher
from auction_portal.fetching.models import FetchOutcome
from auction_portal.fetching.robots import RobotsChecker
from auction_portal.fetching.throttle import DomainThrottle

URL = "https://bank.test/notices/auction.pdf"
PDF = {"content-type": "application/pdf"}


class StubRobots(RobotsChecker):
    def __init__(self):
        pass

    def is_allowed(self, url):
        return True

    def crawl_delay_for(self, url):
        return None


class NoWaitThrottle(DomainThrottle):
    def wait(self, url):
        return 0.0


def build_archiver(settings, handler, session_factory):
    fetcher = Fetcher(
        settings=settings,
        client=httpx.Client(transport=httpx.MockTransport(handler)),
        robots=StubRobots(),
        throttle=NoWaitThrottle(1.0),
    )
    return Archiver(settings=settings, fetcher=fetcher, session_factory=session_factory)


def counts(session_factory):
    with session_factory() as session:
        repo = DocumentRepository(session)
        return repo.count_documents(), repo.count_urls()


def test_first_fetch_archives_and_records(settings, db_session_factory):
    def handler(request):
        return httpx.Response(200, content=b"notice v1", headers=PDF)

    archiver = build_archiver(settings, handler, db_session_factory)
    result = archiver.archive(URL, source_id="testbank")

    assert result.outcome is FetchOutcome.NEW
    assert archiver.store.read(result.storage_key) == b"notice v1"
    assert counts(db_session_factory) == (1, 1)


def test_refetching_identical_content_stores_nothing_new(settings, db_session_factory):
    """The behaviour that keeps the parsing and OCR bill down."""

    def handler(request):
        return httpx.Response(200, content=b"notice v1", headers=PDF)

    archiver = build_archiver(settings, handler, db_session_factory)
    archiver.archive(URL, source_id="testbank")
    second = archiver.archive(URL, source_id="testbank")

    assert second.outcome is FetchOutcome.UNCHANGED
    assert counts(db_session_factory) == (1, 1)

    with db_session_factory() as session:
        state = DocumentRepository(session).get_url_state(URL)
        assert state.fetch_count == 2
        assert state.unchanged_streak == 1


def test_a_ticking_visitor_counter_does_not_archive_a_new_copy(settings, db_session_factory):
    """The bug this guards against: a site-wide counter in every page
    meant each hourly refresh archived a fresh copy of all 219 imminent
    listings, roughly 630 MB a day of identical notices."""
    counter = [2800055]

    def handler(request):
        counter[0] += 137
        body = f"<span>Visitor Count:</span><span>{counter[0]}</span> notice".encode()
        return httpx.Response(200, content=body, headers=PDF)

    archiver = build_archiver(settings, handler, db_session_factory)
    first = archiver.archive(URL, source_id="testbank")
    second = archiver.archive(URL, source_id="testbank")
    third = archiver.archive(URL, source_id="testbank")

    assert first.outcome is FetchOutcome.NEW
    assert second.outcome is FetchOutcome.UNCHANGED
    assert third.outcome is FetchOutcome.UNCHANGED
    assert counts(db_session_factory) == (1, 1)
    assert archiver.store.count() == 1


def test_changed_content_is_archived_as_a_new_version(settings, db_session_factory):
    """A corrigendum must be kept alongside the original, not replace it."""
    bodies = [b"Reserve Price Rs.3,37,55,000", b"Reserve Price Rs.2,90,00,000"]
    call_count = []

    def handler(request):
        body = bodies[min(len(call_count), 1)]
        call_count.append(1)
        return httpx.Response(200, content=body, headers=PDF)

    archiver = build_archiver(settings, handler, db_session_factory)
    first = archiver.archive(URL, source_id="testbank")
    second = archiver.archive(URL, source_id="testbank")

    assert first.outcome is FetchOutcome.NEW
    assert second.outcome is FetchOutcome.NEW
    assert first.storage_key != second.storage_key
    assert counts(db_session_factory) == (2, 1)
    # The original bytes are still readable, unchanged.
    assert archiver.store.read(first.storage_key) == bodies[0]


def test_etag_is_reused_on_the_next_fetch(settings, db_session_factory):
    """Saves the server resending the body. Polite and cheap."""
    seen = []

    def handler(request):
        seen.append(dict(request.headers))
        if request.headers.get("if-none-match") == '"v1"':
            return httpx.Response(304)
        return httpx.Response(200, content=b"notice", headers={**PDF, "etag": '"v1"'})

    archiver = build_archiver(settings, handler, db_session_factory)
    archiver.archive(URL, source_id="testbank")
    second = archiver.archive(URL, source_id="testbank")

    assert second.outcome is FetchOutcome.NOT_MODIFIED
    assert seen[1]["if-none-match"] == '"v1"'
    assert counts(db_session_factory) == (1, 1)

    with db_session_factory() as session:
        assert DocumentRepository(session).get_url_state(URL).fetch_count == 2


def test_failed_fetch_records_nothing(settings, db_session_factory):
    def handler(request):
        return httpx.Response(404)

    archiver = build_archiver(settings, handler, db_session_factory)
    result = archiver.archive(URL, source_id="testbank")

    assert result.outcome is FetchOutcome.FAILED
    assert counts(db_session_factory) == (0, 0)


def test_state_survives_a_restart(settings, db_session_factory):
    """State is in the database, so a crash does not cause a re-download."""

    def handler(request):
        return httpx.Response(200, content=b"notice", headers=PDF)

    build_archiver(settings, handler, db_session_factory).archive(URL, "testbank")

    # A brand new Archiver, as if the process had been restarted.
    restarted = build_archiver(settings, handler, db_session_factory)
    result = restarted.archive(URL, source_id="testbank")

    assert result.outcome is FetchOutcome.UNCHANGED
    assert counts(db_session_factory) == (1, 1)


def test_robots_block_records_nothing(settings, db_session_factory):
    def handler(request):
        raise AssertionError("must not be called")

    fetcher = Fetcher(
        settings=settings,
        client=httpx.Client(transport=httpx.MockTransport(handler)),
        robots=type("Blocked", (StubRobots,), {"is_allowed": lambda self, url: False})(),
        throttle=NoWaitThrottle(1.0),
    )
    archiver = Archiver(settings=settings, fetcher=fetcher, session_factory=db_session_factory)
    result = archiver.archive(URL, source_id="testbank")

    assert result.outcome is FetchOutcome.BLOCKED_BY_ROBOTS
    assert counts(db_session_factory) == (0, 0)
