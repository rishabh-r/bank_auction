"""Data structures for fetched content."""

import hashlib
import re
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


#: Fragments that change on every request without the page's meaning
#: changing. Removed before computing the change-detection hash.
#:
#: BAANKNET renders a site-wide visitor counter into every page, so two
#: fetches of an untouched listing differ by a handful of digits. Without
#: this, each hourly refresh would archive a fresh copy of every page -
#: roughly 630 MB a day carrying no information.
#:
#: Kept deliberately narrow. Over-matching here would hide a genuine
#: change, which is far worse than storing a duplicate.
_VOLATILE_FRAGMENTS: tuple[re.Pattern[bytes], ...] = (
    # "Visitor Count:</span><span ...>2813191</span>"
    re.compile(rb"(itor Count.{0,200}?)\d{4,}", re.DOTALL),
    # The same number again inside the Next.js payload.
    re.compile(rb'(\\"children\\":)\d{6,}(\]\]\}\],\[\\"\$\\",\\"div)'),
)


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
        """Fingerprint of the exact bytes, for integrity and addressing."""
        return hashlib.sha256(self.content).hexdigest()

    @cached_property
    def canonical_sha256(self) -> str:
        """Fingerprint ignoring content that changes on every request.

        Used to decide whether a page has *meaningfully* changed.
        `sha256` remains the true hash of what we stored; this is only
        for change detection, so a visitor counter ticking over does not
        look like a republished notice.
        """
        content = self.content
        for pattern in _VOLATILE_FRAGMENTS:
            content = pattern.sub(rb"\g<1>", content)
        return hashlib.sha256(content).hexdigest()

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
