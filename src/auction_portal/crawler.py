"""Runs a source adapter end to end.

    discover URLs -> fetch and archive -> parse -> normalise -> store

Every stage is resumable. A crawl that dies halfway leaves the archive and
the database consistent, and re-running it skips everything already done.
"""

import logging
from dataclasses import dataclass, field

from sqlalchemy.orm import Session, sessionmaker

from auction_portal.archiver import Archiver
from auction_portal.config import Settings, get_settings
from auction_portal.db.listing_repository import ListingRepository
from auction_portal.db.repository import DocumentRepository
from auction_portal.db.session import get_sessionmaker
from auction_portal.fetching.models import FetchOutcome, RawDocument
from auction_portal.sources.base import SourceAdapter

log = logging.getLogger(__name__)


@dataclass
class CrawlReport:
    source_id: str
    discovered: int = 0
    fetched: int = 0
    unchanged: int = 0
    blocked: int = 0
    failed: int = 0
    listings_created: int = 0
    listings_updated: int = 0
    listings_unchanged: int = 0
    parse_failures: int = 0
    errors: list[str] = field(default_factory=list)

    def summary(self) -> str:
        return (
            f"{self.source_id}: {self.discovered} discovered, "
            f"{self.fetched} fetched, {self.unchanged} unchanged, "
            f"{self.listings_created} new listings, "
            f"{self.listings_updated} updated"
        )


class Crawler:
    def __init__(
        self,
        adapter: SourceAdapter,
        settings: Settings | None = None,
        archiver: Archiver | None = None,
        session_factory: sessionmaker[Session] | None = None,
    ):
        self._adapter = adapter
        self._settings = settings or get_settings()
        self._sessions = session_factory or get_sessionmaker()
        self._archiver = archiver or Archiver(self._settings, session_factory=self._sessions)

    def run(self, limit: int | None = None, skip_unchanged: bool = True) -> CrawlReport:
        report = CrawlReport(source_id=self._adapter.source_id)

        urls = self._adapter.discover(limit=limit)
        report.discovered = len(urls)
        log.info("%s: %d urls to consider", self._adapter.source_id, len(urls))

        for position, url in enumerate(urls, start=1):
            try:
                self._process(url, report, skip_unchanged)
            except Exception as exc:  # one bad page must not stop the crawl
                report.failed += 1
                message = f"{url}: {type(exc).__name__}: {exc}"
                report.errors.append(message)
                log.exception("failed processing %s", url)

            if position % 25 == 0:
                log.info("  %d/%d  %s", position, len(urls), report.summary())

        log.info("done - %s", report.summary())
        return report

    def _process(self, url: str, report: CrawlReport, skip_unchanged: bool) -> None:
        result = self._archiver.archive(url, source_id=self._adapter.source_id)

        if result.outcome is FetchOutcome.BLOCKED_BY_ROBOTS:
            report.blocked += 1
            return
        if result.outcome is FetchOutcome.FAILED:
            report.failed += 1
            return
        if result.outcome is FetchOutcome.NOT_MODIFIED:
            report.unchanged += 1
            return
        if result.outcome is FetchOutcome.UNCHANGED:
            report.unchanged += 1
            if skip_unchanged:
                return

        if result.document is None:
            return

        report.fetched += 1

        listings = self._adapter.parse(result.document)
        if not listings:
            report.parse_failures += 1
            return

        with self._sessions.begin() as session:
            documents = DocumentRepository(session)
            archived = documents.get_document_by_hash(url, result.document.sha256)
            document_id = archived.id if archived else None

            repository = ListingRepository(session)
            for parsed in listings:
                _, action = repository.upsert(parsed, source_document_id=document_id)
                if action == "created":
                    report.listings_created += 1
                elif action == "updated":
                    report.listings_updated += 1
                else:
                    report.listings_unchanged += 1

    def reparse(self, limit: int | None = None) -> CrawlReport:
        """Re-run parsing over already-archived documents. No network access.

        This is the payoff for storing raw bytes immutably: when the parser
        improves, history is reprocessed instead of re-crawled. Nobody's
        server is touched and nothing is lost.
        """
        report = CrawlReport(source_id=self._adapter.source_id)
        store = self._archiver.store

        with self._sessions() as session:
            documents = DocumentRepository(session).documents_for_source(
                self._adapter.source_id, limit=limit
            )
            records = [(d.id, d.storage_key, d.source_url) for d in documents]

        report.discovered = len(records)
        log.info("reparsing %d archived documents", len(records))

        for document_id, storage_key, url in records:
            try:
                content = store.read(storage_key)
            except OSError as exc:
                report.failed += 1
                report.errors.append(f"{storage_key}: {exc}")
                continue

            document = RawDocument(
                source_id=self._adapter.source_id,
                url=url,
                content=content,
                mime_type="text/html",
                http_status=200,
            )
            listings = self._adapter.parse(document)
            if not listings:
                report.parse_failures += 1
                continue

            report.fetched += 1
            with self._sessions.begin() as session:
                repository = ListingRepository(session)
                for parsed in listings:
                    _, action = repository.upsert(parsed, source_document_id=document_id)
                    if action == "created":
                        report.listings_created += 1
                    elif action == "updated":
                        report.listings_updated += 1
                    else:
                        report.listings_unchanged += 1

        log.info("reparse done - %s", report.summary())
        return report

    def close(self) -> None:
        self._archiver.close()

    def __enter__(self) -> "Crawler":
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()
