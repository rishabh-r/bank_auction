"""Tests for crawl scheduling and URL prioritisation.

The behaviour under test is what lets coverage grow. Asking the adapter
for only the first N URLs would return the same N on every run, so a
scheduled crawl would loop over the first page of the sitemap forever and
never reach the other 71,000 pages.
"""

from datetime import UTC, datetime, timedelta

import httpx

from auction_portal.archiver import Archiver
from auction_portal.crawler import Crawler
from auction_portal.db.models import UrlStateRow
from auction_portal.fetching.client import Fetcher
from auction_portal.fetching.robots import RobotsChecker
from auction_portal.fetching.throttle import DomainThrottle
from auction_portal.sources.base import ParsedListing, SourceAdapter

NOW = datetime(2026, 9, 27, 12, 0, tzinfo=UTC)
ALL_URLS = [f"https://bank.test/property-detail/{n}/x" for n in range(20)]


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


class StubAdapter(SourceAdapter):
    source_id = "stub"
    display_name = "Stub"
    base_url = "https://bank.test"

    def __init__(self, urls: list[str]):
        self._urls = urls
        self.discover_calls: list[int | None] = []

    def discover(self, limit: int | None = None) -> list[str]:
        self.discover_calls.append(limit)
        return list(self._urls) if limit is None else list(self._urls)[:limit]

    def parse(self, document):
        return [
            ParsedListing(
                source_id=self.source_id,
                external_id=document.url.rsplit("/", 2)[-2],
                canonical_url=document.url,
                asset_class="property",
                city="Testville",
                state="Teststate",
            )
        ]


def build_crawler(settings, session_factory, urls=ALL_URLS):
    def handler(request):
        return httpx.Response(
            200, content=f"page {request.url}".encode(), headers={"content-type": "text/html"}
        )

    fetcher = Fetcher(
        settings=settings,
        client=httpx.Client(transport=httpx.MockTransport(handler)),
        robots=StubRobots(),
        throttle=NoWaitThrottle(1.0),
    )
    adapter = StubAdapter(urls)
    archiver = Archiver(settings=settings, fetcher=fetcher, session_factory=session_factory)
    return Crawler(
        adapter, settings=settings, archiver=archiver, session_factory=session_factory
    ), adapter


def fetched_urls(session_factory) -> set[str]:
    with session_factory() as session:
        return {row.url for row in session.query(UrlStateRow).all()}


def test_crawler_asks_the_adapter_for_everything(settings, db_session_factory):
    """Selection happens here, not in the adapter, so it can take account
    of what has already been fetched."""
    crawler, adapter = build_crawler(settings, db_session_factory)
    crawler.run(limit=5)

    assert adapter.discover_calls == [None]


def test_a_limited_run_fetches_only_the_limit(settings, db_session_factory):
    crawler, _ = build_crawler(settings, db_session_factory)
    report = crawler.run(limit=5)

    assert report.discovered == 5
    assert len(fetched_urls(db_session_factory)) == 5


def test_successive_runs_reach_new_pages(settings, db_session_factory):
    """The bug this guards against: repeated runs re-fetching the same
    first N URLs, so coverage never grows."""
    crawler, _ = build_crawler(settings, db_session_factory)

    crawler.run(limit=5)
    first_batch = fetched_urls(db_session_factory)

    crawler.run(limit=5)
    after_second = fetched_urls(db_session_factory)

    assert len(first_batch) == 5
    assert len(after_second) == 10
    assert first_batch < after_second


def test_repeated_runs_eventually_cover_the_whole_source(settings, db_session_factory):
    crawler, _ = build_crawler(settings, db_session_factory)

    for _ in range(4):
        crawler.run(limit=5)

    assert fetched_urls(db_session_factory) == set(ALL_URLS)


def test_once_everything_is_seen_the_stalest_is_refreshed(settings, db_session_factory):
    """After full coverage, runs should refresh oldest-first rather than
    always revisiting the same pages."""
    crawler, _ = build_crawler(settings, db_session_factory, urls=ALL_URLS[:5])
    crawler.run(limit=5)

    # Age two of them so they are clearly the stalest.
    with db_session_factory() as session:
        for url in ALL_URLS[:2]:
            state = session.get(UrlStateRow, url)
            state.last_fetched_at = NOW - timedelta(days=30)
        session.commit()

    crawler.run(limit=2)

    with db_session_factory() as session:
        refreshed = {
            url
            for url in ALL_URLS[:2]
            if session.get(UrlStateRow, url).last_fetched_at > NOW - timedelta(days=1)
        }
    assert refreshed == set(ALL_URLS[:2])


def test_an_unlimited_run_takes_everything(settings, db_session_factory):
    crawler, _ = build_crawler(settings, db_session_factory)
    report = crawler.run()

    assert report.discovered == len(ALL_URLS)
    assert fetched_urls(db_session_factory) == set(ALL_URLS)


def test_a_limit_beyond_the_source_is_harmless(settings, db_session_factory):
    crawler, _ = build_crawler(settings, db_session_factory)
    report = crawler.run(limit=10_000)

    assert report.discovered == len(ALL_URLS)


def test_run_urls_bypasses_discovery(settings, db_session_factory):
    """Used to re-check imminent auctions without walking the sitemap."""
    crawler, adapter = build_crawler(settings, db_session_factory)
    report = crawler.run_urls(ALL_URLS[:3])

    assert adapter.discover_calls == []
    assert report.discovered == 3
    assert len(fetched_urls(db_session_factory)) == 3
