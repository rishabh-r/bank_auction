"""Tests for the HTTP fetcher.

All network traffic is faked with httpx.MockTransport - these tests never
contact a real site.
"""

import httpx
import pytest

from auction_portal.fetching.client import Fetcher
from auction_portal.fetching.models import FetchOutcome
from auction_portal.fetching.robots import RobotsChecker
from auction_portal.fetching.throttle import DomainThrottle

URL = "https://bank.test/notices/auction.pdf"


def make_fetcher(settings, handler, robots_allows=True, delay=1.0):
    """Build a Fetcher wired to a fake transport and a no-op throttle."""
    client = httpx.Client(transport=httpx.MockTransport(handler))

    class StubRobots(RobotsChecker):
        def __init__(self):
            pass

        def is_allowed(self, url):
            return robots_allows

        def crawl_delay_for(self, url):
            return None

    class NoWaitThrottle(DomainThrottle):
        def wait(self, url):
            return 0.0

    return Fetcher(
        settings=settings,
        client=client,
        robots=StubRobots(),
        throttle=NoWaitThrottle(delay),
    )


def test_successful_fetch_returns_content(settings):
    def handler(request):
        return httpx.Response(
            200, content=b"%PDF-1.4 notice", headers={"content-type": "application/pdf"}
        )

    result = make_fetcher(settings, handler).fetch(URL, source_id="test")

    assert result.outcome is FetchOutcome.NEW
    assert result.document.content == b"%PDF-1.4 notice"
    assert result.document.extension == ".pdf"


def test_robots_disallow_prevents_any_request(settings):
    """If robots.txt says no, we must not even attempt the fetch."""
    attempts = []

    def handler(request):
        attempts.append(request.url)
        return httpx.Response(200, content=b"should never be reached")

    result = make_fetcher(settings, handler, robots_allows=False).fetch(URL, "test")

    assert result.outcome is FetchOutcome.BLOCKED_BY_ROBOTS
    assert attempts == []


def test_user_agent_identifies_us(settings):
    seen = {}

    def handler(request):
        seen["ua"] = request.headers.get("user-agent")
        return httpx.Response(200, content=b"ok")

    make_fetcher(settings, handler).fetch(URL, "test")

    assert seen["ua"].startswith("AuctionPortalBot/")
    assert "bot@example.com" in seen["ua"]


def test_304_not_modified_is_recognised(settings):
    def handler(request):
        assert request.headers["if-none-match"] == '"abc123"'
        return httpx.Response(304)

    result = make_fetcher(settings, handler).fetch(URL, "test", etag='"abc123"')

    assert result.outcome is FetchOutcome.NOT_MODIFIED
    assert result.document is None


def test_conditional_headers_sent_when_known(settings):
    seen = {}

    def handler(request):
        seen.update(request.headers)
        return httpx.Response(200, content=b"ok")

    make_fetcher(settings, handler).fetch(
        URL, "test", etag='"v1"', last_modified="Wed, 21 Oct 2026 07:28:00 GMT"
    )

    assert seen["if-none-match"] == '"v1"'
    assert seen["if-modified-since"] == "Wed, 21 Oct 2026 07:28:00 GMT"


def test_server_error_is_retried_then_succeeds(settings):
    attempts = []

    def handler(request):
        attempts.append(1)
        if len(attempts) < 3:
            return httpx.Response(503)
        return httpx.Response(200, content=b"recovered")

    result = make_fetcher(settings, handler).fetch(URL, "test")

    assert result.outcome is FetchOutcome.NEW
    assert len(attempts) == 3


def test_gives_up_after_max_retries(settings):
    attempts = []

    def handler(request):
        attempts.append(1)
        return httpx.Response(503)

    result = make_fetcher(settings, handler).fetch(URL, "test")

    assert result.outcome is FetchOutcome.FAILED
    assert len(attempts) == settings.crawler_max_retries + 1


def test_404_is_not_retried(settings):
    """A missing page is a real answer, not a transient fault."""
    attempts = []

    def handler(request):
        attempts.append(1)
        return httpx.Response(404)

    result = make_fetcher(settings, handler).fetch(URL, "test")

    assert result.outcome is FetchOutcome.FAILED
    assert "404" in result.error
    assert len(attempts) == 1


def test_rate_limit_response_is_retried(settings):
    attempts = []

    def handler(request):
        attempts.append(1)
        if len(attempts) == 1:
            return httpx.Response(429, headers={"retry-after": "0"})
        return httpx.Response(200, content=b"ok")

    result = make_fetcher(settings, handler).fetch(URL, "test")

    assert result.outcome is FetchOutcome.NEW
    assert len(attempts) == 2


def test_connection_error_is_retried(settings):
    attempts = []

    def handler(request):
        attempts.append(1)
        if len(attempts) < 2:
            raise httpx.ConnectError("network down")
        return httpx.Response(200, content=b"ok")

    result = make_fetcher(settings, handler).fetch(URL, "test")

    assert result.outcome is FetchOutcome.NEW


def test_etag_captured_for_next_time(settings):
    def handler(request):
        return httpx.Response(200, content=b"ok", headers={"etag": '"xyz"'})

    result = make_fetcher(settings, handler).fetch(URL, "test")

    assert result.document.etag == '"xyz"'


@pytest.mark.parametrize("attempt", [0, 1, 2, 3])
def test_backoff_grows_and_is_bounded(attempt):
    delay = Fetcher._backoff(attempt)
    assert 0 < delay <= 2.0**attempt
