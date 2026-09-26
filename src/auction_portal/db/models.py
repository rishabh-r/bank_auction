"""Database tables.

Only two tables in this milestone, both about *provenance* rather than
auction content. Parsed listings arrive in Milestone 4.

  source_documents  every document we have ever downloaded
  url_state         what we knew about each URL at its last fetch

The design rule that shapes both: rows here are append-mostly. We record
what happened, we do not overwrite history.
"""

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


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
