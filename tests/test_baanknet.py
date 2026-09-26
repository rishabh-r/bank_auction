"""Tests for the BAANKNET adapter, run against real archived pages.

The fixtures in tests/fixtures/baanknet are genuine documents downloaded
from BAANKNET. Running the parser against them on every change is what
stops a fix for one layout silently breaking another.
"""

from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest

from auction_portal.fetching.models import RawDocument
from auction_portal.sources.baanknet import BaanknetAdapter

FIXTURES = Path(__file__).parent / "fixtures" / "baanknet"

SITEMAP = """<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url><loc>https://baanknet.com/property-detail/298977/7fdde6b2</loc></url>
  <url><loc>https://baanknet.com/property-detail/298975/3e2f985e</loc></url>
  <url><loc>https://baanknet.com/property-listing/Gujarat</loc></url>
  <url><loc>https://baanknet.com/vehicle-detail/449/0537b111</loc></url>
</urlset>
"""


def document(fixture_name: str, url: str = "https://baanknet.com/property-detail/1/a"):
    path = FIXTURES / f"{fixture_name}.html"
    if not path.exists():
        pytest.skip(f"fixture missing: {path.name}")
    return RawDocument(
        source_id="baanknet",
        url=url,
        content=path.read_bytes(),
        mime_type="text/html",
        http_status=200,
        fetched_at=datetime(2026, 9, 26, tzinfo=UTC),
    )


def parse_one(fixture_name: str, url: str = "https://baanknet.com/property-detail/1/a"):
    listings = BaanknetAdapter().parse(document(fixture_name, url))
    assert listings, "adapter produced no listing"
    return listings[0]


# --- discovery ------------------------------------------------------------


def test_discover_reads_property_urls_from_the_sitemap():
    adapter = BaanknetAdapter(fetch_text=lambda url: SITEMAP)
    urls = adapter.discover()

    assert len(urls) == 2
    assert all("/property-detail/" in u for u in urls)
    # Listing and vehicle pages are not property detail pages.
    assert not any("property-listing" in u for u in urls)
    assert not any("vehicle-detail" in u for u in urls)


def test_discover_respects_the_limit():
    adapter = BaanknetAdapter(fetch_text=lambda url: SITEMAP)
    assert len(adapter.discover(limit=1)) == 1


def test_discover_survives_one_unreachable_sitemap():
    """A failure on one sitemap must not lose the other."""
    calls = []

    def flaky(url: str) -> str:
        calls.append(url)
        if len(calls) == 1:
            raise RuntimeError("timeout")
        return SITEMAP

    urls = BaanknetAdapter(fetch_text=flaky).discover()
    assert len(urls) == 2


def test_discover_without_a_fetcher_is_an_error():
    with pytest.raises(RuntimeError, match="fetch_text"):
        BaanknetAdapter().discover()


# --- parsing real pages ---------------------------------------------------


def test_parses_the_tiruppur_property():
    listing = parse_one("property_tiruppur_transposed_coords")

    assert listing.source_id == "baanknet"
    assert listing.external_id == "298977"
    assert listing.state == "Tamil Nadu"
    assert listing.city == "Tiruppur"
    assert listing.pincode == "641603"
    assert listing.bank_name == "Bank of Baroda"
    assert listing.reserve_price == Decimal("131850000.00")
    assert listing.emd_amount == Decimal("13185000.00")
    assert listing.possession_type == "symbolic"
    assert listing.asset_key == "BARB896825092026001"


def test_transposed_coordinates_are_corrected():
    """BAANKNET reports Tiruppur as lat 77.58 / lon 11.28; it is the reverse.

    A pin two hundred kilometres out is worse than no pin at all, so this
    is detected and fixed rather than trusted.
    """
    listing = parse_one("property_tiruppur_transposed_coords")

    assert listing.latitude == Decimal("11.280619")
    assert listing.longitude == Decimal("77.582599")
    assert "coordinates_transposed" in listing.quality_flags


def test_emd_is_ten_percent_of_reserve_on_real_data():
    listing = parse_one("property_tiruppur_transposed_coords")
    ratio = listing.emd_amount / listing.reserve_price
    assert ratio == Decimal("0.1")
    assert not any(f.startswith("emd_ratio_unusual") for f in listing.quality_flags)


def test_parses_the_gujarat_agricultural_property():
    listing = parse_one("property_gujarat_agriculture_drt")

    assert listing.external_id == "298715"
    assert listing.state == "Gujarat"
    assert listing.city == "Vani"
    assert listing.district == "Ahmedabad"
    assert listing.locality == "Kointiya"
    assert listing.asset_type == "agricultural"
    assert listing.asset_subtype == "Agriculture Land"


def test_drt_sales_are_distinguished_from_sarfaesi():
    """Different legal track, different risks for a buyer."""
    assert parse_one("property_gujarat_agriculture_drt").legal_basis == "drt"


def test_missing_coordinates_do_not_become_a_pin():
    listing = parse_one("property_gujarat_agriculture_drt")
    assert listing.latitude is None
    assert listing.longitude is None


def test_auction_schedule_is_parsed():
    listing = parse_one("property_gujarat_agriculture_drt")
    assert listing.auction_start_at is not None
    assert listing.auction_start_at.year == 2026
    assert listing.emd_deadline_at is not None


def test_canonical_url_is_recorded():
    url = "https://baanknet.com/property-detail/298715/e6783746"
    assert parse_one("property_gujarat_agriculture_drt", url).canonical_url == url


def test_raw_payload_is_kept_for_provenance():
    listing = parse_one("property_gujarat_agriculture_drt")
    assert "property" in listing.raw_payload
    assert listing.raw_payload["property"]["propertyDetailId"] == 298715


# --- confidence and robustness -------------------------------------------


def test_complete_records_score_highly():
    listing = parse_one("property_tiruppur_transposed_coords")
    assert listing.confidence >= Decimal("0.70")


def test_garbage_input_produces_no_listing_rather_than_a_bad_one():
    doc = RawDocument(
        source_id="baanknet",
        url="https://baanknet.com/property-detail/1/a",
        content=b"<html><body>not a property page</body></html>",
        mime_type="text/html",
        http_status=200,
    )
    assert BaanknetAdapter().parse(doc) == []


def test_empty_document_is_handled():
    doc = RawDocument(
        source_id="baanknet",
        url="https://baanknet.com/property-detail/1/a",
        content=b"",
        mime_type="text/html",
        http_status=200,
    )
    assert BaanknetAdapter().parse(doc) == []
