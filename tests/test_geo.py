"""Tests for coordinate validation against the claimed state."""

from decimal import Decimal

import pytest

from auction_portal.normalise.geo import INDIA_BOUNDS, bounds_for, resolve_coordinates


def test_correct_coordinates_pass_unchanged():
    lat, lon, flag = resolve_coordinates(Decimal("11.280619"), Decimal("77.582599"), "Tamil Nadu")
    assert (lat, lon, flag) == (Decimal("11.280619"), Decimal("77.582599"), None)


def test_transposed_coordinates_are_swapped_back():
    """The real Tiruppur record: BAANKNET has latitude and longitude the
    wrong way round."""
    lat, lon, flag = resolve_coordinates(Decimal("77.582599"), Decimal("11.280619"), "Tamil Nadu")
    assert lat == Decimal("11.280619")
    assert lon == Decimal("77.582599")
    assert flag == "coordinates_transposed"


def test_coordinates_in_the_wrong_state_are_discarded():
    """The real Azamgarh record: 14.64 N, 71.70 E is in the Arabian Sea.

    This is inside India's bounding box, so only a state-level check
    catches it. A wrong pin is worse than no pin.
    """
    lat, lon, flag = resolve_coordinates(
        Decimal("14.641932"), Decimal("71.702334"), "Uttar Pradesh"
    )
    assert lat is None
    assert lon is None
    assert flag == "coordinates_outside_state"


def test_missing_coordinates_are_not_an_error():
    assert resolve_coordinates(None, None, "Gujarat") == (None, None, None)
    assert resolve_coordinates(Decimal("11.2"), None, "Gujarat") == (None, None, None)


def test_unknown_state_falls_back_to_india_bounds():
    """We should not reject a valid pin just because a state name is new."""
    lat, lon, flag = resolve_coordinates(Decimal("19.076"), Decimal("72.877"), "Some New Territory")
    assert (lat, lon, flag) == (Decimal("19.076"), Decimal("72.877"), None)


def test_coordinates_outside_india_are_discarded():
    lat, lon, flag = resolve_coordinates(Decimal("51.5"), Decimal("-0.12"), None)
    assert lat is None and flag == "coordinates_outside_state"


@pytest.mark.parametrize(
    ("state", "lat", "lon"),
    [
        ("Maharashtra", "19.0760", "72.8777"),  # Mumbai
        ("Delhi", "28.6139", "77.2090"),
        ("Tamil Nadu", "13.0827", "80.2707"),  # Chennai
        ("West Bengal", "22.5726", "88.3639"),  # Kolkata
        ("Karnataka", "12.9716", "77.5946"),  # Bengaluru
        ("Gujarat", "23.0225", "72.5714"),  # Ahmedabad
        ("Telangana", "17.3850", "78.4867"),  # Hyderabad
        ("Uttar Pradesh", "26.8467", "80.9462"),  # Lucknow
    ],
)
def test_real_city_coordinates_are_accepted(state, lat, lon):
    resolved_lat, _, flag = resolve_coordinates(Decimal(lat), Decimal(lon), state)
    assert flag is None
    assert resolved_lat == Decimal(lat)


def test_state_lookup_is_case_insensitive():
    assert bounds_for("TAMIL NADU") == bounds_for("tamil nadu")
    assert bounds_for(None) == INDIA_BOUNDS
