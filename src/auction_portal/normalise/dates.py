"""Parsing dates and times from Indian sources.

The dangerous case is `05/02/2026`. In India that is 5 February; read as US
format it is 2 May. Both parse successfully, so there is no exception to
catch - you simply show the wrong date and someone misses an auction.

Every format here is therefore explicit and day-first. We never fall back
to a permissive parser.
"""

from datetime import UTC, date, datetime
from zoneinfo import ZoneInfo

IST = ZoneInfo("Asia/Kolkata")

# Day-first only. Ambiguous input is resolved towards Indian convention.
_DATE_FORMATS = (
    "%d/%m/%Y",
    "%d-%m-%Y",
    "%d.%m.%Y",
    "%d-%b-%Y",
    "%d %b %Y",
    "%d %B %Y",
    "%d-%B-%Y",
    "%d/%m/%y",
    "%d-%m-%y",
    "%Y-%m-%d",  # ISO, unambiguous
)

_DATETIME_FORMATS = tuple(
    f"{d} {t}"
    for d in ("%d/%m/%Y", "%d-%m-%Y", "%d.%m.%Y", "%d-%b-%Y", "%Y-%m-%d")
    for t in ("%H:%M", "%H:%M:%S", "%I:%M %p", "%I.%M %p", "%I:%M%p")
)


def parse_date(value: object) -> date | None:
    """Parse a date-only value, e.g. '28-Jul-2022' or '2026-09-25'."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value

    text = str(value).strip()
    if not text:
        return None
    text = text.split("T")[0]

    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None


def parse_indian_date(value: object) -> datetime | None:
    """Parse a date or datetime written in local Indian convention, as IST."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=IST)

    text = " ".join(str(value).split()).strip()
    if not text:
        return None

    for fmt in _DATETIME_FORMATS:
        try:
            return datetime.strptime(text, fmt).replace(tzinfo=IST)
        except ValueError:
            continue

    if (only_date := parse_date(text)) is not None:
        return datetime(only_date.year, only_date.month, only_date.day, tzinfo=IST)
    return None


def parse_iso_utc(value: object) -> datetime | None:
    """Parse an ISO 8601 timestamp from an API, e.g. '2026-10-28T08:30:00.000Z'.

    Returned in UTC. Callers that need to show it to a user should convert
    to IST with `to_ist`.
    """
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.astimezone(UTC) if value.tzinfo else value.replace(tzinfo=UTC)

    text = str(value).strip()
    if not text:
        return None

    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None

    return parsed.astimezone(UTC) if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def to_ist(moment: datetime | None) -> datetime | None:
    if moment is None:
        return None
    return moment.astimezone(IST)


def days_between(earlier: date | datetime | None, later: date | datetime | None) -> int | None:
    """Whole days from `earlier` to `later`, or None if either is missing."""
    if earlier is None or later is None:
        return None
    if isinstance(earlier, datetime):
        earlier = earlier.date()
    if isinstance(later, datetime):
        later = later.date()
    return (later - earlier).days
