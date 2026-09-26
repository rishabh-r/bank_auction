"""What we know about each URL from the last time we fetched it.

Powers two savings:
  - conditional GET: send the stored ETag so the server can reply "304 Not
    Modified" instead of resending the body
  - change detection: compare the content hash and skip all downstream
    parsing when nothing changed

Backed by a JSON file for now. Milestone 3 replaces the implementation with
a Postgres table; the interface below stays the same, so nothing that uses
it needs to change.
"""

import json
import logging
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path

log = logging.getLogger(__name__)


@dataclass(slots=True)
class UrlState:
    """Last known state of one URL."""

    url: str
    source_id: str
    sha256: str
    storage_key: str
    first_seen_at: str
    last_fetched_at: str
    last_changed_at: str
    fetch_count: int = 1
    etag: str | None = None
    last_modified: str | None = None


class UrlStateStore:
    """Persistent record of previously fetched URLs."""

    def __init__(self, path: Path):
        self._path = path
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._states: dict[str, UrlState] = self._load()

    def get(self, url: str) -> UrlState | None:
        return self._states.get(url)

    def record(
        self,
        url: str,
        source_id: str,
        sha256: str,
        storage_key: str,
        etag: str | None = None,
        last_modified: str | None = None,
    ) -> tuple[UrlState, bool]:
        """Record a successful fetch.

        Returns the state and whether the content differed from last time.
        """
        now = datetime.now(UTC).isoformat()
        previous = self._states.get(url)

        if previous is None:
            state = UrlState(
                url=url,
                source_id=source_id,
                sha256=sha256,
                storage_key=storage_key,
                first_seen_at=now,
                last_fetched_at=now,
                last_changed_at=now,
                etag=etag,
                last_modified=last_modified,
            )
            self._states[url] = state
            self._save()
            return state, True

        changed = previous.sha256 != sha256
        previous.last_fetched_at = now
        previous.fetch_count += 1
        previous.etag = etag
        previous.last_modified = last_modified
        if changed:
            previous.sha256 = sha256
            previous.storage_key = storage_key
            previous.last_changed_at = now
            log.info("content changed at %s", url)

        self._save()
        return previous, changed

    def touch(self, url: str) -> None:
        """Note that we checked a URL and it was unchanged (HTTP 304)."""
        if state := self._states.get(url):
            state.last_fetched_at = datetime.now(UTC).isoformat()
            state.fetch_count += 1
            self._save()

    def __len__(self) -> int:
        return len(self._states)

    def _load(self) -> dict[str, UrlState]:
        if not self._path.exists():
            return {}
        try:
            raw = json.loads(self._path.read_text("utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            log.error("could not read url state at %s: %s", self._path, exc)
            return {}
        return {url: UrlState(**data) for url, data in raw.items()}

    def _save(self) -> None:
        payload = {url: asdict(state) for url, state in self._states.items()}
        tmp = self._path.with_suffix(".json.part")
        tmp.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
        tmp.replace(self._path)
