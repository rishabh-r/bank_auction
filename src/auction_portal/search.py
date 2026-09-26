"""Searching and filtering listings.

Kept separate from the web layer so the same query logic serves the HTML
pages, the JSON API and, later, saved-search alerts.

Only published listings are ever returned by default. A listing we are not
confident about is withheld rather than shown with a possibly wrong price.
"""

from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from sqlalchemy import Select, func, or_, select
from sqlalchemy.orm import Session

from auction_portal.db.models import Listing

SortOption = Literal["auction_date", "price_low", "price_high", "newest", "relevance"]

SORT_LABELS: dict[str, str] = {
    "auction_date": "Auction date (soonest)",
    "price_low": "Price (lowest first)",
    "price_high": "Price (highest first)",
    "newest": "Recently added",
    "relevance": "Best match",
}

PAGE_SIZE = 20
MAX_PAGE_SIZE = 100


@dataclass(slots=True)
class SearchQuery:
    text: str | None = None
    bank: str | None = None
    state: str | None = None
    city: str | None = None
    asset_type: str | None = None
    possession: str | None = None
    status: str | None = None
    min_price: Decimal | None = None
    max_price: Decimal | None = None
    auction_before: date | None = None
    auction_after: date | None = None
    sort: SortOption = "auction_date"
    page: int = 1
    page_size: int = PAGE_SIZE
    include_unpublished: bool = False

    def __post_init__(self) -> None:
        self.page = max(1, self.page)
        self.page_size = max(1, min(self.page_size, MAX_PAGE_SIZE))
        if self.text:
            self.text = self.text.strip() or None

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.page_size

    def active_filters(self) -> dict[str, str]:
        """Filters currently applied, for showing removable chips in the UI."""
        labels = {
            "q": self.text,
            "bank": self.bank,
            "state": self.state,
            "city": self.city,
            "asset_type": self.asset_type,
            "possession": self.possession,
            "status": self.status,
            "min_price": f"min {self.min_price:,.0f}" if self.min_price else None,
            "max_price": f"max {self.max_price:,.0f}" if self.max_price else None,
        }
        return {key: value for key, value in labels.items() if value}


@dataclass(slots=True)
class Facet:
    value: str
    count: int


@dataclass(slots=True)
class SearchResults:
    listings: list[Listing]
    total: int
    page: int
    page_size: int
    facets: dict[str, list[Facet]] = field(default_factory=dict)

    @property
    def total_pages(self) -> int:
        return max(1, -(-self.total // self.page_size))  # ceiling division

    @property
    def has_previous(self) -> bool:
        return self.page > 1

    @property
    def has_next(self) -> bool:
        return self.page < self.total_pages

    @property
    def first_index(self) -> int:
        return 0 if not self.total else (self.page - 1) * self.page_size + 1

    @property
    def last_index(self) -> int:
        return min(self.page * self.page_size, self.total)


class SearchService:
    #: Columns offered as facets in the sidebar.
    FACET_COLUMNS = {
        "state": Listing.state,
        "city": Listing.city,
        "asset_type": Listing.asset_type,
        "bank": Listing.bank_name,
        "possession": Listing.possession_type,
        "status": Listing.status,
    }

    def __init__(self, session: Session):
        self._session = session

    def search(self, query: SearchQuery, with_facets: bool = True) -> SearchResults:
        stmt = self._apply_filters(select(Listing), query)

        total = self._session.scalar(select(func.count()).select_from(stmt.subquery())) or 0

        stmt = self._apply_sort(stmt, query)
        listings = list(self._session.scalars(stmt.offset(query.offset).limit(query.page_size)))

        facets = self._facets(query) if with_facets else {}

        return SearchResults(
            listings=listings,
            total=total,
            page=query.page,
            page_size=query.page_size,
            facets=facets,
        )

    def get(self, listing_id: int, include_unpublished: bool = False) -> Listing | None:
        listing = self._session.get(Listing, listing_id)
        if listing is None:
            return None
        if not listing.is_published and not include_unpublished:
            return None
        return listing

    def nearby(self, listing: Listing, limit: int = 4) -> list[Listing]:
        """Other published listings in the same city."""
        if not listing.city:
            return []
        return list(
            self._session.scalars(
                select(Listing)
                .where(
                    Listing.city == listing.city,
                    Listing.id != listing.id,
                    Listing.is_published.is_(True),
                )
                .order_by(Listing.auction_start_at.asc().nulls_last())
                .limit(limit)
            )
        )

    def totals(self) -> dict[str, int]:
        published = select(func.count()).select_from(Listing).where(Listing.is_published.is_(True))
        return {
            "listings": self._session.scalar(published) or 0,
            "states": self._session.scalar(
                select(func.count(func.distinct(Listing.state))).where(
                    Listing.is_published.is_(True), Listing.state.is_not(None)
                )
            )
            or 0,
            "banks": self._session.scalar(
                select(func.count(func.distinct(Listing.bank_name))).where(
                    Listing.is_published.is_(True), Listing.bank_name.is_not(None)
                )
            )
            or 0,
        }

    # --- internals --------------------------------------------------------

    def _apply_filters(self, stmt: Select, query: SearchQuery) -> Select:
        if not query.include_unpublished:
            stmt = stmt.where(Listing.is_published.is_(True))

        if query.text:
            stmt = stmt.where(
                or_(
                    Listing.search_vector.op("@@")(func.websearch_to_tsquery("simple", query.text)),
                    Listing.title.ilike(f"%{query.text}%"),
                )
            )

        for value, column in (
            (query.bank, Listing.bank_name),
            (query.state, Listing.state),
            (query.city, Listing.city),
            (query.asset_type, Listing.asset_type),
            (query.possession, Listing.possession_type),
            (query.status, Listing.status),
        ):
            if value:
                stmt = stmt.where(column == value)

        if query.min_price is not None:
            stmt = stmt.where(Listing.reserve_price >= query.min_price)
        if query.max_price is not None:
            stmt = stmt.where(Listing.reserve_price <= query.max_price)

        if query.auction_after is not None:
            stmt = stmt.where(Listing.auction_start_at >= _start_of(query.auction_after))
        if query.auction_before is not None:
            stmt = stmt.where(Listing.auction_start_at <= _end_of(query.auction_before))

        return stmt

    def _apply_sort(self, stmt: Select, query: SearchQuery) -> Select:
        if query.sort == "price_low":
            return stmt.order_by(Listing.reserve_price.asc().nulls_last())
        if query.sort == "price_high":
            return stmt.order_by(Listing.reserve_price.desc().nulls_last())
        if query.sort == "newest":
            return stmt.order_by(Listing.first_seen_at.desc())
        if query.sort == "relevance" and query.text:
            rank = func.ts_rank(
                Listing.search_vector, func.websearch_to_tsquery("simple", query.text)
            )
            return stmt.order_by(rank.desc(), Listing.auction_start_at.asc().nulls_last())
        return stmt.order_by(Listing.auction_start_at.asc().nulls_last(), Listing.id)

    def _facets(self, query: SearchQuery) -> dict[str, list[Facet]]:
        """Counts per facet value.

        Each facet is counted with its *own* filter removed, so selecting
        'Gujarat' does not reduce the state list to just Gujarat.
        """
        results: dict[str, list[Facet]] = {}

        for name, column in self.FACET_COLUMNS.items():
            narrowed = SearchQuery(
                **{
                    **{
                        f.name: getattr(query, f.name)
                        for f in SearchQuery.__dataclass_fields__.values()
                    },
                    name if name != "bank" else "bank": None,
                }
            )
            stmt = self._apply_filters(
                select(column, func.count()).where(column.is_not(None)), narrowed
            )
            rows = self._session.execute(
                stmt.group_by(column).order_by(func.count().desc()).limit(15)
            )
            values = [Facet(value=value, count=count) for value, count in rows.all()]
            if values:
                results[name] = values

        return results


def _start_of(day: date) -> datetime:
    return datetime.combine(day, datetime.min.time()).astimezone()


def _end_of(day: date) -> datetime:
    return datetime.combine(day, datetime.max.time()).astimezone()
