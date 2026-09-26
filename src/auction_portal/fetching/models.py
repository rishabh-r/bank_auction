"""Data structures for fetched content."""

import hashlib
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from functools import cached_property

# Map content types to file extensions for the archive. Unknown types are
# stored as .bin rather than guessed at.
_EXTENSIONS = {
    "application/pdf": ".pdf",
    "text/html": ".html",
    "application/xhtml+xml": ".html",
    "application/json": ".json",
    "text/plain": ".txt",
    "text/xml": ".xml",
    "application/xml": ".xml",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": ".xlsx",
    "application/vnd.ms-excel": ".xls",
    "image/jpeg": ".jpg",
    "image/png": ".png",
}


class FetchOutcome(StrEnum):
    """What happened on a fetch attempt."""

    NEW = "new"  # content we have never seen at this URL
    UNCHANGED = "unchanged"  # byte-identical to what we already hold
    NOT_MODIFIED = "not_modified"  # server said 304; we did not re-download
    BLOCKED_BY_ROBOTS = "blocked_by_robots"
    FAILED = "failed"


# No slots=True here: cached_property needs a __dict__ to memoise the hash.
@dataclass(frozen=True)
class RawDocument:
    """Bytes exactly as received, plus how and when we got them.

    Immutable by design. Once fetched, a document is never altered; parsers
    read from it and write their output elsewhere.
    """

    source_id: str
    url: str
    content: bytes
    mime_type: str
    http_status: int
    fetched_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    etag: str | None = None
    last_modified: str | None = None

    @cached_property
    def sha256(self) -> str:
        """Content fingerprint. Identical bytes always give an identical hash."""
        return hashlib.sha256(self.content).hexdigest()

    @property
    def size_bytes(self) -> int:
        return len(self.content)

    @property
    def extension(self) -> str:
        return _EXTENSIONS.get(self.mime_type.split(";")[0].strip().lower(), ".bin")


@dataclass(frozen=True, slots=True)
class FetchResult:
    """Result of a fetch attempt, including the cases where nothing was stored."""

    outcome: FetchOutcome
    url: str
    document: RawDocument | None = None
    storage_key: str | None = None
    error: str | None = None

    @property
    def is_new_content(self) -> bool:
        return self.outcome is FetchOutcome.NEW
