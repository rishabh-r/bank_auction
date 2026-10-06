"""Tests for running without a durable filesystem.

On a GitHub Actions runner the machine is destroyed after each job.
Writing an archive there would appear to work and quietly leave
database rows pointing at files that no longer exist, so the archive is
switched off and must fail honestly if anything tries to read it.
"""

from datetime import UTC, datetime

import httpx
import pytest
from tests.test_archiver import PDF, URL, NoWaitThrottle, StubRobots

from auction_portal.archiver import Archiver
from auction_portal.config import Settings
from auction_portal.crawler import Crawler
from auction_portal.db.repository import DocumentRepository
from auction_portal.fetching.client import Fetcher
from auction_portal.fetching.models import FetchOutcome, RawDocument
from auction_portal.storage.raw_store import ArchiveDisabledError, RawStore

VALID = {
    "contact_email": "bot@example.com",
    "contact_url": "https://example.com/bot",
}


def document(content: bytes = b"notice") -> RawDocument:
    return RawDocument(
        source_id="testbank",
        url=URL,
        content=content,
        mime_type="application/pdf",
        http_status=200,
        fetched_at=datetime(2026, 10, 5, tzinfo=UTC),
    )


# --- the setting ----------------------------------------------------------


def test_archive_is_on_by_default():
    assert Settings(**VALID).archive_enabled is True


def test_archive_can_be_switched_off(tmp_path):
    settings = Settings(**VALID, data_dir=tmp_path, archive_enabled=False)
    assert RawStore(settings).enabled is False


# --- behaviour when disabled ---------------------------------------------


def test_nothing_is_written_to_disk(tmp_path):
    store = RawStore(Settings(**VALID, data_dir=tmp_path, archive_enabled=False))
    store.save(document())

    assert not any(tmp_path.rglob("*.pdf"))
    assert store.count() == 0


def test_a_key_is_still_returned_so_the_pipeline_is_unchanged(tmp_path):
    """The database still records where the data came from; only the
    bytes are missing."""
    store = RawStore(Settings(**VALID, data_dir=tmp_path, archive_enabled=False))
    key = store.save(document())

    assert key.startswith("testbank/2026/10/05/")
    assert key.endswith(".pdf")


def test_reading_back_fails_loudly_rather_than_returning_nothing(tmp_path):
    store = RawStore(Settings(**VALID, data_dir=tmp_path, archive_enabled=False))
    key = store.save(document())

    with pytest.raises(ArchiveDisabledError, match="cannot be read back"):
        store.read(key)


def test_the_directory_is_not_even_created(tmp_path):
    target = tmp_path / "nothing-here"
    RawStore(Settings(**VALID, data_dir=target, archive_enabled=False))
    assert not (target / "raw").exists()


# --- end to end -----------------------------------------------------------


def build_archiver(settings, handler, session_factory):
    fetcher = Fetcher(
        settings=settings,
        client=httpx.Client(transport=httpx.MockTransport(handler)),
        robots=StubRobots(),
        throttle=NoWaitThrottle(1.0),
    )
    return Archiver(settings=settings, fetcher=fetcher, session_factory=session_factory)


def test_crawling_still_records_listings_without_an_archive(tmp_path, db_session_factory):
    """The point of the trade-off: listings are collected normally, only
    the raw documents are lost."""
    settings = Settings(
        **VALID,
        data_dir=tmp_path,
        archive_enabled=False,
        crawler_delay_seconds=1.0,
        crawler_respect_robots=False,
    )

    def handler(request):
        return httpx.Response(200, content=b"notice", headers=PDF)

    result = build_archiver(settings, handler, db_session_factory).archive(URL, "testbank")

    assert result.outcome is FetchOutcome.NEW
    with db_session_factory() as session:
        assert DocumentRepository(session).count_documents() == 1
    assert not any(tmp_path.rglob("*.pdf"))


def test_reparse_refuses_rather_than_silently_doing_nothing(tmp_path, db_session_factory):
    """Without this, reparse would report success having read zero
    documents, which looks like the parser found nothing to change."""
    settings = Settings(**VALID, data_dir=tmp_path, archive_enabled=False)

    class Adapter:
        source_id = "testbank"
        display_name = "Test"

        def discover(self, limit=None):
            return []

        def parse(self, document):
            return []

    crawler = Crawler(
        Adapter(),
        settings=settings,
        archiver=Archiver(settings=settings, session_factory=db_session_factory),
        session_factory=db_session_factory,
    )

    with pytest.raises(ArchiveDisabledError, match="Nothing to reparse"):
        crawler.reparse()
