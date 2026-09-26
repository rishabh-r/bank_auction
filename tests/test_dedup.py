"""Tests for deduplication and re-auction detection."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from auction_portal.db.listing_repository import ListingRepository
from auction_portal.db.models import Listing
from auction_portal.dedup import (
    DuplicateFinder,
    blocking_keys,
    classify,
    normalise_address,
    price_change,
    similarity,
    token_similarity,
)
from auction_portal.sources.base import ParsedListing

BASE = datetime(2026, 3, 1, 10, 0, tzinfo=UTC)


def listing(**overrides) -> Listing:
    values = {
        "id": 1,
        "source_id": "baanknet",
        "external_id": "1",
        "canonical_url": "https://x.test/1",
        "asset_class": "property",
        "address": "Flat 302, Sunrise Apartments, Andheri West, Mumbai",
        "locality": "Andheri West",
        "city": "Mumbai",
        "state": "Maharashtra",
        "pincode": "400053",
        "reserve_price": Decimal("5000000.00"),
        "emd_amount": Decimal("500000.00"),
        "area_sqft": Decimal("850.00"),
        "auction_start_at": BASE,
        "status": "upcoming",
        "content_hash": "x",
    }
    values.update(overrides)
    return Listing(**values)


# --- address normalisation ------------------------------------------------


def test_address_normalisation_strips_noise_words():
    normalised = normalise_address("Flat No. 302, Sunrise Apartments, Andheri Road")
    assert "flat" not in normalised
    assert "road" not in normalised
    assert "sunrise" in normalised


def test_same_address_written_differently_normalises_alike():
    a = normalise_address("Flat 302, Sunrise Apartments, Andheri West")
    b = normalise_address("Sunrise Apartments Flat No. 302, Andheri (W)")
    assert token_similarity(a, b) > 0.6


def test_unrelated_addresses_do_not_match():
    a = normalise_address("Sunrise Apartments, Andheri")
    b = normalise_address("Greenfield Warehouse, Kolkata")
    assert token_similarity(a, b) < 0.2


# --- blocking -------------------------------------------------------------


def test_blocking_keys_are_generated():
    keys = blocking_keys(listing())
    assert any(k.startswith("geo:") for k in keys)
    assert any(k.startswith("pin:") for k in keys)


def test_identical_listings_share_a_blocking_key():
    assert blocking_keys(listing()) & blocking_keys(listing(id=2))


def test_unrelated_listings_share_no_blocking_key():
    other = listing(
        id=2,
        city="Kolkata",
        state="West Bengal",
        pincode="700001",
        address="Greenfield Warehouse, Salt Lake",
        reserve_price=Decimal("90000000.00"),
    )
    assert not (blocking_keys(listing()) & blocking_keys(other))


def test_asset_key_is_a_blocking_key():
    """The strongest signal when the source provides a stable identifier."""
    keys = blocking_keys(listing(asset_key="BARB896825092026001"))
    assert "asset:BARB896825092026001" in keys


# --- similarity -----------------------------------------------------------


def test_identical_listings_score_almost_one():
    score, _ = similarity(listing(), listing(id=2))
    assert score > 0.95


def test_identical_reserve_price_is_called_out():
    """An exact match on an odd number like 50,00,000 is strong evidence."""
    _, reasons = similarity(listing(), listing(id=2))
    assert any("identical reserve price" in r for r in reasons)


def test_different_properties_score_low():
    other = listing(
        id=2,
        address="Greenfield Warehouse, Salt Lake, Kolkata",
        locality="Salt Lake",
        reserve_price=Decimal("90000000.00"),
        emd_amount=Decimal("9000000.00"),
        area_sqft=Decimal("25000.00"),
        auction_start_at=BASE + timedelta(days=200),
    )
    score, _ = similarity(listing(), other)
    assert score < 0.5


# --- classification -------------------------------------------------------


def test_same_listing_from_two_sources_is_a_duplicate():
    a = listing()
    b = listing(id=2, source_id="hdfc_web", address="Flat No 302 Sunrise Apartments Andheri W")
    assert classify(a, b).relationship == "duplicate"


def test_later_cheaper_auction_is_a_reauction_not_a_duplicate():
    """The most valuable signal the portal can surface, and the easiest
    thing to get wrong by merging it away."""
    first = listing()
    second = listing(
        id=2,
        auction_start_at=BASE + timedelta(days=90),
        reserve_price=Decimal("3300000.00"),
        emd_amount=Decimal("330000.00"),
    )
    verdict = classify(first, second)

    assert verdict.relationship == "reauction"
    assert any("34% below" in reason for reason in verdict.reasons)


def test_reauction_at_the_same_price_is_still_a_reauction():
    second = listing(id=2, auction_start_at=BASE + timedelta(days=60))
    assert classify(listing(), second).relationship == "reauction"


def test_same_property_same_week_is_a_duplicate_not_a_reauction():
    second = listing(id=2, source_id="other", auction_start_at=BASE + timedelta(days=2))
    assert classify(listing(), second).relationship == "duplicate"


def test_unrelated_listings_are_distinct():
    other = listing(
        id=2,
        city="Kolkata",
        address="Greenfield Warehouse, Salt Lake",
        locality="Salt Lake",
        reserve_price=Decimal("90000000.00"),
        emd_amount=Decimal("9000000.00"),
        area_sqft=Decimal("25000.00"),
    )
    assert classify(listing(), other).relationship == "distinct"


def test_middling_scores_go_to_review_not_auto_merge():
    """A wrong merge destroys two listings and is hard to spot, so the
    uncertain band is reported rather than acted on."""
    other = listing(
        id=2,
        address="Flat 305, Sunrise Apartments, Andheri West, Mumbai",
        reserve_price=Decimal("5600000.00"),
        emd_amount=Decimal("560000.00"),
        area_sqft=Decimal("910.00"),
    )
    assert classify(listing(), other).relationship in {"review", "duplicate"}


def test_price_change_reports_a_cut_as_negative():
    assert price_change(Decimal("5000000"), Decimal("3300000")) == Decimal("-0.3400")
    assert price_change(Decimal("5000000"), Decimal("5500000")) == Decimal("0.1000")
    assert price_change(None, Decimal("100")) is None


# --- against the database -------------------------------------------------


def parsed(external_id: str, **overrides) -> ParsedListing:
    values = {
        "source_id": "baanknet",
        "external_id": external_id,
        "canonical_url": f"https://x.test/{external_id}",
        "asset_class": "property",
        "address": "Flat 302, Sunrise Apartments, Andheri West, Mumbai",
        "locality": "Andheri West",
        "city": "Mumbai",
        "state": "Maharashtra",
        "pincode": "400053",
        "reserve_price": Decimal("5000000.00"),
        "emd_amount": Decimal("500000.00"),
        "area_sqft": Decimal("850.00"),
        "auction_start_at": BASE,
        "status": "upcoming",
    }
    values.update(overrides)
    return ParsedListing(**values)


def test_finder_spots_a_duplicate_in_the_database(db_session):
    repo = ListingRepository(db_session)
    repo.upsert(parsed("1"))
    repo.upsert(parsed("2", source_id="hdfc_web"))
    db_session.flush()

    tally = DuplicateFinder(db_session).scan()
    assert tally["duplicate"] == 1


def test_finder_spots_a_reauction_in_the_database(db_session):
    repo = ListingRepository(db_session)
    repo.upsert(parsed("1"))
    repo.upsert(
        parsed(
            "2",
            auction_start_at=BASE + timedelta(days=120),
            reserve_price=Decimal("3300000.00"),
            emd_amount=Decimal("330000.00"),
        )
    )
    db_session.flush()

    tally = DuplicateFinder(db_session).scan()
    assert tally["reauction"] == 1
    assert tally["duplicate"] == 0


def test_finder_ignores_unrelated_listings(db_session):
    repo = ListingRepository(db_session)
    repo.upsert(parsed("1"))
    repo.upsert(
        parsed(
            "2",
            city="Kolkata",
            state="West Bengal",
            pincode="700001",
            address="Greenfield Warehouse, Salt Lake",
            locality="Salt Lake",
            reserve_price=Decimal("90000000.00"),
            emd_amount=Decimal("9000000.00"),
            area_sqft=Decimal("25000.00"),
        )
    )
    db_session.flush()

    tally = DuplicateFinder(db_session).scan()
    assert tally["compared"] == 0


def test_a_vehicle_never_matches_a_property(db_session):
    repo = ListingRepository(db_session)
    repo.upsert(parsed("1"))
    repo.upsert(parsed("2", source_id="baanknet_vehicle", asset_class="vehicle"))
    db_session.flush()

    assert DuplicateFinder(db_session).scan()["compared"] == 0
