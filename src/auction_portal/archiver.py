"""Ties fetching and storage together.

The full flow for one URL:

    1. look up what we knew about this URL last time
    2. fetch, sending ETag / If-Modified-Since so the server can say 304
    3. if the server said 304, or the bytes hash to what we already have,
       stop here - nothing downstream needs to run
    4. otherwise archive the bytes and record the new state

Step 3 is where roughly 90% of crawls end, which is what keeps the parsing
and OCR bill small.
"""

import logging

from auction_portal.config import Settings, get_settings
from auction_portal.fetching.client import Fetcher
from auction_portal.fetching.models import FetchOutcome, FetchResult
from auction_portal.storage.raw_store import RawStore
from auction_portal.storage.url_state import UrlStateStore

log = logging.getLogger(__name__)


class Archiver:
    def __init__(
        self,
        settings: Settings | None = None,
        fetcher: Fetcher | None = None,
        store: RawStore | None = None,
        state: UrlStateStore | None = None,
    ):
        self._settings = settings or get_settings()
        self._fetcher = fetcher or Fetcher(self._settings)
        self._store = store or RawStore(self._settings)
        self._state = state or UrlStateStore(self._settings.data_dir / "state" / "url_state.json")

    def archive(self, url: str, source_id: str) -> FetchResult:
        """Fetch a URL and archive it if the content is new."""
        previous = self._state.get(url)

        result = self._fetcher.fetch(
            url,
            source_id=source_id,
            etag=previous.etag if previous else None,
            last_modified=previous.last_modified if previous else None,
        )

        if result.outcome is FetchOutcome.NOT_MODIFIED:
            self._state.touch(url)
            return result

        if result.document is None:
            return result  # blocked or failed; nothing to store

        document = result.document

        if previous is not None and previous.sha256 == document.sha256:
            self._state.record(
                url,
                source_id,
                document.sha256,
                previous.storage_key,
                etag=document.etag,
                last_modified=document.last_modified,
            )
            log.info("unchanged: %s", url)
            return FetchResult(
                outcome=FetchOutcome.UNCHANGED,
                url=url,
                document=document,
                storage_key=previous.storage_key,
            )

        storage_key = self._store.save(document)
        self._state.record(
            url,
            source_id,
            document.sha256,
            storage_key,
            etag=document.etag,
            last_modified=document.last_modified,
        )
        return FetchResult(
            outcome=FetchOutcome.NEW,
            url=url,
            document=document,
            storage_key=storage_key,
        )

    @property
    def store(self) -> RawStore:
        return self._store

    @property
    def state(self) -> UrlStateStore:
        return self._state

    def close(self) -> None:
        self._fetcher.close()

    def __enter__(self) -> "Archiver":
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()
