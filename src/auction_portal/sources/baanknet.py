"""BAANKNET adapter.

BAANKNET (baanknet.com) is the Department of Financial Services auction
platform, launched 3 January 2025. All 12 public sector banks and the IBBI
list properties there.

Why this source first:
  - robots.txt is "User-agent: * / Disallow:" - everything is permitted
  - it publishes sitemaps, which is a site explicitly telling crawlers what
    to fetch; we use them rather than guessing URLs
  - detail pages are server-rendered, so the structured record the page was
    built from is available directly (Tier 0 - no OCR, no LLM, no guessing)
  - ~72,000 properties across every state

Data quality notes discovered during development:
  - `latitude` and `longitude` are transposed in the source. A Tirupur
    property reports latitude 77.58 / longitude 11.28; Tirupur is at
    11.28 N, 77.58 E. We detect and correct this rather than trusting it.
  - Possession type is more reliably derived from which possession *date*
    is populated than from propertyPossessionTypeId.
  - Addresses contain U+FFFD from a broken encoding round-trip upstream.
"""

import logging
import re
from datetime import UTC, datetime
from decimal import Decimal

from auction_portal.fetching.models import RawDocument
from auction_portal.normalise.area import canonical_unit, to_square_feet
from auction_portal.normalise.dates import parse_date, parse_iso_utc
from auction_portal.normalise.geo import resolve_coordinates
from auction_portal.normalise.money import emd_ratio, is_plausible_price, parse_inr
from auction_portal.normalise.text import (
    clean_text,
    normalise_phone,
    normalise_pincode,
    title_case,
)
from auction_portal.sources.base import ParsedListing, SourceAdapter, strip_personal_data
from auction_portal.sources.flight import extract_payload, find_objects, largest_object

log = logging.getLogger(__name__)

_SITEMAP_LOC = re.compile(r"<loc>(.*?)</loc>", re.DOTALL)
_DETAIL_ID = re.compile(r"/property-detail/(\d+)/([0-9a-f]+)")


class BaanknetAdapter(SourceAdapter):
    source_id = "baanknet"
    display_name = "BAANKNET (PSB Alliance)"
    base_url = "https://baanknet.com"
    asset_class = "property"

    #: Sitemaps listing individual property detail pages.
    property_sitemaps = (
        "https://baanknet.com/sitemap-properties-1.xml",
        "https://baanknet.com/sitemap-properties-2.xml",
    )

    def __init__(self, fetch_text=None):
        """`fetch_text` is injected so tests never touch the network."""
        self._fetch_text = fetch_text

    # --- discovery --------------------------------------------------------

    def discover(self, limit: int | None = None) -> list[str]:
        """Read the published sitemaps for property detail URLs."""
        if self._fetch_text is None:
            raise RuntimeError("BaanknetAdapter needs a fetch_text callable to discover")

        # dict preserves insertion order while removing duplicates: the same
        # property can appear in more than one sitemap, and fetching it twice
        # wastes a request and the source's bandwidth.
        urls: dict[str, None] = {}

        for sitemap in self.property_sitemaps:
            try:
                body = self._fetch_text(sitemap)
            except Exception as exc:
                log.error("could not read sitemap %s: %s", sitemap, exc)
                continue

            found = [u for u in _SITEMAP_LOC.findall(body) if "/property-detail/" in u]
            log.info("%s -> %d property urls", sitemap.rsplit("/", 1)[-1], len(found))
            urls.update(dict.fromkeys(found))

            if limit and len(urls) >= limit:
                break

        result = list(urls)
        return result[:limit] if limit else result

    # --- parsing ----------------------------------------------------------

    def parse(self, document: RawDocument) -> list[ParsedListing]:
        html = document.content.decode("utf-8", errors="replace")
        payload = extract_payload(html)
        if not payload:
            log.warning("no server payload in %s", document.url)
            return []

        property_record = largest_object(payload, "propertyDetailId")
        if property_record is None:
            log.warning("no property record in %s", document.url)
            return []

        auction_record = self._best_auction(payload)
        listing = self._build(document.url, property_record, auction_record)
        return [listing] if listing else []

    @staticmethod
    def _best_auction(payload: str) -> dict:
        """Pick the auction object carrying the most detail."""
        candidates = find_objects(payload, "reservePrice")
        return max(candidates, key=len) if candidates else {}

    def _build(self, url: str, prop: dict, auction: dict) -> ParsedListing | None:
        match = _DETAIL_ID.search(url)
        external_id = str(prop.get("propertyDetailId") or (match.group(1) if match else ""))
        if not external_id:
            log.warning("no property id for %s", url)
            return None

        listing = ParsedListing(
            source_id=self.source_id,
            external_id=external_id,
            canonical_url=url,
            asset_class="property",
            asset_key=clean_text(prop.get("propertyUniqueId")) or f"baanknet:{external_id}",
            legal_basis="sarfaesi",
        )

        self._apply_classification(listing, prop)
        self._apply_location(listing, prop)
        self._apply_money(listing, prop, auction)
        self._apply_schedule(listing, auction)
        self._apply_legal(listing, prop, auction)

        # Borrower and guarantor details are dropped before storage, not
        # merely hidden at display time.
        listing.raw_payload = {
            "property": strip_personal_data(prop),
            "auction": strip_personal_data(auction),
        }
        self._score(listing)
        return listing

    # --- field groups -----------------------------------------------------

    def _apply_classification(self, listing: ParsedListing, prop: dict) -> None:
        # Nested: propertySubType.propertyType.propertyType -> "Agriculture"
        subtype_node = _node(prop, "propertySubType")
        type_name = _dig(subtype_node, "propertyType", "propertyType")
        listing.asset_type = _normalise_asset_type(type_name)
        listing.asset_subtype = title_case(
            subtype_node.get("propertySubType") or prop.get("specificPropSubtype")
        )

        listing.description = clean_text(prop.get("summaryDesc"), max_length=2000)
        # summaryDesc is sometimes a flight placeholder like "$21" rather
        # than real text; treat those as absent.
        if listing.description and re.fullmatch(r"\$\d+", listing.description):
            listing.description = None

        self._apply_area(listing, prop)

        locality = title_case(prop.get("locality"))
        city = _dig(prop, "city", "name")
        bits = [listing.asset_subtype or listing.asset_type or "Property"]
        if locality:
            bits.append(f"at {locality}")
        if city:
            bits.append(f"in {title_case(city)}")
        listing.title = clean_text(" ".join(bits), max_length=250)

    @staticmethod
    def _apply_area(listing: ParsedListing, prop: dict) -> None:
        details = _node(prop, "propertyTypeDetails")
        if not details:
            return

        unit = _dig(details, "unitOfMeasure", "measurementAbb")

        # carpetAreaSqFeet is named for square feet but actually carries the
        # value in whatever unitOfMeasure says, so it must be converted.
        for field_name in ("carpetAreaSqFeet", "builtUpAreaSqFeet", "areaInSqYard"):
            raw = details.get(field_name)
            if raw in (None, "", 0):
                continue
            value = _to_decimal(raw)
            if value is None or value <= 0:
                continue
            effective_unit = "sqyard" if field_name == "areaInSqYard" else unit
            listing.area_value = value
            listing.area_unit = canonical_unit(effective_unit) or effective_unit
            listing.area_sqft = to_square_feet(value, effective_unit)
            if listing.area_sqft is None:
                listing.flag("area_unit_unconvertible")
            break

    def _apply_location(self, listing: ParsedListing, prop: dict) -> None:
        listing.address = clean_text(prop.get("address"), max_length=1000)
        listing.locality = title_case(prop.get("locality"))

        # Nested: city.name, district.name, district.State.name
        district_node = _node(prop, "district")
        listing.city = title_case(_dig(prop, "city", "name"))
        listing.district = title_case(district_node.get("name"))
        listing.state = title_case(_dig(district_node, "State", "name"))

        listing.pincode = normalise_pincode(prop.get("pincode")) or normalise_pincode(
            prop.get("address")
        )

        # Validated against the claimed state, not merely against India:
        # an Azamgarh (Uttar Pradesh) property was published at
        # 14.64 N, 71.70 E, which is inside India's bounding box but sits
        # in the Arabian Sea.
        latitude, longitude, flag = resolve_coordinates(
            _to_decimal(prop.get("latitude")),
            _to_decimal(prop.get("longitude")),
            listing.state,
        )
        listing.latitude = latitude
        listing.longitude = longitude
        if flag:
            listing.flag(flag)

    def _apply_money(self, listing: ParsedListing, prop: dict, auction: dict) -> None:
        listing.reserve_price = parse_inr(auction.get("reservePrice") or prop.get("propertyPrice"))
        listing.emd_amount = parse_inr(auction.get("emd"))
        listing.bid_increment = parse_inr(auction.get("incrementPrice"))
        listing.outstanding_dues = parse_inr(prop.get("npaAmount"))

        if listing.reserve_price is not None and not is_plausible_price(listing.reserve_price):
            listing.flag("reserve_price_implausible")
            listing.reserve_price = None

        # EMD is conventionally 10% of the reserve price. A ratio well
        # outside 5-20% suggests the two values were confused somewhere.
        ratio = emd_ratio(listing.reserve_price, listing.emd_amount)
        if ratio is not None and not (Decimal("0.05") <= ratio <= Decimal("0.20")):
            listing.flag(f"emd_ratio_unusual:{ratio}")

    def _apply_schedule(self, listing: ParsedListing, auction: dict) -> None:
        listing.auction_start_at = parse_iso_utc(auction.get("auctionFrom"))
        listing.auction_end_at = parse_iso_utc(
            auction.get("auctionExtendedTo") or auction.get("auctionTo")
        )
        listing.emd_deadline_at = parse_iso_utc(auction.get("emdEnd"))
        listing.inspection_from = parse_iso_utc(auction.get("inspectionStart"))
        listing.inspection_to = parse_iso_utc(auction.get("inspectionEnd"))

        if (
            listing.auction_start_at
            and listing.auction_end_at
            and listing.auction_end_at < listing.auction_start_at
        ):
            listing.flag("auction_end_before_start")
            listing.auction_end_at = None

        listing.status = self._status(listing.auction_start_at, listing.auction_end_at)

    @staticmethod
    def _status(start: datetime | None, end: datetime | None) -> str:
        """Auction lifecycle state.

        'unscheduled' is a real, common state on BAANKNET, not an error:
        banks list a property first and fix the auction date later. Those
        listings are still useful to a buyer watching a locality.
        """
        now = datetime.now(UTC)
        if start is None:
            return "unscheduled"
        if now < start:
            return "upcoming"
        if end is not None and now <= end:
            return "live"
        return "closed"

    def _apply_legal(self, listing: ParsedListing, prop: dict, auction: dict) -> None:
        listing.bank_name = clean_text(prop.get("bankName") or auction.get("bankName"))
        listing.branch_name = title_case(auction.get("auctionBranch") or prop.get("branchName"))

        listing.symbolic_possession_date = parse_date(prop.get("symbolicPossDate"))
        listing.physical_possession_date = parse_date(prop.get("physicalpossdate"))
        listing.npa_date = parse_date(prop.get("npaDate"))
        listing.possession_type = self._possession_type(listing, prop)

        # propertyTypeOfAction distinguishes a SARFAESI sale from a DRT
        # recovery sale. Different legal track, so worth recording.
        action = _dig(prop, "propertyTypeOfAction", "typeOfAction")
        listing.legal_basis = _normalise_legal_basis(action)

        listing.authorised_officer_name = title_case(
            auction.get("checkerName") or auction.get("inspectionName")
        )
        listing.authorised_officer_phone = normalise_phone(auction.get("inspectionMobileNo"))

    @staticmethod
    def _possession_type(listing: ParsedListing, prop: dict) -> str:
        """Prefer the possession dates; fall back to the declared type.

        The dates are populated consistently by uploading banks; the
        declared type is often left as the default 'Other'.
        """
        if listing.physical_possession_date:
            return "physical"
        if listing.symbolic_possession_date:
            return "symbolic"

        declared = (_dig(prop, "propertyPossessionType", "propertyPossessionType") or "").lower()
        if "physical" in declared:
            return "physical"
        if "symbolic" in declared:
            return "symbolic"
        return "unknown"

    # --- quality ----------------------------------------------------------

    def _score(self, listing: ParsedListing) -> None:
        """Confidence drives whether a listing is shown publicly.

        Anything the portal cannot state accurately is withheld rather than
        guessed at - fewer listings, but no wrong prices.
        """
        confidence = Decimal("1.00")

        # Reserve price is the field we must never get wrong, so its
        # absence is the heaviest penalty.
        if listing.reserve_price is None:
            listing.flag("missing_reserve_price")
            confidence -= Decimal("0.40")

        # A missing date on an unscheduled listing is expected, not a data
        # quality problem. Only penalise it where a date should exist.
        if listing.auction_start_at is None:
            if listing.status == "unscheduled":
                listing.flag("auction_not_yet_scheduled")
                confidence -= Decimal("0.10")
            else:
                listing.flag("missing_auction_date")
                confidence -= Decimal("0.30")

        if not listing.state:
            listing.flag("missing_state")
            confidence -= Decimal("0.15")
        if not listing.city:
            listing.flag("missing_city")
            confidence -= Decimal("0.10")
        if listing.emd_amount is None and listing.status != "unscheduled":
            listing.flag("missing_emd")
            confidence -= Decimal("0.05")
        if any(f.startswith("emd_ratio_unusual") for f in listing.quality_flags):
            confidence -= Decimal("0.15")

        listing.confidence = max(Decimal("0.00"), confidence)


def _to_decimal(value: object) -> Decimal | None:
    if value is None or value == "":
        return None
    try:
        return Decimal(str(value))
    except (ArithmeticError, ValueError):
        return None


def _node(record: dict, key: str) -> dict:
    """A nested object, or an empty dict when absent or the wrong shape."""
    value = record.get(key)
    return value if isinstance(value, dict) else {}


def _dig(record: dict, *keys: str) -> object:
    """Walk a chain of nested keys, returning None if any link is missing."""
    current: object = record
    for key in keys:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


def _normalise_asset_type(value: object) -> str | None:
    """Map BAANKNET's type names onto our own taxonomy."""
    text = clean_text(value)
    if text is None:
        return None
    lowered = text.lower()
    for token, canonical in (
        ("residential", "residential"),
        ("commercial", "commercial"),
        ("industrial", "industrial"),
        ("agricultur", "agricultural"),
    ):
        if token in lowered:
            return canonical
    return "other"


def _normalise_legal_basis(value: object) -> str:
    text = (clean_text(value) or "").lower()
    if "drt" in text:
        return "drt"
    if "ibc" in text or "liquidat" in text or "insolven" in text:
        return "ibc_liquidation"
    return "sarfaesi"
