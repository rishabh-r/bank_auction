"""End-to-end tests for fetch + archive, with a faked network.

These cover the behaviour the whole milestone exists for: fetch once, store
once, and do nothing at all when the content has not changed.
"""

import httpx

from auction_portal.archiver import Archiver
from auction_portal.fetching.client import Fetcher
from auction_portal.fetching.models import FetchOutcome
from auction_portal.fetching.robots import RobotsChecker
from auction_portal.fetching.throttle import DomainThrottle

URL = "https://bank.test/notices/auction.pdf"


def build_archiver(settings, handler):
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

    fetcher = Fetcher(
        settings=settings,
        client=httpx.Client(transport=httpx.MockTransport(handler)),
        robots=StubRobots(),
        throttle=NoWaitThrottle(1.0),
    )
    return Archiver(settings=settings, fetcher=fetcher)


def test_first_fetch_archives_the_document(settings):
    def handler(request):
        return httpx.Response(
            200, content=b"notice v1", headers={"content-type": "application/pdf"}
        )

    archiver = build_archiver(settings, handler)
    result = archiver.archive(URL, source_id="testbank")

    assert result.outcome is FetchOutcome.NEW
    assert archiver.store.count() == 1
    assert archiver.store.read(result.storage_key) == b"notice v1"


def test_refetching_identical_content_stores_nothing_new(settings):
    """The behaviour that keeps the parsing and OCR bill down."""

    def handler(request):
        return httpx.Response(
            200, content=b"notice v1", headers={"content-type": "application/pdf"}
        )

    archiver = build_archiver(settings, handler)
    archiver.archive(URL, source_id="testbank")
    second = archiver.archive(URL, source_id="testbank")

    assert second.outcome is FetchOutcome.UNCHANGED
    assert archiver.store.count() == 1


def test_changed_content_is_archived_as_a_new_version(settings):
    """A corrigendum must be kept alongside the original, not replace it."""
    bodies = [b"Reserve Price Rs.3,37,55,000", b"Reserve Price Rs.2,90,00,000"]

    def handler(request):
        return httpx.Response(
            200, content=bodies[min(len(calls), 1)], headers={"content-type": "application/pdf"}
        )

    calls = []
    original_handler = handler

    def counting_handler(request):
        response = original_handler(request)
        calls.append(1)
        return response

    archiver = build_archiver(settings, counting_handler)
    first = archiver.archive(URL, source_id="testbank")
    second = archiver.archive(URL, source_id="testbank")

    assert first.outcome is FetchOutcome.NEW
    assert second.outcome is FetchOutcome.NEW
    assert first.storage_key != second.storage_key
    assert archiver.store.count() == 2
    assert archiver.store.read(first.storage_key) == bodies[0]


def test_etag_is_reused_on_the_next_fetch(settings):
    """Saves the server sending the body again. Polite and cheap."""
    seen_headers = []

    def handler(request):
        seen_headers.append(dict(request.headers))
        if request.headers.get("if-none-match") == '"v1"':
            return httpx.Response(304)
        return httpx.Response(
            200, content=b"notice", headers={"content-type": "application/pdf", "etag": '"v1"'}
        )

    archiver = build_archiver(settings, handler)
    archiver.archive(URL, source_id="testbank")
    second = archiver.archive(URL, source_id="testbank")

    assert second.outcome is FetchOutcome.NOT_MODIFIED
    assert seen_headers[1]["if-none-match"] == '"v1"'
    assert archiver.store.count() == 1


def test_url_state_tracks_fetch_history(settings):
    def handler(request):
        return httpx.Response(200, content=b"notice", headers={"content-type": "application/pdf"})

    archiver = build_archiver(settings, handler)
    archiver.archive(URL, source_id="testbank")
    archiver.archive(URL, source_id="testbank")
    archiver.archive(URL, source_id="testbank")

    state = archiver.state.get(URL)
    assert state.fetch_count == 3
    assert state.first_seen_at == state.last_changed_at  # never changed
    assert len(archiver.state) == 1


def test_failed_fetch_archives_nothing(settings):
    def handler(request):
        return httpx.Response(404)

    archiver = build_archiver(settings, handler)
    result = archiver.archive(URL, source_id="testbank")

    assert result.outcome is FetchOutcome.FAILED
    assert archiver.store.count() == 0
    assert archiver.state.get(URL) is None


def test_state_survives_a_restart(settings):
    """State is on disk, so a crash does not cause everything to re-download."""

    def handler(request):
        return httpx.Response(200, content=b"notice", headers={"content-type": "application/pdf"})

    build_archiver(settings, handler).archive(URL, source_id="testbank")

    # A brand new Archiver, as if the process had been restarted.
    restarted = build_archiver(settings, handler)
    result = restarted.archive(URL, source_id="testbank")

    assert result.outcome is FetchOutcome.UNCHANGED
    assert restarted.store.count() == 1
