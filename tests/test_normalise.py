"""Tests for normalising Indian money, dates, areas and text."""

from datetime import date, datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest

from auction_portal.normalise.area import canonical_unit, to_square_feet
from auction_portal.normalise.dates import (
    IST,
    days_between,
    parse_date,
    parse_indian_date,
    parse_iso_utc,
    to_ist,
)
from auction_portal.normalise.money import (
    emd_ratio,
    format_inr,
    is_plausible_price,
    parse_inr,
)
from auction_portal.normalise.text import (
    clean_text,
    normalise_phone,
    normalise_pincode,
    title_case,
)

# --- money ----------------------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        # The real HDFC notice values from the project research.
        ("Rs.3,37,55,000/-", Decimal("33755000.00")),
        ("Rs.33,75,500/-", Decimal("3375500.00")),
        # Indian grouping is 2,2,3 - comma positions cannot be trusted.
        ("3,37,55,000", Decimal("33755000.00")),
        ("33,755,000", Decimal("33755000.00")),
        ("Rs 3.3755 Cr", Decimal("33755000.00")),
        ("337.55 Lakhs", Decimal("33755000.00")),
        ("₹ 45,00,000", Decimal("4500000.00")),
        ("131850000.00000", Decimal("131850000.00")),
        (275000, Decimal("275000.00")),
        (Decimal("451980.00000"), Decimal("451980.00")),
        ("१,००,०००", Decimal("100000.00")),  # Devanagari numerals
        ("Rs. 50,000/- only", Decimal("50000.00")),
    ],
)
def test_parse_inr(raw, expected):
    assert parse_inr(raw) == expected


@pytest.mark.parametrize("raw", [None, "", "   ", "not a number", "N/A", "-"])
def test_parse_inr_returns_none_rather_than_guessing(raw):
    assert parse_inr(raw) is None


def test_parse_inr_keeps_paise_exactly():
    """Decimal, not float. Losing paise on a crore is a dispute waiting."""
    assert parse_inr("Rs.3,38,94,383.15") == Decimal("33894383.15")


def test_emd_ratio_confirms_correct_column_split():
    """The real HDFC figures: EMD is exactly 10% of the reserve price.

    This check is what catches a parser that grabbed the wrong column.
    """
    reserve = parse_inr("Rs.3,37,55,000/-")
    emd = parse_inr("Rs.33,75,500/-")
    assert emd_ratio(reserve, emd) == Decimal("0.1000")


def test_emd_ratio_flags_a_confused_column():
    reserve = parse_inr("Rs.3,37,55,000/-")
    dues = parse_inr("Rs.3,38,94,383.15")  # outstanding dues, not the EMD
    ratio = emd_ratio(reserve, dues)
    assert not (Decimal("0.05") <= ratio <= Decimal("0.20"))


@pytest.mark.parametrize(
    ("amount", "plausible"),
    [
        (Decimal("33755000"), True),
        (Decimal("500000"), True),
        (Decimal("8000"), False),  # far too cheap for a property
        (Decimal("1e13"), False),  # far too expensive
        (None, False),
    ],
)
def test_price_plausibility_band(amount, plausible):
    assert is_plausible_price(amount) is plausible


@pytest.mark.parametrize(
    ("amount", "shown"),
    [
        (Decimal("33755000"), "Rs 3.38 Cr"),
        (Decimal("4500000"), "Rs 45.00 L"),
        (Decimal("50000"), "Rs 50,000"),
        (None, "-"),
    ],
)
def test_format_inr(amount, shown):
    assert format_inr(amount) == shown


# --- dates ----------------------------------------------------------------


def test_indian_dates_are_day_first():
    """05/02/2026 is 5 February in India, not 2 May.

    Both readings parse successfully, so this cannot be caught at runtime -
    only by getting the convention right here.
    """
    assert parse_date("05/02/2026") == date(2026, 2, 5)
    assert parse_date("27/01/2026") == date(2026, 1, 27)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("28-Jul-2022", date(2022, 7, 28)),
        ("15.01.2026", date(2026, 1, 15)),
        ("2026-09-25", date(2026, 9, 25)),
        ("2026-09-25T13:54:03.000Z", date(2026, 9, 25)),
        ("1 March 2026", date(2026, 3, 1)),
    ],
)
def test_parse_date_formats(raw, expected):
    assert parse_date(raw) == expected


@pytest.mark.parametrize("raw", [None, "", "not a date", "13/13/2026"])
def test_parse_date_rejects_nonsense(raw):
    assert parse_date(raw) is None


def test_parse_iso_utc_handles_api_timestamps():
    parsed = parse_iso_utc("2026-10-28T08:30:00.000Z")
    assert parsed.year == 2026
    assert parsed.hour == 8
    assert parsed.tzinfo is not None


def test_ist_conversion_shows_local_auction_time():
    """08:30 UTC is 14:00 IST - what a bidder actually needs to see."""
    shown = to_ist(parse_iso_utc("2026-10-28T08:30:00.000Z"))
    assert (shown.hour, shown.minute) == (14, 0)


def test_parse_indian_date_attaches_ist():
    parsed = parse_indian_date("27/01/2026 15:00")
    assert parsed == datetime(2026, 1, 27, 15, 0, tzinfo=ZoneInfo("Asia/Kolkata"))
    assert parsed.tzinfo == IST


def test_days_between_enforces_the_rule_9_1_gap():
    """Rule 9(1): at least 30 days between sale notice and auction."""
    assert days_between(date(2026, 1, 15), date(2026, 2, 14)) == 30
    assert days_between(date(2026, 1, 15), date(2026, 2, 5)) == 21  # unlawfully short
    assert days_between(None, date(2026, 2, 5)) is None


# --- area -----------------------------------------------------------------


@pytest.mark.parametrize(
    ("value", "unit", "expected"),
    [
        (100, "sqft", Decimal("100.00")),
        (100, "Sq. Ft.", Decimal("100.00")),
        (1, "acre", Decimal("43560.00")),
        (1, "hectares", Decimal("107639.00")),
        (242.33, "sqyard", Decimal("2180.97")),  # the HDFC Kailash Hills plot
        (10, "sqm", Decimal("107.64")),
    ],
)
def test_area_conversion(value, unit, expected):
    assert to_square_feet(value, unit) == expected


@pytest.mark.parametrize("unit", ["bigha", "katha", "biswa"])
def test_ambiguous_units_are_refused_not_guessed(unit):
    """A bigha ranges from ~1,600 to ~27,000 sqft depending on the state."""
    assert to_square_feet(10, unit) is None


def test_unknown_unit_returns_none():
    assert to_square_feet(10, "furlongs") is None
    assert to_square_feet(10, None) is None


def test_canonical_unit_normalises_spelling():
    assert canonical_unit("Sq. Ft.") == "sqft"
    assert canonical_unit("SQUARE YARDS") == "sqyards"


# --- text -----------------------------------------------------------------


def test_clean_text_collapses_whitespace_and_newlines():
    raw = "NEW T S NO:1 PART ,\n\n  BLOCK 31,   WARD : B "
    assert clean_text(raw) == "NEW T S NO:1 PART , BLOCK 31, WARD : B"


def test_clean_text_repairs_broken_encoding():
    """BAANKNET addresses contain U+FFFD from an upstream encoding fault."""
    assert "\ufffd" not in clean_text("Tirupur \ufffd 641603")


@pytest.mark.parametrize("raw", [None, "", "  ", "null", "N/A", "-", "nil"])
def test_clean_text_treats_placeholders_as_absent(raw):
    assert clean_text(raw) is None


def test_title_case_makes_shouted_names_readable():
    assert title_case("BOMMASANI SWETHA") == "Bommasani Swetha"
    assert title_case("STATE BANK OF INDIA") == "State Bank Of India"


def test_title_case_leaves_mixed_case_alone():
    assert title_case("Bank of Baroda") == "Bank of Baroda"


def test_pincode_extracted_from_free_text():
    assert normalise_pincode("Tirupur - 641603") == "641603"
    assert normalise_pincode("641603") == "641603"
    assert normalise_pincode("no pincode here") is None


def test_phone_normalisation_strips_country_code():
    assert normalise_phone("+91 98348 23416") == "9834823416"
    assert normalise_phone("09834823416") == "9834823416"
    assert normalise_phone("9834823416") == "9834823416"
    assert normalise_phone("abc") is None
