"""Tests for search, filtering and pagination."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from auction_portal.db.listing_repository import ListingRepository
from auction_portal.search import SearchQuery, SearchService
from auction_portal.sources.base import ParsedListing

NOW = datetime.now(UTC)


def make(external_id: str, **overrides) -> ParsedListing:
    values = {
        "source_id": "baanknet",
        "external_id": external_id,
        "canonical_url": f"https://baanknet.com/property-detail/{external_id}/x",
        "asset_class": "property",
        "asset_type": "residential",
        "title": "Flat at Andheri",
        "city": "Mumbai",
        "state": "Maharashtra",
        "bank_name": "State Bank of India",
        "possession_type": "physical",
        "reserve_price": Decimal("5000000.00"),
        "emd_amount": Decimal("500000.00"),
        "auction_start_at": NOW + timedelta(days=10),
        "status": "upcoming",
    }
    values.update(overrides)
    return ParsedListing(**values)


@pytest.fixture
def seeded(db_session):
    """A small, deliberately varied corpus."""
    repo = ListingRepository(db_session)
    repo.upsert(make("1"))
    repo.upsert(
        make(
            "2",
            title="Shop at Bandra",
            asset_type="commercial",
            reserve_price=Decimal("12000000.00"),
            auction_start_at=NOW + timedelta(days=3),
        )
    )
    repo.upsert(
        make(
            "3",
            title="Plot at Vani",
            city="Vani",
            state="Gujarat",
            asset_type="agricultural",
            bank_name="Bank of Baroda",
            possession_type="symbolic",
            reserve_price=Decimal("900000.00"),
            auction_start_at=NOW + timedelta(days=30),
        )
    )
    repo.upsert(make("4", title="Withheld property", confidence=Decimal("0.20")))
    db_session.commit()
    return SearchService(db_session)


def test_unfiltered_search_excludes_withheld_listings(seeded):
    """The withheld one must never reach a user by default."""
    results = seeded.search(SearchQuery())
    assert results.total == 3
    assert all(listing.is_published for listing in results.listings)


def test_filter_by_state(seeded):
    results = seeded.search(SearchQuery(state="Gujarat"))
    assert results.total == 1
    assert results.listings[0].city == "Vani"


def test_filter_by_city(seeded):
    assert seeded.search(SearchQuery(city="Mumbai")).total == 2


def test_filter_by_asset_type(seeded):
    assert seeded.search(SearchQuery(asset_type="commercial")).total == 1


def test_filter_by_bank(seeded):
    assert seeded.search(SearchQuery(bank="Bank of Baroda")).total == 1


def test_filter_by_possession(seeded):
    """Physical versus symbolic changes what a buyer is taking on."""
    assert seeded.search(SearchQuery(possession="symbolic")).total == 1
    assert seeded.search(SearchQuery(possession="physical")).total == 2


def test_filters_combine(seeded):
    query = SearchQuery(state="Maharashtra", asset_type="residential")
    assert seeded.search(query).total == 1


def test_price_range_filter(seeded):
    assert seeded.search(SearchQuery(min_price=Decimal("1000000"))).total == 2
    assert seeded.search(SearchQuery(max_price=Decimal("1000000"))).total == 1
    assert (
        seeded.search(SearchQuery(min_price=Decimal("1000000"), max_price=Decimal("6000000"))).total
        == 1
    )


def test_full_text_search_matches_city(seeded):
    assert seeded.search(SearchQuery(text="Vani")).total == 1


def test_full_text_search_matches_bank(seeded):
    assert seeded.search(SearchQuery(text="Baroda")).total == 1


def test_search_for_nothing_returns_nothing(seeded):
    assert seeded.search(SearchQuery(text="Antarctica")).total == 0


def test_sort_by_price_ascending(seeded):
    listings = seeded.search(SearchQuery(sort="price_low")).listings
    prices = [listing.reserve_price for listing in listings]
    assert prices == sorted(prices)


def test_sort_by_price_descending(seeded):
    listings = seeded.search(SearchQuery(sort="price_high")).listings
    prices = [listing.reserve_price for listing in listings]
    assert prices == sorted(prices, reverse=True)


def test_default_sort_is_soonest_auction_first(seeded):
    listings = seeded.search(SearchQuery()).listings
    dates = [listing.auction_start_at for listing in listings]
    assert dates == sorted(dates)


def test_finished_auctions_sort_below_upcoming_ones(db_session):
    """Ascending on the raw date puts last month's finished auctions at
    the top, which is useless to someone looking to buy."""
    repo = ListingRepository(db_session)
    repo.upsert(make("past", auction_start_at=NOW - timedelta(days=5)))
    repo.upsert(make("soon", auction_start_at=NOW + timedelta(days=2)))
    repo.upsert(make("later", auction_start_at=NOW + timedelta(days=40)))
    db_session.commit()

    listings = SearchService(db_session).search(SearchQuery()).listings
    order = [listing.external_id for listing in listings]

    assert order == ["soon", "later", "past"]


def test_finished_auctions_sort_last_even_if_the_job_has_not_run(db_session):
    """Ordering is driven by the date, not the stored status, so a
    stalled maintenance job does not push stale listings to the top."""
    repo = ListingRepository(db_session)
    repo.upsert(make("stale", auction_start_at=NOW - timedelta(days=5), status="upcoming"))
    repo.upsert(make("real", auction_start_at=NOW + timedelta(days=2)))
    db_session.commit()

    listings = SearchService(db_session).search(SearchQuery()).listings
    assert [listing.external_id for listing in listings] == ["real", "stale"]


def test_pagination_splits_results(seeded):
    first = seeded.search(SearchQuery(page=1, page_size=2))
    second = seeded.search(SearchQuery(page=2, page_size=2))

    assert first.total == 3
    assert len(first.listings) == 2
    assert len(second.listings) == 1
    assert first.total_pages == 2
    assert first.has_next and not first.has_previous
    assert second.has_previous and not second.has_next


def test_pagination_indices_are_human_readable(seeded):
    page = seeded.search(SearchQuery(page=2, page_size=2))
    assert (page.first_index, page.last_index) == (3, 3)


def test_page_size_is_capped():
    """A caller cannot ask for the whole table in one request."""
    assert SearchQuery(page_size=100_000).page_size == 100


def test_page_number_cannot_be_zero_or_negative():
    assert SearchQuery(page=0).page == 1
    assert SearchQuery(page=-5).page == 1


def test_facets_count_available_values(seeded):
    facets = seeded.search(SearchQuery()).facets
    states = {facet.value: facet.count for facet in facets["state"]}
    assert states == {"Maharashtra": 2, "Gujarat": 1}


def test_facet_counts_ignore_their_own_filter(seeded):
    """Choosing Gujarat must not collapse the state list to only Gujarat.

    Otherwise a user cannot switch to a different state without clearing
    the filter first.
    """
    facets = seeded.search(SearchQuery(state="Gujarat")).facets
    states = {facet.value for facet in facets["state"]}
    assert states == {"Maharashtra", "Gujarat"}


def test_facet_counts_do_respect_other_filters(seeded):
    facets = seeded.search(SearchQuery(city="Mumbai")).facets
    types = {facet.value for facet in facets["asset_type"]}
    assert types == {"residential", "commercial"}  # no agricultural in Mumbai


def test_get_returns_a_published_listing(seeded):
    listing = seeded.search(SearchQuery(state="Gujarat")).listings[0]
    assert seeded.get(listing.id) is not None


def test_get_hides_a_withheld_listing(seeded, db_session):
    withheld = ListingRepository(db_session).get("baanknet", "4")
    assert withheld.is_published is False
    assert seeded.get(withheld.id) is None
    assert seeded.get(withheld.id, include_unpublished=True) is not None


def test_get_unknown_id_returns_none(seeded):
    assert seeded.get(999_999) is None


def test_nearby_finds_listings_in_the_same_city(seeded):
    listing = seeded.search(SearchQuery(asset_type="commercial")).listings[0]
    nearby = seeded.nearby(listing)
    assert len(nearby) == 1
    assert nearby[0].city == "Mumbai"
    assert nearby[0].id != listing.id


def test_totals_summarise_the_corpus(seeded):
    totals = seeded.totals()
    assert totals == {"listings": 3, "states": 2, "banks": 2}


def test_active_filters_are_reportable():
    query = SearchQuery(state="Gujarat", city="Vani", text="plot")
    assert query.active_filters() == {
        "q": "plot",
        "state": "Gujarat",
        "city": "Vani",
    }
