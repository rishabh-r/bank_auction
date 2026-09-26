"""Tests for the BAANKNET vehicle adapter, against a real archived page."""

from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest

from auction_portal.fetching.models import RawDocument
from auction_portal.sources.baanknet_vehicle import BaanknetVehicleAdapter
from auction_portal.sources.base import PERSONAL_FIELDS

FIXTURES = Path(__file__).parent / "fixtures" / "baanknet"
FIXTURE = "vehicle_bengaluru_hypothecation"

SITEMAP = """<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url><loc>https://baanknet.com/vehicle-detail/449/0537b111</loc></url>
  <url><loc>https://baanknet.com/vehicle-detail/440/b8d3e856</loc></url>
  <url><loc>https://baanknet.com/property-detail/298977/7fdde6b2</loc></url>
</urlset>
"""


def parse_one(url: str = "https://baanknet.com/vehicle-detail/449/x"):
    path = FIXTURES / f"{FIXTURE}.html"
    if not path.exists():
        pytest.skip(f"fixture missing: {path.name}")
    document = RawDocument(
        source_id="baanknet_vehicle",
        url=url,
        content=path.read_bytes(),
        mime_type="text/html",
        http_status=200,
        fetched_at=datetime(2026, 9, 26, tzinfo=UTC),
    )
    listings = BaanknetVehicleAdapter().parse(document)
    assert listings, "adapter produced no listing"
    return listings[0]


# --- discovery ------------------------------------------------------------


def test_discover_finds_only_vehicle_urls():
    urls = BaanknetVehicleAdapter(fetch_text=lambda url: SITEMAP).discover()
    assert len(urls) == 2
    assert all("/vehicle-detail/" in u for u in urls)
    assert not any("property-detail" in u for u in urls)


# --- parsing --------------------------------------------------------------


def test_parses_a_real_vehicle():
    listing = parse_one()

    assert listing.asset_class == "vehicle"
    assert listing.external_id == "449"
    assert listing.bank_name == "State Bank of India"
    assert listing.city == "Bengaluru"
    assert listing.state == "Karnataka"
    assert listing.pincode == "560016"


def test_reserve_price_falls_back_to_the_listed_price():
    """Vehicles are often listed before an auction is scheduled, so there
    is a price but no reservePrice field yet."""
    assert parse_one().reserve_price == Decimal("400000.00")


def test_emd_is_derived_from_the_percentage_when_no_amount_is_given():
    listing = parse_one()
    assert listing.emd_amount == Decimal("40000.00")  # 10% of 4,00,000
    assert "emd_derived_from_percentage" in listing.quality_flags


def test_hypothecation_is_recorded_as_a_contractual_sale():
    """Cars are repossessed under the loan contract, not SARFAESI. The
    legal process and the buyer's risks are different."""
    assert parse_one().legal_basis == "contractual"


def test_possession_type_is_read():
    assert parse_one().possession_type == "physical"


def test_location_is_where_the_vehicle_is_not_where_its_owner_lives():
    """parkingYardAddress is the useful, non-personal address."""
    listing = parse_one()
    assert listing.address is not None
    assert "KALKERE" in listing.address.upper()


def test_owner_address_is_never_stored():
    """The borrower's home address must not enter the database at all."""
    listing = parse_one()
    stored = str(listing.raw_payload).lower()

    assert "yoganarasimha" not in stored  # from the real ownerAddress
    assert listing.address is None or "yoganarasimha" not in listing.address.lower()


def test_all_personal_fields_are_stripped_from_the_payload():
    payload = parse_one().raw_payload["vehicle"]
    assert not (set(payload) & PERSONAL_FIELDS)


def test_unscheduled_vehicle_auctions_are_marked_as_such():
    listing = parse_one()
    assert listing.status == "unscheduled"
    assert "auction_not_yet_scheduled" in listing.quality_flags


def test_title_describes_the_vehicle():
    title = parse_one().title
    assert title and title != "Vehicle"


def test_garbage_input_produces_no_listing():
    document = RawDocument(
        source_id="baanknet_vehicle",
        url="https://baanknet.com/vehicle-detail/1/a",
        content=b"<html><body>nothing here</body></html>",
        mime_type="text/html",
        http_status=200,
    )
    assert BaanknetVehicleAdapter().parse(document) == []
