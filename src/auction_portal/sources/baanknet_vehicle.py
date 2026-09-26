"""BAANKNET vehicle adapter.

Vehicles reach auction by a different legal route from property. A car is
hypothecated, not mortgaged, and banks almost never use SARFAESI for one -
the Section 14 magistrate route costs more than the vehicle is worth.
Instead they repossess under the contractual repossession clause governed
by RBI's Responsible Business Conduct Directions. BAANKNET records this as
`typeOfAction: "Under Hypothecation"`.

The record shape differs from property too: location fields are flat and
prefixed `repossession*` rather than nested.

One deliberate omission: `ownerAddress` is the defaulting borrower's home
address. It is never stored. Where the vehicle physically sits - the
parking yard - is what a bidder actually needs, and carries no personal
data.
"""

import logging
import re
from decimal import Decimal

from auction_portal.fetching.models import RawDocument
from auction_portal.normalise.dates import parse_date, parse_iso_utc
from auction_portal.normalise.money import is_plausible_price, parse_inr
from auction_portal.normalise.text import clean_text, normalise_pincode, title_case
from auction_portal.sources.base import ParsedListing, SourceAdapter, strip_personal_data
from auction_portal.sources.flight import extract_payload, find_objects

log = logging.getLogger(__name__)

_SITEMAP_LOC = re.compile(r"<loc>(.*?)</loc>", re.DOTALL)
_DETAIL_ID = re.compile(r"/vehicle-detail/(\d+)/([0-9a-f]+)")


class BaanknetVehicleAdapter(SourceAdapter):
    source_id = "baanknet_vehicle"
    display_name = "BAANKNET vehicles"
    base_url = "https://baanknet.com"
    asset_class = "vehicle"

    vehicle_sitemaps = ("https://baanknet.com/sitemap-vehicles-1.xml",)

    def __init__(self, fetch_text=None):
        self._fetch_text = fetch_text

    # --- discovery --------------------------------------------------------

    def discover(self, limit: int | None = None) -> list[str]:
        if self._fetch_text is None:
            raise RuntimeError("BaanknetVehicleAdapter needs a fetch_text callable")

        urls: dict[str, None] = {}
        for sitemap in self.vehicle_sitemaps:
            try:
                body = self._fetch_text(sitemap)
            except Exception as exc:
                log.error("could not read sitemap %s: %s", sitemap, exc)
                continue

            found = [u for u in _SITEMAP_LOC.findall(body) if "/vehicle-detail/" in u]
            log.info("%s -> %d vehicle urls", sitemap.rsplit("/", 1)[-1], len(found))
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
            return []

        records = find_objects(payload, "vehicleId")
        if not records:
            log.warning("no vehicle record in %s", document.url)
            return []

        record = max(records, key=len)
        listing = self._build(document.url, record)
        return [listing] if listing else []

    def _build(self, url: str, record: dict) -> ParsedListing | None:
        match = _DETAIL_ID.search(url)
        external_id = str(record.get("vehicleId") or (match.group(1) if match else ""))
        if not external_id:
            return None

        listing = ParsedListing(
            source_id=self.source_id,
            external_id=external_id,
            canonical_url=url,
            asset_class="vehicle",
            asset_type="vehicle",
            asset_key=clean_text(record.get("collateralId")) or f"baanknet_vehicle:{external_id}",
            legal_basis=_legal_basis(record.get("typeOfAction")),
        )

        self._apply_vehicle(listing, record)
        self._apply_location(listing, record)
        self._apply_money(listing, record)
        self._apply_schedule(listing, record)
        self._apply_legal(listing, record)

        listing.raw_payload = {"vehicle": strip_personal_data(record)}
        self._score(listing)
        return listing

    # --- field groups -----------------------------------------------------

    @staticmethod
    def _apply_vehicle(listing: ParsedListing, record: dict) -> None:
        brand = clean_text(record.get("brand") or record.get("brandName"))
        model = clean_text(record.get("model") or record.get("modelName"))
        variant = clean_text(record.get("variant"))
        year = parse_date(record.get("registrationYear"))

        listing.asset_subtype = clean_text(
            record.get("vehicleType") or record.get("vehicleBodyType")
        )

        parts = [str(year.year)] if year else []
        parts += [p for p in (brand, model, variant) if p]
        listing.title = clean_text(" ".join(parts)) or "Vehicle"

        details = []
        for label, key in (
            ("Fuel", "fuelType"),
            ("Body", "vehicleBodyType"),
            ("Engine", "engineCapacity"),
            ("Odometer", "odometerReading"),
        ):
            value = clean_text(record.get(key))
            if value:
                suffix = (
                    " cc"
                    if key == "engineCapacity"
                    else (" km" if key == "odometerReading" else "")
                )
                details.append(f"{label}: {value}{suffix}")
        listing.description = "; ".join(details) or None

    @staticmethod
    def _apply_location(listing: ParsedListing, record: dict) -> None:
        # Where the vehicle physically is, not where its owner lives.
        listing.address = clean_text(record.get("parkingYardAddress"), max_length=500)
        listing.locality = title_case(record.get("repossessionLocality"))
        listing.city = title_case(record.get("repossessionCity"))
        listing.district = title_case(record.get("repossessionDistrict"))
        listing.state = title_case(record.get("repossessionState"))
        listing.pincode = normalise_pincode(record.get("repossessionPincode"))

    @staticmethod
    def _apply_money(listing: ParsedListing, record: dict) -> None:
        listing.reserve_price = parse_inr(
            record.get("reservePrice") or record.get("price") or record.get("sortPrice")
        )
        listing.emd_amount = parse_inr(record.get("emd"))
        listing.bid_increment = parse_inr(record.get("incrementPrice"))
        listing.outstanding_dues = parse_inr(record.get("npaAmount"))

        # Many vehicle records give an EMD percentage instead of an amount.
        if listing.emd_amount is None and listing.reserve_price is not None:
            percentage = record.get("emdPercentage")
            if isinstance(percentage, (int, float)) and 0 < percentage <= 100:
                listing.emd_amount = (
                    listing.reserve_price * Decimal(str(percentage)) / Decimal(100)
                ).quantize(Decimal("0.01"))
                listing.flag("emd_derived_from_percentage")

        if listing.reserve_price is not None and not is_plausible_price(listing.reserve_price):
            listing.flag("reserve_price_implausible")
            listing.reserve_price = None

    @staticmethod
    def _apply_schedule(listing: ParsedListing, record: dict) -> None:
        listing.auction_start_at = parse_iso_utc(
            record.get("auctionFrom") or record.get("auctionStartTime")
        )
        listing.auction_end_at = parse_iso_utc(
            record.get("auctionTo") or record.get("auctionEndTime")
        )
        listing.emd_deadline_at = parse_iso_utc(record.get("emdEnd") or record.get("emdEndTime"))
        listing.inspection_from = parse_iso_utc(record.get("inspectionStart"))
        listing.inspection_to = parse_iso_utc(record.get("inspectionEnd"))

        from auction_portal.sources.baanknet import BaanknetAdapter

        listing.status = BaanknetAdapter._status(listing.auction_start_at, listing.auction_end_at)

    @staticmethod
    def _apply_legal(listing: ParsedListing, record: dict) -> None:
        listing.bank_name = clean_text(record.get("bankName"))
        listing.branch_name = title_case(record.get("auctionBranch"))
        listing.npa_date = parse_date(record.get("npaDate"))

        declared = (clean_text(record.get("possessionType")) or "").lower()
        if "physical" in declared:
            listing.possession_type = "physical"
        elif "symbolic" in declared:
            listing.possession_type = "symbolic"
        else:
            listing.possession_type = "unknown"

        listing.authorised_officer_name = title_case(record.get("checkerName"))

    @staticmethod
    def _score(listing: ParsedListing) -> None:
        confidence = Decimal("1.00")

        if listing.reserve_price is None:
            listing.flag("missing_reserve_price")
            confidence -= Decimal("0.40")
        if listing.auction_start_at is None:
            listing.flag("auction_not_yet_scheduled")
            confidence -= Decimal("0.10")
        if not listing.state:
            listing.flag("missing_state")
            confidence -= Decimal("0.15")
        if not listing.city:
            listing.flag("missing_city")
            confidence -= Decimal("0.10")
        if not listing.title or listing.title == "Vehicle":
            listing.flag("missing_vehicle_identity")
            confidence -= Decimal("0.15")

        listing.confidence = max(Decimal("0.00"), confidence)


def _legal_basis(value: object) -> str:
    text = (clean_text(value) or "").lower()
    if "hypothecation" in text:
        return "contractual"
    if "drt" in text:
        return "drt"
    if "sarfaesi" in text:
        return "sarfaesi"
    return "contractual"
