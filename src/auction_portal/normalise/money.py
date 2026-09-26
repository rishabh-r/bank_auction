"""Parsing Indian rupee amounts.

Handles the forms that actually appear in auction notices and bank APIs:

    Rs.3,37,55,000/-        Indian digit grouping (2,2,3 - not 3,3,3)
    Rs. 337.55 Lakhs        lakh/crore multipliers
    Rs 3.3755 Cr
    131850000.00000         raw API decimals
    ३,३७,५५,०००             Devanagari numerals

Always Decimal, never float: losing paise on a three-crore figure is the
kind of error that ends up in a dispute.
"""

import re
from decimal import Decimal, InvalidOperation

# Longest first, so "lakhs" is matched before "lakh".
_MULTIPLIERS: tuple[tuple[str, Decimal], ...] = (
    ("crores", Decimal("1e7")),
    ("crore", Decimal("1e7")),
    ("karod", Decimal("1e7")),
    ("cr", Decimal("1e7")),
    ("lakhs", Decimal("1e5")),
    ("lacs", Decimal("1e5")),
    ("lakh", Decimal("1e5")),
    ("lac", Decimal("1e5")),
    ("thousand", Decimal("1e3")),
)

_DEVANAGARI = str.maketrans("०१२३४५६७८९", "0123456789")
_CURRENCY = re.compile(r"(?:rs\.?|inr|₹|/-|only|rupees)", re.IGNORECASE)
_NUMBER = re.compile(r"\d[\d,]*(?:\.\d+)?")

# Anything outside this range is almost certainly a parsing failure rather
# than a real Indian auction price.
MIN_PLAUSIBLE = Decimal("10000")
MAX_PLAUSIBLE = Decimal("1e12")


def parse_inr(value: object) -> Decimal | None:
    """Parse a rupee amount. Returns None when it cannot be read confidently."""
    if value is None:
        return None

    if isinstance(value, (int, float, Decimal)):
        try:
            return _quantise(Decimal(str(value)))
        except InvalidOperation:
            return None

    text = str(value).translate(_DEVANAGARI).strip().lower()
    if not text:
        return None

    text = _CURRENCY.sub(" ", text)

    multiplier = Decimal(1)
    for word, factor in _MULTIPLIERS:
        if re.search(rf"\b{word}\b", text):
            multiplier = factor
            text = re.sub(rf"\b{word}\b", " ", text)
            break

    match = _NUMBER.search(text)
    if not match:
        return None

    try:
        # Commas are stripped rather than interpreted: Indian grouping is
        # 2,2,3 and Western is 3,3,3, so their positions cannot be trusted.
        amount = Decimal(match.group().replace(",", "")) * multiplier
    except InvalidOperation:
        return None

    return _quantise(amount)


def is_plausible_price(amount: Decimal | None) -> bool:
    """Sanity band. A flat listed at Rs 8,000 means the parse failed."""
    return amount is not None and MIN_PLAUSIBLE <= amount <= MAX_PLAUSIBLE


def emd_ratio(reserve: Decimal | None, emd: Decimal | None) -> Decimal | None:
    """EMD as a fraction of reserve price.

    Conventionally 10%. A ratio far outside 5-20% is strong evidence that
    two columns were confused during extraction.
    """
    if not reserve or not emd or reserve == 0:
        return None
    return (emd / reserve).quantize(Decimal("0.0001"))


def format_inr(amount: Decimal | None) -> str:
    """Render for display in Indian convention: 'Rs 3.38 Cr', 'Rs 45.20 L'."""
    if amount is None:
        return "-"
    if amount >= Decimal("1e7"):
        return f"Rs {amount / Decimal('1e7'):.2f} Cr"
    if amount >= Decimal("1e5"):
        return f"Rs {amount / Decimal('1e5'):.2f} L"
    return f"Rs {amount:,.0f}"


def _quantise(amount: Decimal) -> Decimal:
    return amount.quantize(Decimal("0.01"))
