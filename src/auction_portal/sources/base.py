"""The interface every data source implements.

The pipeline only ever sees this class. Adding a source means adding one
file; when a bank redesigns its site, exactly one adapter changes and the
tests tell you whether it still works.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from auction_portal.fetching.models import RawDocument


@dataclass(slots=True)
class ParsedListing:
    """One auction listing, normalised but not yet stored.

    Every field is optional except the identity ones. An adapter that is
    unsure about a value leaves it None and adds a quality flag; it never
    guesses, because a wrong reserve price is far worse than a missing one.
    """

    source_id: str
    external_id: str
    canonical_url: str
    asset_class: str  # 'property' | 'vehicle'

    asset_type: str | None = None
    asset_subtype: str | None = None
    title: str | None = None
    description: str | None = None

    address: str | None = None
    locality: str | None = None
    city: str | None = None
    district: str | None = None
    state: str | None = None
    pincode: str | None = None
    latitude: Decimal | None = None
    longitude: Decimal | None = None

    area_value: Decimal | None = None
    area_unit: str | None = None
    area_sqft: Decimal | None = None

    reserve_price: Decimal | None = None
    emd_amount: Decimal | None = None
    bid_increment: Decimal | None = None
    outstanding_dues: Decimal | None = None

    auction_start_at: datetime | None = None
    auction_end_at: datetime | None = None
    emd_deadline_at: datetime | None = None
    inspection_from: datetime | None = None
    inspection_to: datetime | None = None

    bank_name: str | None = None
    branch_name: str | None = None
    possession_type: str | None = None
    symbolic_possession_date: date | None = None
    physical_possession_date: date | None = None
    npa_date: date | None = None
    legal_basis: str | None = None

    authorised_officer_name: str | None = None
    authorised_officer_phone: str | None = None

    status: str = "upcoming"
    asset_key: str | None = None
    confidence: Decimal = Decimal("1.00")
    quality_flags: list[str] = field(default_factory=list)
    raw_payload: dict[str, Any] | None = None

    def flag(self, name: str) -> None:
        if name not in self.quality_flags:
            self.quality_flags.append(name)


class SourceAdapter(ABC):
    """Base class for every auction data source."""

    source_id: str
    display_name: str
    base_url: str
    asset_class: str = "property"

    #: Set False for sources whose terms or robots.txt we have not cleared.
    enabled: bool = True

    @abstractmethod
    def discover(self, limit: int | None = None) -> list[str]:
        """URLs worth fetching this run.

        Cheap relative to fetching: usually a sitemap or an index page. The
        caller diffs the result against what is already archived and only
        fetches what is new.
        """

    @abstractmethod
    def parse(self, document: RawDocument) -> list[ParsedListing]:
        """Turn one fetched document into listings.

        Returns a list because a single notice routinely covers several
        properties (see 'Item No. 1-4' in a typical bank sale notice).
        """

    def __repr__(self) -> str:
        return f"<{type(self).__name__} {self.source_id}>"
