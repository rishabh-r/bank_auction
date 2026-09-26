"""FastAPI application.

Server-rendered rather than a single-page app. Most traffic to a portal
like this arrives from people searching "SBI auction property Pune", so
pages that are complete HTML on first response - indexable, fast, working
without JavaScript - matter more than client-side interactivity.

A JSON API is exposed alongside for future clients.
"""

from datetime import UTC, date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Annotated
from urllib.parse import urlencode

from fastapi import Depends, FastAPI, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from auction_portal.db.models import Listing
from auction_portal.db.session import get_sessionmaker
from auction_portal.normalise.dates import to_ist
from auction_portal.normalise.money import format_inr
from auction_portal.search import SORT_LABELS, SearchQuery, SearchService

HERE = Path(__file__).parent
TEMPLATES = HERE / "templates"
STATIC = HERE / "static"

DISCLAIMER = (
    "Information is aggregated from publicly available sources and may be "
    "inaccurate or out of date. This is not an offer to sell. Always verify "
    "every detail against the bank's original notice before acting or "
    "committing any money."
)


def get_session():
    factory = get_sessionmaker()
    session = factory()
    try:
        yield session
    finally:
        session.close()


#: The current FastAPI idiom for dependencies: keeps the call out of the
#: argument default, which is both clearer and what linters expect.
SessionDep = Annotated[Session, Depends(get_session)]


def create_app() -> FastAPI:
    app = FastAPI(
        title="Auction Portal",
        description="Search bank auction properties across India.",
        version="0.1.0",
        docs_url="/api/docs",
        openapi_url="/api/openapi.json",
    )
    app.mount("/static", StaticFiles(directory=STATIC), name="static")
    templates = Jinja2Templates(directory=str(TEMPLATES))
    templates.env.filters["inr"] = format_inr
    templates.env.filters["ist"] = _format_ist
    templates.env.filters["day"] = _format_day
    templates.env.filters["human"] = _humanise

    # --- HTML pages -------------------------------------------------------

    @app.get("/", response_class=HTMLResponse)
    def home(
        request: Request,
        session: SessionDep,
        q: str | None = None,
        bank: str | None = None,
        state: str | None = None,
        city: str | None = None,
        asset_type: str | None = None,
        possession: str | None = None,
        status: str | None = None,
        min_price: str | None = None,
        max_price: str | None = None,
        sort: str = "auction_date",
        page: int = 1,
    ):
        service = SearchService(session)
        query = SearchQuery(
            text=q,
            bank=bank,
            state=state,
            city=city,
            asset_type=asset_type,
            possession=possession,
            status=status,
            min_price=_decimal(min_price),
            max_price=_decimal(max_price),
            sort=sort if sort in SORT_LABELS else "auction_date",
            page=page,
        )
        results = service.search(query)

        return templates.TemplateResponse(
            request,
            "search.html",
            {
                "results": results,
                "query": query,
                "sort_labels": SORT_LABELS,
                "totals": service.totals(),
                "disclaimer": DISCLAIMER,
                "params": _params(request),
                "now": datetime.now(UTC),
                **_url_helpers(request),
            },
        )

    @app.get("/listing/{listing_id}", response_class=HTMLResponse)
    def listing_detail(
        request: Request,
        listing_id: int,
        session: SessionDep,
    ):
        service = SearchService(session)
        listing = service.get(listing_id)
        if listing is None:
            return templates.TemplateResponse(
                request, "not_found.html", {"disclaimer": DISCLAIMER}, status_code=404
            )

        return templates.TemplateResponse(
            request,
            "detail.html",
            {
                "listing": listing,
                "nearby": service.nearby(listing),
                "disclaimer": DISCLAIMER,
                "now": datetime.now(UTC),
            },
        )

    # --- JSON API ---------------------------------------------------------

    @app.get("/api/listings")
    def api_listings(
        session: SessionDep,
        q: str | None = None,
        state: str | None = None,
        city: str | None = None,
        bank: str | None = None,
        asset_type: str | None = None,
        min_price: str | None = None,
        max_price: str | None = None,
        sort: str = "auction_date",
        page: int = 1,
        page_size: Annotated[int, Query(le=100)] = 20,
    ):
        service = SearchService(session)
        query = SearchQuery(
            text=q,
            state=state,
            city=city,
            bank=bank,
            asset_type=asset_type,
            min_price=_decimal(min_price),
            max_price=_decimal(max_price),
            sort=sort if sort in SORT_LABELS else "auction_date",
            page=page,
            page_size=page_size,
        )
        results = service.search(query, with_facets=False)
        return {
            "total": results.total,
            "page": results.page,
            "page_size": results.page_size,
            "total_pages": results.total_pages,
            "disclaimer": DISCLAIMER,
            "listings": [_serialise(listing) for listing in results.listings],
        }

    @app.get("/api/listings/{listing_id}")
    def api_listing(listing_id: int, session: SessionDep):
        listing = SearchService(session).get(listing_id)
        if listing is None:
            return JSONResponse({"error": "not found"}, status_code=404)
        return {**_serialise(listing), "disclaimer": DISCLAIMER}

    @app.get("/api/health")
    def health(session: SessionDep):
        totals = SearchService(session).totals()
        return {"status": "ok", **totals}

    # --- crawler directives ----------------------------------------------

    @app.get("/robots.txt", response_class=PlainTextResponse)
    def robots():
        # Listing pages carry no personal data, so they are indexable.
        # The API is not useful to a search engine.
        return "User-agent: *\nDisallow: /api/\nAllow: /\n"

    return app


# --- helpers --------------------------------------------------------------


def _serialise(listing: Listing) -> dict:
    """Public representation of a listing.

    Borrower and guarantor names are deliberately absent. They add nothing
    for a buyer and publishing someone's default is a real harm; see
    Part E of the project documentation.
    """
    return {
        "id": listing.id,
        "title": listing.title,
        "asset_type": listing.asset_type,
        "asset_subtype": listing.asset_subtype,
        "address": listing.address,
        "locality": listing.locality,
        "city": listing.city,
        "district": listing.district,
        "state": listing.state,
        "pincode": listing.pincode,
        "latitude": float(listing.latitude) if listing.latitude else None,
        "longitude": float(listing.longitude) if listing.longitude else None,
        "area_sqft": float(listing.area_sqft) if listing.area_sqft else None,
        "reserve_price": float(listing.reserve_price) if listing.reserve_price else None,
        "reserve_price_display": format_inr(listing.reserve_price),
        "emd_amount": float(listing.emd_amount) if listing.emd_amount else None,
        "emd_display": format_inr(listing.emd_amount),
        "auction_start_at": _iso(listing.auction_start_at),
        "auction_end_at": _iso(listing.auction_end_at),
        "emd_deadline_at": _iso(listing.emd_deadline_at),
        "inspection_from": _iso(listing.inspection_from),
        "inspection_to": _iso(listing.inspection_to),
        "bank_name": listing.bank_name,
        "branch_name": listing.branch_name,
        "possession_type": listing.possession_type,
        "legal_basis": listing.legal_basis,
        "status": listing.status,
        "confidence": float(listing.confidence),
        "source": {
            "source_id": listing.source_id,
            "notice_url": listing.canonical_url,
            "first_seen_at": _iso(listing.first_seen_at),
            "last_verified_at": _iso(listing.last_verified_at),
        },
    }


def _params(request: Request) -> dict[str, str]:
    return {k: v for k, v in request.query_params.items() if k != "page" and v}


def _url_helpers(request: Request) -> dict:
    """Query-string builders for filter links.

    Toggling a filter has to preserve every other filter, and always reset
    to page 1 - otherwise a user narrowing their search lands on an empty
    page 7.
    """
    current = dict(request.query_params)

    def build_query(name: str, value: str | None) -> str:
        params = {k: v for k, v in current.items() if k != "page"}
        if value:
            params[name] = value
        else:
            params.pop(name, None)
        return urlencode({k: v for k, v in params.items() if v})

    def query_value(name: str) -> str | None:
        return current.get(name)

    def page_url(page: int) -> str:
        params = {k: v for k, v in current.items() if k != "page" and v}
        params["page"] = str(page)
        return urlencode(params)

    return {
        "build_query": build_query,
        "query_value": query_value,
        "page_url": page_url,
    }


def _decimal(value: str | None) -> Decimal | None:
    if not value:
        return None
    try:
        return Decimal(value.replace(",", "").strip())
    except (InvalidOperation, AttributeError):
        return None


def _iso(moment: datetime | None) -> str | None:
    return moment.isoformat() if moment else None


def _format_ist(moment: datetime | None) -> str:
    local = to_ist(moment)
    return local.strftime("%d %b %Y, %H:%M") if local else "Not scheduled"


def _format_day(value: date | datetime | None) -> str:
    if value is None:
        return "-"
    if isinstance(value, datetime):
        value = to_ist(value).date()
    return value.strftime("%d %b %Y")


def _humanise(moment: datetime | None) -> str:
    """'in 32 days' / '2 hours ago' - freshness a reader can judge."""
    if moment is None:
        return "unknown"
    delta = moment - datetime.now(UTC)
    seconds = delta.total_seconds()
    future = seconds > 0
    seconds = abs(seconds)

    if seconds < 3600:
        amount, unit = int(seconds // 60), "minute"
    elif seconds < 86400:
        amount, unit = int(seconds // 3600), "hour"
    else:
        amount, unit = int(seconds // 86400), "day"

    amount = max(amount, 1)
    plural = "" if amount == 1 else "s"
    return f"in {amount} {unit}{plural}" if future else f"{amount} {unit}{plural} ago"


app = create_app()
