"""Tests for the web portal: pages, API and the guarantees we promise users."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from auction_portal.db.listing_repository import ListingRepository
from auction_portal.sources.base import ParsedListing
from auction_portal.web.app import create_app, get_session

NOW = datetime.now(UTC)


def make(external_id: str, **overrides) -> ParsedListing:
    values = {
        "source_id": "baanknet",
        "external_id": external_id,
        "canonical_url": f"https://baanknet.com/property-detail/{external_id}/x",
        "asset_class": "property",
        "asset_type": "residential",
        "title": "Flat at Andheri",
        "address": "Plot 12, Andheri East",
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
def client(db_session_factory):
    session = db_session_factory()
    repo = ListingRepository(session)
    repo.upsert(make("1"))
    repo.upsert(
        make(
            "2",
            title="Plot at Vani",
            city="Vani",
            state="Gujarat",
            asset_type="agricultural",
            bank_name="Bank of Baroda",
            possession_type="symbolic",
            legal_basis="drt",
            reserve_price=Decimal("900000.00"),
        )
    )
    repo.upsert(make("3", title="Withheld one", confidence=Decimal("0.20")))
    session.commit()

    app = create_app()
    app.dependency_overrides[get_session] = lambda: session
    with TestClient(app) as test_client:
        yield test_client
    session.close()


def listing_id(client, external: str) -> int:
    """Resolve a database id through the API, as a user would."""
    for item in client.get("/api/listings", params={"page_size": 100}).json()["listings"]:
        if item["source"]["notice_url"].endswith(f"/{external}/x"):
            return item["id"]
    raise AssertionError(f"listing {external} not found")


# --- pages ----------------------------------------------------------------


def test_home_page_renders(client):
    response = client.get("/")
    assert response.status_code == 200
    assert "Flat at Andheri" in response.text
    assert "Plot at Vani" in response.text


def test_home_page_hides_withheld_listings(client):
    """A listing we are not confident about must not reach a user."""
    assert "Withheld one" not in client.get("/").text


def test_search_box_filters_results(client):
    response = client.get("/", params={"q": "Vani"})
    assert "Plot at Vani" in response.text
    assert "Flat at Andheri" not in response.text


def test_state_filter_works(client):
    response = client.get("/", params={"state": "Gujarat"})
    assert "Plot at Vani" in response.text
    assert "Flat at Andheri" not in response.text


def test_price_filter_works(client):
    response = client.get("/", params={"max_price": "1000000"})
    assert "Plot at Vani" in response.text
    assert "Flat at Andheri" not in response.text


def test_no_matches_shows_a_helpful_message(client):
    response = client.get("/", params={"q": "Antarctica"})
    assert response.status_code == 200
    assert "Nothing matches those filters" in response.text


def test_prices_are_shown_in_indian_convention(client):
    """Rs 50.00 L, not 5000000."""
    assert "Rs 50.00 L" in client.get("/").text


def test_detail_page_renders(client):
    response = client.get(f"/listing/{listing_id(client, '1')}")
    assert response.status_code == 200
    assert "Flat at Andheri" in response.text
    assert "State Bank of India" in response.text


def test_detail_page_links_to_the_original_notice(client):
    """Every listing must be traceable to the bank's own publication."""
    response = client.get(f"/listing/{listing_id(client, '1')}")
    assert "https://baanknet.com/property-detail/1/x" in response.text
    assert "View the original notice" in response.text


def test_detail_page_warns_about_symbolic_possession(client):
    """The buyer may inherit an eviction; that has to be said plainly."""
    response = client.get(f"/listing/{listing_id(client, '2')}")
    assert "Symbolic possession" in response.text
    assert "Occupants may still be living there" in response.text


def test_detail_page_warns_about_non_sarfaesi_sales(client):
    assert "DRT sale" in client.get(f"/listing/{listing_id(client, '2')}").text


def test_physical_possession_gets_no_warning(client):
    response = client.get(f"/listing/{listing_id(client, '1')}")
    assert "Occupants may still be living there" not in response.text


def test_withheld_listing_is_not_reachable_by_url(client):
    """Guessing an id must not expose a listing we chose not to publish."""
    response = client.get("/listing/999999")
    assert response.status_code == 404
    assert "Listing not found" in response.text


def test_disclaimer_appears_on_every_page(client):
    for path in ("/", f"/listing/{listing_id(client, '1')}"):
        assert "may be inaccurate or out of date" in client.get(path).text


def test_pages_state_we_are_not_a_bank(client):
    text = client.get("/").text
    assert "Not affiliated with any bank" in text
    assert "do not conduct auctions" in text


# --- personal data --------------------------------------------------------


def test_borrower_names_are_never_published(client):
    """Publishing someone's default is a real harm and adds nothing for a
    buyer. Borrower and guarantor names are not stored on the listing at
    all, so they cannot leak through a template change.
    """
    for path in ("/", f"/listing/{listing_id(client, '1')}"):
        body = client.get(path).text.lower()
        for token in ("borrower", "guarantor"):
            assert token not in body


def test_api_response_contains_no_borrower_fields(client):
    payload = client.get("/api/listings").json()
    serialised = str(payload).lower()
    assert "borrower" not in serialised
    assert "guarantor" not in serialised


# --- JSON API -------------------------------------------------------------


def test_api_lists_published_listings(client):
    payload = client.get("/api/listings").json()
    assert payload["total"] == 2
    assert len(payload["listings"]) == 2


def test_api_includes_a_disclaimer(client):
    assert "disclaimer" in client.get("/api/listings").json()


def test_api_filters_like_the_html_pages(client):
    payload = client.get("/api/listings", params={"state": "Gujarat"}).json()
    assert payload["total"] == 1
    assert payload["listings"][0]["city"] == "Vani"


def test_api_gives_both_raw_and_display_prices(client):
    item = client.get("/api/listings", params={"state": "Gujarat"}).json()["listings"][0]
    assert item["reserve_price"] == 900000.0
    assert item["reserve_price_display"] == "Rs 9.00 L"


def test_api_exposes_provenance(client):
    item = client.get("/api/listings").json()["listings"][0]
    assert item["source"]["notice_url"].startswith("https://baanknet.com/")
    assert item["source"]["last_verified_at"]


def test_api_page_size_is_capped(client):
    assert client.get("/api/listings", params={"page_size": 5000}).status_code == 422


def test_api_single_listing(client):
    response = client.get(f"/api/listings/{listing_id(client, '1')}")
    assert response.status_code == 200
    assert response.json()["city"] == "Mumbai"


def test_api_unknown_listing_is_404(client):
    assert client.get("/api/listings/999999").status_code == 404


def test_health_endpoint(client):
    payload = client.get("/api/health").json()
    assert payload["status"] == "ok"
    assert payload["listings"] == 2


# --- crawler directives ---------------------------------------------------


def test_robots_txt_allows_listings_but_not_the_api(client):
    body = client.get("/robots.txt").text
    assert "Disallow: /api/" in body
    assert "Allow: /" in body


def test_security_txt_is_published(client):
    body = client.get("/.well-known/security.txt").text
    assert "Contact: mailto:" in body


# --- new data notice ------------------------------------------------------


def test_version_endpoint_fingerprints_the_data(client):
    payload = client.get("/api/version").json()
    assert payload["count"] == 2  # published only
    assert "newest" in payload
    assert "changed" in payload


def test_version_counts_only_published_listings(client, db_session_factory):
    """A withheld listing appearing would prompt a refresh that shows
    the reader nothing new."""
    assert client.get("/api/version").json()["count"] == 2


def test_version_changes_when_a_listing_is_added(client, db_session_factory):
    before = client.get("/api/version").json()

    session = db_session_factory()
    ListingRepository(session).upsert(make("99", title="Brand new listing"))
    session.commit()
    session.close()

    after = client.get("/api/version").json()
    assert after["count"] == before["count"] + 1


def test_pages_carry_the_version_for_the_browser_to_compare(client):
    body = client.get("/").text
    assert 'id="update-notice"' in body
    assert "data-count=" in body


def test_version_reports_when_the_collector_last_ran(client):
    """'Nothing new' and 'nothing is running' look identical without
    this, and the second one is a fault."""
    assert "collected" in client.get("/api/version").json()


def test_pages_show_a_heartbeat(client):
    """Silence is ambiguous: the reader cannot tell a quiet hour from a
    dead collector."""
    body = client.get("/").text
    assert 'id="update-heartbeat"' in body
    assert "Watching for new listings" in body


def test_heartbeat_carries_the_last_collection_time(client):
    assert "data-collected=" in client.get("/").text


def test_heartbeat_appears_on_detail_pages_too(client):
    assert 'id="update-heartbeat"' in client.get(f"/listing/{listing_id(client, '1')}").text


def test_the_notice_starts_hidden(client):
    """It must only appear once something has actually changed."""
    body = client.get("/").text
    assert "update-notice" in body
    notice = body[body.index('id="update-notice"') : body.index('id="update-notice"') + 400]
    assert "hidden" in notice


def test_the_notice_offers_a_choice_rather_than_reloading(client):
    body = client.get("/").text
    assert "update-refresh" in body
    assert "update-dismiss" in body


def test_the_update_script_is_served(client):
    response = client.get("/static/updates.js")
    assert response.status_code == 200
    assert "api/version" in response.text


def test_detail_pages_also_offer_refresh(client):
    assert 'id="update-notice"' in client.get(f"/listing/{listing_id(client, '1')}").text


# --- crawler disclosure ---------------------------------------------------


def test_bot_page_exists(client):
    """CONTACT_URL points here, and it is sent with every request we make."""
    assert client.get("/bot").status_code == 200


def test_bot_page_shows_our_user_agent(client):
    assert "AuctionPortalBot/" in client.get("/bot").text


def test_bot_page_explains_how_to_block_us(client):
    body = client.get("/bot").text
    assert "robots.txt" in body
    assert "Disallow: /" in body


def test_bot_page_gives_a_contact_address(client):
    assert "mailto:" in client.get("/bot").text


def test_bot_page_states_we_do_not_publish_borrower_names(client):
    body = client.get("/bot").text.lower()
    assert "do not publish borrower" in body


def test_bot_page_is_linked_from_every_page(client):
    for path in ("/", f"/listing/{listing_id(client, '1')}"):
        assert 'href="/bot"' in client.get(path).text
