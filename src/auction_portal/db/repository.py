"""Database access for archived documents.

Replaces the JSON file used in Milestone 2. Everything here is written to be
safely re-runnable: a worker that crashes and retries must not create
duplicate rows.
"""

import logging
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from auction_portal.db.models import SourceDocument, UrlStateRow
from auction_portal.fetching.models import RawDocument

log = logging.getLogger(__name__)


class DocumentRepository:
    """Reads and writes source_documents and url_state."""

    def __init__(self, session: Session):
        self._session = session

    # --- reads ------------------------------------------------------------

    def get_url_state(self, url: str) -> UrlStateRow | None:
        return self._session.get(UrlStateRow, url)

    def get_document_by_hash(self, source_url: str, sha256: str) -> SourceDocument | None:
        return self._session.scalar(
            select(SourceDocument).where(
                SourceDocument.source_url == source_url,
                SourceDocument.content_sha256 == sha256,
            )
        )

    def count_documents(self, source_id: str | None = None) -> int:
        stmt = select(func.count()).select_from(SourceDocument)
        if source_id:
            stmt = stmt.where(SourceDocument.source_id == source_id)
        return self._session.scalar(stmt) or 0

    def count_urls(self) -> int:
        return self._session.scalar(select(func.count()).select_from(UrlStateRow)) or 0

    def documents_per_source(self) -> dict[str, int]:
        rows = self._session.execute(
            select(SourceDocument.source_id, func.count())
            .group_by(SourceDocument.source_id)
            .order_by(func.count().desc())
        )
        return dict(rows.all())

    def documents_for_source(
        self, source_id: str, limit: int | None = None
    ) -> list[SourceDocument]:
        """Archived documents for one source, newest first."""
        stmt = (
            select(SourceDocument)
            .where(SourceDocument.source_id == source_id)
            .order_by(SourceDocument.fetched_at.desc())
        )
        if limit:
            stmt = stmt.limit(limit)
        return list(self._session.scalars(stmt))

    def recent_documents(self, limit: int = 10) -> list[SourceDocument]:
        return list(
            self._session.scalars(
                select(SourceDocument).order_by(SourceDocument.fetched_at.desc()).limit(limit)
            )
        )

    # --- writes -----------------------------------------------------------

    def record_document(
        self, document: RawDocument, storage_key: str
    ) -> tuple[SourceDocument, bool]:
        """Record a downloaded document.

        Returns the row and whether it is new content for this URL. Uses an
        upsert so that a retried task cannot insert a duplicate - the
        (source_url, content_sha256) unique constraint is the safety net.
        """
        now = datetime.now(UTC)

        stmt = (
            insert(SourceDocument)
            .values(
                source_id=document.source_id,
                source_url=document.url,
                fetched_at=document.fetched_at,
                content_sha256=document.sha256,
                storage_key=storage_key,
                mime_type=document.mime_type,
                http_status=document.http_status,
                size_bytes=document.size_bytes,
                etag=document.etag,
                last_modified=document.last_modified,
                last_seen_at=now,
            )
            .on_conflict_do_update(
                constraint="uq_source_doc_url_hash",
                # Seen these exact bytes before: just note that we saw them
                # again. The original row, and its fetched_at, stay intact.
                set_={"last_seen_at": now},
            )
            .returning(SourceDocument.id)
        )
        document_id = self._session.execute(stmt).scalar_one()

        changed = self._update_url_state(document, storage_key, document_id, now)
        record = self._session.get(SourceDocument, document_id)
        return record, changed

    def record_unchanged_fetch(self, document: RawDocument) -> None:
        """Note a fetch whose content had not meaningfully changed.

        No new source_documents row: the bytes differ only in noise such
        as a visitor counter, so a new row would claim a version that
        does not exist. The existing one has its last_seen_at bumped.
        """
        now = datetime.now(UTC)

        state = self._session.get(UrlStateRow, document.url)
        if state is None:
            return

        state.last_fetched_at = now
        state.fetch_count += 1
        state.unchanged_streak += 1
        state.etag = document.etag
        state.last_modified = document.last_modified

        if state.current_document_id is not None:
            existing = self._session.get(SourceDocument, state.current_document_id)
            if existing is not None:
                existing.last_seen_at = now

    def touch_url(self, url: str) -> None:
        """Server replied 304: we checked, nothing changed, nothing downloaded."""
        state = self._session.get(UrlStateRow, url)
        if state is None:
            return
        state.last_fetched_at = datetime.now(UTC)
        state.fetch_count += 1
        state.unchanged_streak += 1

    # --- internals --------------------------------------------------------

    def _update_url_state(
        self,
        document: RawDocument,
        storage_key: str,
        document_id: int,
        now: datetime,
    ) -> bool:
        state = self._session.get(UrlStateRow, document.url)

        if state is None:
            self._session.add(
                UrlStateRow(
                    url=document.url,
                    source_id=document.source_id,
                    content_sha256=document.sha256,
                    canonical_sha256=document.canonical_sha256,
                    storage_key=storage_key,
                    etag=document.etag,
                    last_modified=document.last_modified,
                    first_seen_at=now,
                    last_fetched_at=now,
                    last_changed_at=now,
                    fetch_count=1,
                    unchanged_streak=0,
                    current_document_id=document_id,
                )
            )
            return True

        # Canonical hash: ignores per-request noise such as a visitor
        # counter, so only a real republication counts as a change.
        previous = state.canonical_sha256 or state.content_sha256
        changed = previous != document.canonical_sha256

        state.last_fetched_at = now
        state.fetch_count += 1
        state.etag = document.etag
        state.last_modified = document.last_modified

        if changed:
            log.info("content changed at %s", document.url)
            state.content_sha256 = document.sha256
            state.canonical_sha256 = document.canonical_sha256
            state.storage_key = storage_key
            state.last_changed_at = now
            state.current_document_id = document_id
            state.unchanged_streak = 0
        else:
            state.unchanged_streak += 1

        return changed
