"""Validating coordinates against the state they claim to be in.

BAANKNET's coordinates are unreliable in two distinct ways:

  1. latitude and longitude are transposed on many records
  2. some are simply wrong - an Azamgarh (Uttar Pradesh) property was
     published at 14.64 N, 71.70 E, which is in the Arabian Sea

A country-level bounding box catches (1) but not (2): 14.64/71.70 is
inside India's box. Checking against the *state's* box catches both.

A wrongly placed pin on a multi-crore property is worse than no pin at
all, so anything that fails is discarded rather than displayed.

Boxes are deliberately generous - the aim is to reject coordinates that
are obviously wrong, not to police borders.
"""

from decimal import Decimal

# (min_lat, max_lat, min_lon, max_lon)
_STATE_BOUNDS: dict[str, tuple[float, float, float, float]] = {
    "andaman & nicobar islands": (6.0, 14.0, 92.0, 94.5),
    "andhra pradesh": (12.5, 20.0, 76.5, 85.0),
    "arunachal pradesh": (26.5, 29.6, 91.4, 97.5),
    "assam": (24.0, 28.1, 89.6, 96.2),
    "bihar": (24.1, 27.6, 83.2, 88.4),
    "chandigarh": (30.6, 30.9, 76.6, 77.0),
    "chhattisgarh": (17.6, 24.2, 80.1, 84.5),
    "dadra & nagar haveli & daman & diu": (20.0, 20.9, 72.7, 73.3),
    "dadra & nagar haveli and daman & diu": (20.0, 20.9, 72.7, 73.3),
    "delhi": (28.3, 29.0, 76.7, 77.5),
    "goa": (14.7, 15.9, 73.5, 74.5),
    "gujarat": (20.0, 24.8, 68.0, 74.6),
    "haryana": (27.5, 31.0, 74.3, 77.7),
    "himachal pradesh": (30.2, 33.4, 75.4, 79.1),
    "jammu & kashmir": (32.1, 37.2, 73.7, 80.4),
    "jharkhand": (21.8, 25.5, 83.2, 88.0),
    "karnataka": (11.4, 18.6, 73.9, 78.7),
    "kerala": (8.1, 12.9, 74.7, 77.5),
    "ladakh": (32.1, 37.2, 75.7, 80.4),
    "lakshadweep": (8.0, 12.4, 71.6, 74.1),
    "madhya pradesh": (20.9, 27.0, 73.9, 82.9),
    "maharashtra": (15.5, 22.2, 72.5, 81.0),
    "manipur": (23.7, 25.8, 92.8, 94.9),
    "meghalaya": (24.9, 26.2, 89.7, 92.9),
    "mizoram": (21.8, 24.6, 92.1, 93.5),
    "nagaland": (25.1, 27.1, 93.2, 95.4),
    "odisha": (17.7, 22.7, 81.3, 87.6),
    "puducherry": (9.8, 12.1, 74.7, 80.0),
    "punjab": (29.4, 32.7, 73.7, 77.0),
    "rajasthan": (22.9, 30.3, 69.4, 78.4),
    "sikkim": (26.9, 28.3, 87.9, 89.0),
    "tamil nadu": (7.9, 13.7, 76.1, 80.5),
    "telangana": (15.7, 20.0, 77.1, 81.9),
    "tripura": (22.8, 24.7, 90.9, 92.5),
    "uttar pradesh": (23.7, 30.6, 76.9, 84.8),
    "uttarakhand": (28.6, 31.6, 77.4, 81.2),
    "west bengal": (21.3, 27.4, 85.7, 90.0),
}

# Fallback when the state is unknown or unrecognised.
INDIA_BOUNDS = (6.0, 37.2, 68.0, 97.5)


def bounds_for(state: str | None) -> tuple[float, float, float, float]:
    if not state:
        return INDIA_BOUNDS
    return _STATE_BOUNDS.get(state.strip().lower(), INDIA_BOUNDS)


def within(
    latitude: Decimal, longitude: Decimal, bounds: tuple[float, float, float, float]
) -> bool:
    min_lat, max_lat, min_lon, max_lon = bounds
    return Decimal(str(min_lat)) <= latitude <= Decimal(str(max_lat)) and Decimal(
        str(min_lon)
    ) <= longitude <= Decimal(str(max_lon))


def resolve_coordinates(
    latitude: Decimal | None,
    longitude: Decimal | None,
    state: str | None,
) -> tuple[Decimal | None, Decimal | None, str | None]:
    """Validate a coordinate pair against its claimed state.

    Returns (latitude, longitude, flag). The flag is None when the pair
    was already correct, 'coordinates_transposed' when swapping them made
    it valid, and 'coordinates_outside_state' when neither order works -
    in which case both values are discarded.
    """
    if latitude is None or longitude is None:
        return None, None, None

    bounds = bounds_for(state)

    if within(latitude, longitude, bounds):
        return latitude, longitude, None

    if within(longitude, latitude, bounds):
        return longitude, latitude, "coordinates_transposed"

    return None, None, "coordinates_outside_state"
