"""Ties fetching, storage and the database together.

The full flow for one URL:

    1. look up what the database knows about this URL from last time
    2. fetch, sending ETag / If-Modified-Since so the server can say 304
    3. if the server said 304, or the bytes hash to what we already have,
       record that we checked and stop - nothing downstream needs to run
    4. otherwise archive the bytes and record a new source_documents row

Step 3 is where roughly 90% of crawls end, which is what keeps the parsing
and OCR bill small.
"""

import logging

from sqlalchemy.orm import Session, sessionmaker

from auction_portal.config import Settings, get_settings
from auction_portal.db.repository import DocumentRepository
from auction_portal.db.session import get_sessionmaker
from auction_portal.fetching.client import Fetcher
from auction_portal.fetching.models import FetchOutcome, FetchResult
from auction_portal.storage.raw_store import RawStore

log = logging.getLogger(__name__)


class Archiver:
    def __init__(
        self,
        settings: Settings | None = None,
        fetcher: Fetcher | None = None,
        store: RawStore | None = None,
        session_factory: sessionmaker[Session] | None = None,
    ):
        self._settings = settings or get_settings()
        self._fetcher = fetcher or Fetcher(self._settings)
        self._store = store or RawStore(self._settings)
        self._sessions = session_factory or get_sessionmaker()

    def archive(self, url: str, source_id: str) -> FetchResult:
        """Fetch a URL and archive it if the content is new."""
        with self._sessions() as session:
            state = DocumentRepository(session).get_url_state(url)
            etag = state.etag if state else None
            last_modified = state.last_modified if state else None
            known_hash = state.canonical_sha256 or state.content_sha256 if state else None
            known_key = state.storage_key if state else None

        result = self._fetcher.fetch(
            url, source_id=source_id, etag=etag, last_modified=last_modified
        )

        if result.outcome is FetchOutcome.NOT_MODIFIED:
            with self._sessions.begin() as session:
                DocumentRepository(session).touch_url(url)
            return result

        if result.document is None:
            return result  # blocked by robots, or failed; nothing to store

        document = result.document

        # Compared on the canonical hash, not the raw one. Some sources
        # embed a visitor counter or similar in every page, so the bytes
        # differ on every fetch while the notice itself has not changed.
        #
        # Write the bytes before the database row. If the process dies in
        # between we get an unreferenced file, which is harmless; the reverse
        # would leave a row pointing at a file that does not exist.
        if known_hash == document.canonical_sha256 and known_key:
            # Nothing meaningful changed. No new file and no new
            # source_documents row, because there is no new version to
            # record - only a note that we looked.
            log.info("unchanged: %s", url)
            with self._sessions.begin() as session:
                DocumentRepository(session).record_unchanged_fetch(document)
            return FetchResult(
                outcome=FetchOutcome.UNCHANGED,
                url=url,
                document=document,
                storage_key=known_key,
            )

        storage_key = self._store.save(document)
        with self._sessions.begin() as session:
            DocumentRepository(session).record_document(document, storage_key)

        return FetchResult(
            outcome=FetchOutcome.NEW, url=url, document=document, storage_key=storage_key
        )

    @property
    def store(self) -> RawStore:
        return self._store

    @property
    def sessions(self) -> sessionmaker[Session]:
        return self._sessions

    def close(self) -> None:
        self._fetcher.close()

    def __enter__(self) -> "Archiver":
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()
