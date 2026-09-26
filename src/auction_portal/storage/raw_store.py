"""Immutable archive of fetched documents.

Ground rule 1 of this project: raw downloaded data is never modified or
deleted. Parsers get rewritten constantly; re-downloading from a bank's
website is slow, impolite and sometimes impossible once a notice is taken
down. So everything we fetch is written once and kept.

Files are content-addressed - the filename is the SHA-256 of the bytes.
Two consequences fall out of that for free:
  - identical content can never be stored twice
  - a file whose content changed cannot overwrite the old version

Local disk for now; the same interface moves to S3 in Milestone 6.
"""

import json
import logging
from dataclasses import asdict
from pathlib import Path

from auction_portal.config import Settings, get_settings
from auction_portal.fetching.models import RawDocument

log = logging.getLogger(__name__)


class RawStore:
    """Content-addressed store for raw documents."""

    def __init__(self, settings: Settings | None = None, root: Path | None = None):
        self._root = root or (settings or get_settings()).raw_dir
        self._root.mkdir(parents=True, exist_ok=True)

    def storage_key(self, document: RawDocument) -> str:
        """Stable path for a document, e.g. 'ibbi/2026/09/26/a3f5...pdf'.

        Date-partitioned so the archive stays browsable by hand as it grows.
        """
        stamp = document.fetched_at
        return f"{document.source_id}/{stamp:%Y/%m/%d}/{document.sha256}{document.extension}"

    def exists(self, document: RawDocument) -> bool:
        """Have we already archived these exact bytes today, for this source?"""
        return self._path_for(self.storage_key(document)).exists()

    def contains_hash(self, source_id: str, sha256: str) -> bool:
        """Have we ever archived this content for this source, on any date?"""
        source_dir = self._root / source_id
        if not source_dir.is_dir():
            return False
        return any(source_dir.rglob(f"{sha256}.*"))

    def save(self, document: RawDocument) -> str:
        """Archive a document. Returns its storage key.

        Writing is atomic: content goes to a temporary file and is renamed
        into place, so a crash mid-write cannot leave a truncated archive.
        """
        key = self.storage_key(document)
        path = self._path_for(key)

        if path.exists():
            log.debug("already archived: %s", key)
            return key

        path.parent.mkdir(parents=True, exist_ok=True)

        tmp = path.with_suffix(path.suffix + ".part")
        tmp.write_bytes(document.content)
        tmp.replace(path)

        self._write_metadata(path, document, key)
        log.info("archived %s (%.1f KB)", key, document.size_bytes / 1024)
        return key

    def read(self, key: str) -> bytes:
        return self._path_for(key).read_bytes()

    def metadata(self, key: str) -> dict:
        return json.loads(self._meta_path(self._path_for(key)).read_text("utf-8"))

    def count(self, source_id: str | None = None) -> int:
        """Number of archived documents, optionally for one source."""
        base = self._root / source_id if source_id else self._root
        if not base.is_dir():
            return 0
        return sum(1 for p in base.rglob("*") if p.is_file() and p.suffix != ".json")

    def _write_metadata(self, path: Path, document: RawDocument, key: str) -> None:
        """Provenance sidecar: where this came from and when."""
        meta = asdict(document)
        meta.pop("content")  # the bytes live in the file next to this
        meta["fetched_at"] = document.fetched_at.isoformat()
        meta["sha256"] = document.sha256
        meta["size_bytes"] = document.size_bytes
        meta["storage_key"] = key
        self._meta_path(path).write_text(
            json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8"
        )

    def _path_for(self, key: str) -> Path:
        return self._root / key

    @staticmethod
    def _meta_path(path: Path) -> Path:
        return path.with_suffix(path.suffix + ".meta.json")
