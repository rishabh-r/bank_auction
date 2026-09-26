"""Tests for storing listings and tracking how they change."""

from datetime import UTC, datetime
from decimal import Decimal

from auction_portal.db.listing_repository import PUBLISH_THRESHOLD, ListingRepository
from auction_portal.db.models import Listing
from auction_portal.sources.base import ParsedListing


def make(**overrides) -> ParsedListing:
    values = {
        "source_id": "baanknet",
        "external_id": "298977",
        "canonical_url": "https://baanknet.com/property-detail/298977/abc",
        "asset_class": "property",
        "asset_type": "residential",
        "city": "Tiruppur",
        "state": "Tamil Nadu",
        "reserve_price": Decimal("131850000.00"),
        "emd_amount": Decimal("13185000.00"),
        "auction_start_at": datetime(2026, 10, 28, 8, 30, tzinfo=UTC),
        "status": "upcoming",
        "bank_name": "Bank of Baroda",
    }
    values.update(overrides)
    return ParsedListing(**values)


def test_first_upsert_creates_the_listing(db_session):
    repo = ListingRepository(db_session)

    listing, action = repo.upsert(make())
    db_session.flush()

    assert action == "created"
    assert listing.city == "Tiruppur"
    assert listing.round_number == 1
    assert repo.count() == 1


def test_identical_data_is_recognised_as_unchanged(db_session):
    repo = ListingRepository(db_session)
    repo.upsert(make())
    db_session.flush()

    _, action = repo.upsert(make())
    db_session.flush()

    assert action == "unchanged"
    assert repo.count() == 1


def test_price_cut_is_recorded_in_history(db_session):
    """The headline feature: 'reserve down 34% since January'."""
    repo = ListingRepository(db_session)
    listing, _ = repo.upsert(make())
    db_session.flush()

    _, action = repo.upsert(make(reserve_price=Decimal("87000000.00")))
    db_session.flush()

    assert action == "updated"
    assert repo.count() == 1  # still one listing, not two

    revisions = repo.revisions_for(listing.id)
    price_changes = [r for r in revisions if r.field_name == "reserve_price"]
    assert len(price_changes) == 1
    assert price_changes[0].old_value == "131850000.00"
    assert price_changes[0].new_value == "87000000.00"


def test_postponement_is_recorded(db_session):
    repo = ListingRepository(db_session)
    listing, _ = repo.upsert(make())
    db_session.flush()

    repo.upsert(make(auction_start_at=datetime(2026, 11, 18, 8, 30, tzinfo=UTC)))
    db_session.flush()

    changed = {r.field_name for r in repo.revisions_for(listing.id)}
    assert "auction_start_at" in changed


def test_untracked_field_changes_do_not_create_history(db_session):
    """Only fields a user would care about are worth a history row."""
    repo = ListingRepository(db_session)
    listing, _ = repo.upsert(make())
    db_session.flush()

    repo.upsert(make(authorised_officer_name="Someone Else"))
    db_session.flush()

    assert repo.revisions_for(listing.id) == []
    assert listing.authorised_officer_name == "Someone Else"  # still updated


def test_low_confidence_listings_are_stored_but_withheld(db_session):
    """Milestone 4 policy: never show a number we are unsure of.

    The listing is kept so it can be published later if the parser
    improves, but it does not reach users in the meantime.
    """
    repo = ListingRepository(db_session)

    listing, _ = repo.upsert(make(external_id="low", confidence=Decimal("0.30")))
    db_session.flush()

    assert listing.is_published is False
    assert repo.count() == 1
    assert repo.count(published_only=True) == 0


def test_confident_listings_are_published(db_session):
    repo = ListingRepository(db_session)
    listing, _ = repo.upsert(make(confidence=PUBLISH_THRESHOLD))
    db_session.flush()

    assert listing.is_published is True
    assert repo.count(published_only=True) == 1


def test_improved_confidence_publishes_a_withheld_listing(db_session):
    """A better parser should rescue previously withheld listings."""
    repo = ListingRepository(db_session)
    repo.upsert(make(confidence=Decimal("0.30"), reserve_price=None))
    db_session.flush()
    assert repo.count(published_only=True) == 0

    repo.upsert(make(confidence=Decimal("1.00")))
    db_session.flush()

    assert repo.count(published_only=True) == 1


def test_different_sources_are_separate_listings(db_session):
    """Deduplication across sources is Milestone 6, not here."""
    repo = ListingRepository(db_session)
    repo.upsert(make(source_id="baanknet"))
    repo.upsert(make(source_id="hdfc_web"))
    db_session.flush()

    assert repo.count() == 2


def test_quality_flags_are_stored(db_session):
    repo = ListingRepository(db_session)
    parsed = make()
    parsed.flag("coordinates_transposed")
    listing, _ = repo.upsert(parsed)
    db_session.flush()

    assert listing.quality_flags == ["coordinates_transposed"]


def test_count_by_groups_listings(db_session):
    repo = ListingRepository(db_session)
    repo.upsert(make(external_id="1", state="Tamil Nadu"))
    repo.upsert(make(external_id="2", state="Gujarat"))
    repo.upsert(make(external_id="3", state="Gujarat"))
    db_session.flush()

    assert repo.count_by(Listing.state) == {"Gujarat": 2, "Tamil Nadu": 1}
