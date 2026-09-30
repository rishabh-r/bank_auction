"""Database tables.

Only two tables in this milestone, both about *provenance* rather than
auction content. Parsed listings arrive in Milestone 4.

  source_documents  every document we have ever downloaded
  url_state         what we knew about each URL at its last fetch

The design rule that shapes both: rows here are append-mostly. We record
what happened, we do not overwrite history.
"""

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    Boolean,
    Computed,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, TSVECTOR
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


#: Outcomes that the passage of time cannot change. A cancelled auction
#: does not become 'live' because its start time arrived.
_TERMINAL_STATUSES = frozenset({"cancelled", "withdrawn", "stayed", "sold", "unknown"})


class SourceDocument(Base):
    """One archived download. Immutable once written.

    A new version of the same URL creates a new row rather than updating the
    old one, so a corrigendum never destroys the notice it corrects.
    """

    __tablename__ = "source_documents"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)

    source_id: Mapped[str] = mapped_column(String(64), nullable=False)
    source_url: Mapped[str] = mapped_column(Text, nullable=False)

    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    content_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    storage_key: Mapped[str] = mapped_column(Text, nullable=False)

    mime_type: Mapped[str | None] = mapped_column(String(128))
    http_status: Mapped[int | None] = mapped_column(Integer)
    size_bytes: Mapped[int | None] = mapped_column(BigInteger)
    etag: Mapped[str | None] = mapped_column(String(256))
    last_modified: Mapped[str | None] = mapped_column(String(128))

    # Set when the same bytes are seen again at a later date.
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        # The core change-detection guarantee: identical bytes at the same URL
        # can only ever be recorded once. Enforced by the database, so even a
        # buggy worker or a duplicated task cannot create a second row.
        UniqueConstraint("source_url", "content_sha256", name="uq_source_doc_url_hash"),
        Index("ix_source_doc_source_fetched", "source_id", "fetched_at"),
        Index("ix_source_doc_sha256", "content_sha256"),
    )

    def __repr__(self) -> str:
        return (
            f"<SourceDocument id={self.id} source={self.source_id!r} "
            f"sha256={self.content_sha256[:12]}...>"
        )


class UrlStateRow(Base):
    """What we knew about a URL at its last fetch.

    Powers conditional GET (send the stored ETag) and change detection
    (compare the stored hash). Replaces the JSON file used in Milestone 2.
    """

    __tablename__ = "url_state"

    url: Mapped[str] = mapped_column(Text, primary_key=True)
    source_id: Mapped[str] = mapped_column(String(64), nullable=False)

    content_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    # Hash with per-request noise removed. Compared instead of
    # content_sha256 when deciding whether a page really changed, so a
    # visitor counter ticking over does not archive a fresh copy.
    canonical_sha256: Mapped[str | None] = mapped_column(String(64))
    storage_key: Mapped[str] = mapped_column(Text, nullable=False)

    etag: Mapped[str | None] = mapped_column(String(256))
    last_modified: Mapped[str | None] = mapped_column(String(128))

    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_changed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    fetch_count: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    # Consecutive fetches where the content was identical. A high number means
    # a stable page; a reset to zero means something was republished.
    unchanged_streak: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    current_document_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("source_documents.id", ondelete="SET NULL")
    )
    current_document: Mapped[SourceDocument | None] = relationship(lazy="joined")

    __table_args__ = (Index("ix_url_state_source", "source_id"),)

    def __repr__(self) -> str:
        return f"<UrlStateRow url={self.url!r} fetches={self.fetch_count}>"


class Listing(Base):
    """One asset offered at auction: the user-facing record.

    Identified by (source_id, external_id) rather than a URL, so the same
    asset stays one row even if the source changes its URL scheme. When a
    property is re-auctioned later, that is a *new* row with an incremented
    round_number, linked by asset_key - not an update, because the price
    history is the most valuable thing we accumulate.
    """

    __tablename__ = "listings"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)

    source_id: Mapped[str] = mapped_column(String(64), nullable=False)
    external_id: Mapped[str] = mapped_column(String(128), nullable=False)
    # Stable identity of the underlying asset across re-auctions.
    asset_key: Mapped[str | None] = mapped_column(String(128), index=True)
    round_number: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    source_document_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("source_documents.id", ondelete="SET NULL")
    )
    canonical_url: Mapped[str] = mapped_column(Text, nullable=False)

    # --- what it is ---
    asset_class: Mapped[str] = mapped_column(String(32), nullable=False)  # property|vehicle
    asset_type: Mapped[str | None] = mapped_column(String(64))  # residential|commercial|...
    asset_subtype: Mapped[str | None] = mapped_column(String(128))
    title: Mapped[str | None] = mapped_column(Text)
    description: Mapped[str | None] = mapped_column(Text)

    # --- where it is ---
    address: Mapped[str | None] = mapped_column(Text)
    locality: Mapped[str | None] = mapped_column(Text)
    city: Mapped[str | None] = mapped_column(String(128), index=True)
    district: Mapped[str | None] = mapped_column(String(128))
    state: Mapped[str | None] = mapped_column(String(128), index=True)
    pincode: Mapped[str | None] = mapped_column(String(10), index=True)
    latitude: Mapped[Decimal | None] = mapped_column(Numeric(9, 6))
    longitude: Mapped[Decimal | None] = mapped_column(Numeric(9, 6))

    # --- how big ---
    # Original value and unit are kept for display; the normalised square
    # feet exists so that a range filter can work across mixed units.
    area_value: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    area_unit: Mapped[str | None] = mapped_column(String(24))
    area_sqft: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), index=True)

    # --- the money ---
    reserve_price: Mapped[Decimal | None] = mapped_column(Numeric(18, 2), index=True)
    emd_amount: Mapped[Decimal | None] = mapped_column(Numeric(18, 2))
    bid_increment: Mapped[Decimal | None] = mapped_column(Numeric(18, 2))
    outstanding_dues: Mapped[Decimal | None] = mapped_column(Numeric(18, 2))

    # --- the timetable ---
    auction_start_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    auction_end_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    emd_deadline_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    inspection_from: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    inspection_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # --- the legal position ---
    bank_name: Mapped[str | None] = mapped_column(String(160), index=True)
    branch_name: Mapped[str | None] = mapped_column(String(200))
    possession_type: Mapped[str | None] = mapped_column(String(16))  # physical|symbolic
    symbolic_possession_date: Mapped[date | None] = mapped_column(Date)
    physical_possession_date: Mapped[date | None] = mapped_column(Date)
    npa_date: Mapped[date | None] = mapped_column(Date)
    legal_basis: Mapped[str | None] = mapped_column(String(32))

    authorised_officer_name: Mapped[str | None] = mapped_column(String(200))
    authorised_officer_phone: Mapped[str | None] = mapped_column(String(64))

    status: Mapped[str] = mapped_column(String(24), nullable=False, default="upcoming")

    # --- provenance and quality ---
    confidence: Mapped[Decimal] = mapped_column(
        Numeric(3, 2), nullable=False, default=Decimal("1.00")
    )
    quality_flags: Mapped[list[str] | None] = mapped_column(JSONB)
    is_published: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    raw_payload: Mapped[dict | None] = mapped_column(JSONB)

    # Maintained by PostgreSQL on every insert and update, so there is no
    # sync code that can drift. Weights rank a title match above a match
    # buried in the address.
    search_vector: Mapped[str | None] = mapped_column(
        TSVECTOR,
        Computed(
            "setweight(to_tsvector('simple', coalesce(title, '')), 'A') || "
            "setweight(to_tsvector('simple', coalesce(city, '')), 'B') || "
            "setweight(to_tsvector('simple', coalesce(locality, '')), 'B') || "
            "setweight(to_tsvector('simple', coalesce(state, '')), 'B') || "
            "setweight(to_tsvector('simple', coalesce(bank_name, '')), 'C') || "
            "setweight(to_tsvector('simple', coalesce(address, '')), 'D')",
            persisted=True,
        ),
    )

    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    first_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    last_verified_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        UniqueConstraint("source_id", "external_id", name="uq_listing_source_external"),
        # Most queries want live auctions only, and those are a small slice of
        # the table once history accumulates. A partial index stays small.
        Index(
            "ix_listing_live",
            "status",
            "auction_start_at",
            postgresql_where=(status.in_(("upcoming", "live"))),
        ),
        Index("ix_listing_geo", "state", "city", "asset_type"),
        Index("ix_listing_bank", "bank_name"),
        Index("ix_listing_search", "search_vector", postgresql_using="gin"),
    )

    @property
    def effective_status(self) -> str:
        """Status worked out from the clock, not from when a job last ran.

        The stored `status` column exists so that status can be indexed
        and filtered cheaply, and a scheduled job keeps it current. But
        it is only ever as fresh as the last time that job ran, and a
        portal that calls an auction 'upcoming' two days after it
        finished loses a reader's trust immediately.

        So anything shown to a reader uses this instead. The column stays
        for querying; this is the truth for display.

        States that a date cannot contradict - cancelled, withdrawn,
        stayed, sold - are returned unchanged.
        """
        if self.status in _TERMINAL_STATUSES or self.auction_start_at is None:
            return self.status

        now = datetime.now(UTC)
        if now < self.auction_start_at:
            return "upcoming"
        if self.auction_end_at is not None:
            return "live" if now <= self.auction_end_at else "closed"
        # Started, with no end time published. Assume a single day rather
        # than leaving it 'live' indefinitely.
        return "live" if now < self.auction_start_at + timedelta(days=1) else "closed"

    @property
    def status_is_stale(self) -> bool:
        """True when the stored status disagrees with the clock.

        Surfaced in the health check: a rising count means the
        maintenance job has stopped running.
        """
        return self.status != self.effective_status

    def __repr__(self) -> str:
        return (
            f"<Listing {self.source_id}/{self.external_id} "
            f"{self.city} reserve={self.reserve_price}>"
        )


class SourceHealth(Base):
    """One row per crawl run, per source.

    Scrapers fail silently: a changed selector returns zero results rather
    than an error. Recording the outcome of every run is what turns that
    into something we can alert on.
    """

    __tablename__ = "source_health"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    source_id: Mapped[str] = mapped_column(String(64), nullable=False)
    ran_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    duration_seconds: Mapped[float | None] = mapped_column(Numeric(10, 2))

    discovered: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    fetched: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    unchanged: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    failed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    parse_failures: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    listings_created: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    listings_updated: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # Created + updated + unchanged. This, not listings_created, is the
    # health signal: once a source is established most runs legitimately
    # create nothing, but a run that yields no listings at all means the
    # parser has stopped working.
    listings_seen: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    ok: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    notes: Mapped[str | None] = mapped_column(Text)

    __table_args__ = (Index("ix_source_health_source_time", "source_id", "ran_at"),)

    def __repr__(self) -> str:
        return f"<SourceHealth {self.source_id} at {self.ran_at} ok={self.ok}>"


class ListingRevision(Base):
    """Field-level history. Every price cut and postponement, permanently.

    This is what lets the portal say "third attempt, reserve down 34% since
    January" - which no competitor surfaces.
    """

    __tablename__ = "listing_revisions"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    listing_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("listings.id", ondelete="CASCADE"), nullable=False
    )
    changed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    field_name: Mapped[str] = mapped_column(String(64), nullable=False)
    old_value: Mapped[str | None] = mapped_column(Text)
    new_value: Mapped[str | None] = mapped_column(Text)
    source_document_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("source_documents.id", ondelete="SET NULL")
    )

    __table_args__ = (Index("ix_revision_listing", "listing_id", "changed_at"),)

    def __repr__(self) -> str:
        return f"<ListingRevision {self.field_name}: {self.old_value} -> {self.new_value}>"
