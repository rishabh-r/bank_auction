"""Storing parsed listings.

Two behaviours matter here:

  1. Upsert on (source_id, external_id), so re-crawling updates rather than
     duplicates.
  2. Record every field change in listing_revisions. Price cuts and
     postponements are the most valuable signal the portal can offer, and
     they are only visible if we keep the history.
"""

import hashlib
import json
import logging
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from auction_portal.db.models import Listing, ListingRevision
from auction_portal.sources.base import ParsedListing

log = logging.getLogger(__name__)

#: Only listings we are confident about are shown publicly. Everything else
#: is stored but withheld - fewer listings, but no wrong prices.
PUBLISH_THRESHOLD = Decimal("0.70")

#: Changes to these fields are worth a history row.
TRACKED_FIELDS = (
    "reserve_price",
    "emd_amount",
    "bid_increment",
    "auction_start_at",
    "auction_end_at",
    "emd_deadline_at",
    "status",
    "possession_type",
    "address",
    "city",
    "state",
)

_COPIED_FIELDS = (
    "canonical_url",
    "asset_class",
    "asset_type",
    "asset_subtype",
    "title",
    "description",
    "address",
    "locality",
    "city",
    "district",
    "state",
    "pincode",
    "latitude",
    "longitude",
    "area_value",
    "area_unit",
    "area_sqft",
    "reserve_price",
    "emd_amount",
    "bid_increment",
    "outstanding_dues",
    "auction_start_at",
    "auction_end_at",
    "emd_deadline_at",
    "inspection_from",
    "inspection_to",
    "bank_name",
    "branch_name",
    "possession_type",
    "symbolic_possession_date",
    "physical_possession_date",
    "npa_date",
    "legal_basis",
    "authorised_officer_name",
    "authorised_officer_phone",
    "status",
    "asset_key",
)


class ListingRepository:
    def __init__(self, session: Session):
        self._session = session

    # --- reads ------------------------------------------------------------

    def get(self, source_id: str, external_id: str) -> Listing | None:
        return self._session.scalar(
            select(Listing).where(
                Listing.source_id == source_id, Listing.external_id == external_id
            )
        )

    def count(self, published_only: bool = False) -> int:
        stmt = select(func.count()).select_from(Listing)
        if published_only:
            stmt = stmt.where(Listing.is_published.is_(True))
        return self._session.scalar(stmt) or 0

    def count_by(self, column) -> dict[str, int]:
        rows = self._session.execute(
            select(column, func.count())
            .where(column.is_not(None))
            .group_by(column)
            .order_by(func.count().desc())
        )
        return dict(rows.all())

    def revisions_for(self, listing_id: int) -> list[ListingRevision]:
        return list(
            self._session.scalars(
                select(ListingRevision)
                .where(ListingRevision.listing_id == listing_id)
                .order_by(ListingRevision.changed_at)
            )
        )

    # --- writes -----------------------------------------------------------

    def upsert(
        self, parsed: ParsedListing, source_document_id: int | None = None
    ) -> tuple[Listing, str]:
        """Insert or update one listing.

        Returns the row and one of 'created', 'updated', 'unchanged'.
        """
        content_hash = self._hash(parsed)
        existing = self.get(parsed.source_id, parsed.external_id)
        now = datetime.now(UTC)

        if existing is None:
            listing = Listing(
                source_id=parsed.source_id,
                external_id=parsed.external_id,
                source_document_id=source_document_id,
                content_hash=content_hash,
                confidence=parsed.confidence,
                quality_flags=parsed.quality_flags or None,
                raw_payload=parsed.raw_payload,
                is_published=parsed.confidence >= PUBLISH_THRESHOLD,
                round_number=1,
            )
            for name in _COPIED_FIELDS:
                setattr(listing, name, getattr(parsed, name))
            self._session.add(listing)
            return listing, "created"

        existing.last_verified_at = now

        if existing.content_hash == content_hash:
            return existing, "unchanged"

        for name in TRACKED_FIELDS:
            before = getattr(existing, name)
            after = getattr(parsed, name)
            if before == after:
                continue
            self._session.add(
                ListingRevision(
                    listing_id=existing.id,
                    field_name=name,
                    old_value=_stringify(before),
                    new_value=_stringify(after),
                    source_document_id=source_document_id,
                )
            )
            if name == "reserve_price" and before and after:
                direction = "down" if after < before else "up"
                log.info(
                    "reserve price %s for %s/%s: %s -> %s",
                    direction,
                    parsed.source_id,
                    parsed.external_id,
                    before,
                    after,
                )

        for name in _COPIED_FIELDS:
            setattr(existing, name, getattr(parsed, name))

        existing.content_hash = content_hash
        existing.confidence = parsed.confidence
        existing.quality_flags = parsed.quality_flags or None
        existing.raw_payload = parsed.raw_payload
        existing.is_published = parsed.confidence >= PUBLISH_THRESHOLD
        existing.source_document_id = source_document_id
        existing.updated_at = now
        return existing, "updated"

    # --- internals --------------------------------------------------------

    @staticmethod
    def _hash(parsed: ParsedListing) -> str:
        """Fingerprint of the meaningful fields.

        Excludes raw_payload and confidence so that an unrelated upstream
        edit does not register as a change to the listing itself.
        """
        data: dict[str, Any] = {name: _stringify(getattr(parsed, name)) for name in _COPIED_FIELDS}
        encoded = json.dumps(data, sort_keys=True, ensure_ascii=False)
        return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _stringify(value: object) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)
