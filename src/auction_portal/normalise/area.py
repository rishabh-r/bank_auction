"""Converting Indian area units to a common basis.

Notices and bank systems use square feet, square metres, square yards
(gaj), acres, hectares, cents, gunthas, grounds, ares, kanals and marlas -
sometimes two of them in one record. We keep the original value and unit
for display, and a square-foot figure so that "800-1200 sqft" can be a
filter.

Bigha is deliberately excluded: it varies from roughly 1,600 to 27,000
square feet by state, so converting it without knowing the state would
invent precision that is not there.
"""

import re
from decimal import Decimal, InvalidOperation

_TO_SQFT: dict[str, Decimal] = {
    "sqft": Decimal("1"),
    "sqfeet": Decimal("1"),
    "squarefeet": Decimal("1"),
    "sft": Decimal("1"),
    "sqm": Decimal("10.7639"),
    "sqmt": Decimal("10.7639"),
    "sqmeter": Decimal("10.7639"),
    "sqmeters": Decimal("10.7639"),
    "squaremeters": Decimal("10.7639"),
    "sqyard": Decimal("9"),
    "sqyards": Decimal("9"),
    "squareyards": Decimal("9"),
    "gaj": Decimal("9"),
    "acre": Decimal("43560"),
    "acres": Decimal("43560"),
    "hectare": Decimal("107639"),
    "hectares": Decimal("107639"),
    "cent": Decimal("435.6"),
    "cents": Decimal("435.6"),
    "guntha": Decimal("1089"),
    "gunthas": Decimal("1089"),
    "ground": Decimal("2400"),
    "grounds": Decimal("2400"),
    "are": Decimal("1076.39"),
    "ares": Decimal("1076.39"),
    "kanal": Decimal("5445"),
    "marla": Decimal("272.25"),
}

#: Units whose conversion depends on the state; never converted silently.
AMBIGUOUS_UNITS = frozenset({"bigha", "bighas", "katha", "kattha", "biswa"})

_CLEAN = re.compile(r"[\s._\-]+")


def canonical_unit(unit: object) -> str | None:
    """Normalise a unit label, e.g. 'Sq. Ft.' -> 'sqft'."""
    if unit is None:
        return None
    key = _CLEAN.sub("", str(unit).strip().lower())
    if not key:
        return None
    key = key.replace("square", "sq").replace("feets", "feet")
    if key in _TO_SQFT or key in AMBIGUOUS_UNITS:
        return key
    # Try a few common spellings before giving up.
    for candidate in (key.rstrip("s"), key + "s"):
        if candidate in _TO_SQFT or candidate in AMBIGUOUS_UNITS:
            return candidate
    return key


def to_square_feet(value: object, unit: object) -> Decimal | None:
    """Convert an area to square feet, or None if it cannot be done safely."""
    if value is None:
        return None
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None
    if amount <= 0:
        return None

    key = canonical_unit(unit)
    if key is None or key in AMBIGUOUS_UNITS:
        return None

    factor = _TO_SQFT.get(key)
    if factor is None:
        return None
    return (amount * factor).quantize(Decimal("0.01"))


def format_area(value: Decimal | None, unit: str | None) -> str:
    if value is None:
        return "-"
    return f"{value:,.0f} {unit or 'sqft'}"
