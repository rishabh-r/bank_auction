# Centralised Bank Auction Portal for India

## Domain Research, Regulatory Framework and Production Build Plan

---

## Reality check first: half of the idea already exists, for free

On **3 January 2025** the Department of Financial Services launched **BAANKNET** (baanknet.com), a revamp of the older e-BKray / IBAPI portals. All **12 public sector banks** — SBI, PNB, Bank of Baroda, Canara, Union Bank and others — plus the **IBBI** now list their auction properties there, with search by state / city / locality, property type, price range, bank filter, map view, reserve price, auction dates, EMD, eKYC and integrated bidding. That is precisely the portal described in the original brief, for public sector banks.

This is good news, not bad news, and here is why: **BAANKNET covers only the 12 public sector banks.** The banks named first in the brief — ICICI, HDFC, Axis — are private and are *not* on it. Their listings are scattered across `bankeauctions.com` (C1 India), `auctiontiger.net` (e-Procurement Technologies), `mstcecommerce.com`, each bank's own PDF notice page, and newspaper advertisements. Add roughly 9,000+ NBFCs, ARCs, cooperative banks, DRT sales and IBBI liquidations, and there is a very real, very messy gap.

**Strategic conclusion:** build the aggregator, but position it as *"every distressed asset in India in one search"*, not *"bank auctions"*. Do not compete with BAANKNET on public sector banks — index it, and go and get everything it does not cover.

---

# Part A — What actually happens when someone stops paying

## A.1 The vocabulary you need

When a bank lends against an asset, that is a **secured loan**. The legal grip the bank has on the asset is a **security interest**, created in one of three ways:

- **Mortgage** — for immovable property (home loan, loan against property). Usually an *equitable mortgage*, created by depositing the original title deeds with the bank.
- **Hypothecation** — for movable assets the borrower keeps using (car, machinery, stock). The borrower drives the car; the bank's charge is noted on the RC.
- **Pledge** — the bank physically holds the asset (gold loan). Note: gold loans are *pledges*, and pledges are explicitly outside SARFAESI — banks auction pledged gold under the Indian Contract Act, not SARFAESI.

The borrower is the **mortgagor**; the bank is the **secured creditor**; the specific bank officer empowered to run enforcement is the **Authorised Officer**, whose name and phone number appear on every sale notice. This is a field worth capturing.

## A.2 The default timeline

Under the **RBI (Commercial Banks – Income Recognition, Asset Classification and Provisioning) Directions, 2025** (current version updated 1 July 2026), the clock is mechanical and runs at day-end:

| Stage | Trigger |
|---|---|
| Overdue | Day-end of the due date, payment not received |
| SMA-0 | Overdue up to 30 days |
| SMA-1 | Overdue more than 30 and up to 60 days |
| SMA-2 | Overdue more than 60 and up to 90 days |
| **NPA** | Overdue **more than 90 days** |

RBI's own illustration: due date 31 March, then SMA-1 on 30 April, SMA-2 on 30 May, and **NPA on 29 June**. Roughly three missed EMIs.

Once an account is an NPA it is further graded **substandard**, then **doubtful**, then **loss** as time passes. This grading drives how much capital the bank must provision against the loan — and that provisioning pressure is exactly *why* banks push to auction rather than wait.

## A.3 Enforcement under SARFAESI

The **Securitisation and Reconstruction of Financial Assets and Enforcement of Security Interest Act, 2002** ("SARFAESI") is the reason banks can seize and sell a house *without going to court first*. That is its entire purpose. The procedural detail sits in the **Security Interest (Enforcement) Rules, 2002**.

```
   Loan goes NPA (90+ days overdue)
                |
                v
   Section 13(2) Demand Notice  --  pay full dues within 60 days
                |
                +--> Borrower objects under Sec 13(3A)?
                |         -> Bank must reply with reasons within 15 days
                v
   60 days expire, still unpaid
                |
                v
   Section 13(4): Bank takes possession
                |
                +--> SYMBOLIC   : paper exercise, notice pasted on door
                +--> PHYSICAL   : usually needs Sec 14 order from
                                  District Magistrate / Chief Metro Magistrate
                |
                v
   Possession Notice published in 2 newspapers within 7 days   [Rule 8(1)-(2)]
                |
                v
   Valuation by approved valuer; Reserve Price fixed           [Rule 8(5)]
                |
                v
   Sale Notice: 30 days to borrower + newspaper + website      [Rule 8(6)]
                |
                v
   E-Auction, minimum 30 days after the notice                 [Rule 9(1)]
                |
                +--> No bid at/above Reserve Price
                |         -> Failed auction, re-auction with
                |            Reserve Price often cut 10-25%  (loops back)
                v
   Highest bid accepted
                |
                v
   25% of sale price deposited immediately                     [Rule 9(3)]
                |
                v
   Balance 75% within 15 days                                  [Rule 9(4)]
                |
                v
   Sale Certificate issued, possession delivered               [Rule 9(6)]
```

### Step by step, in plain terms

**1. Section 13(2) demand notice.** Once the account is an NPA, the bank sends a notice demanding the entire outstanding amount — not just the missed EMIs, the whole loan accelerates — within **60 days**. Every sale notice you scrape will reference this notice and its date.

**2. Section 13(3A) representation.** The borrower can object. The bank must consider the objection and, if rejecting it, communicate reasons within 15 days. This does not stop the clock; it is a procedural safeguard that borrowers frequently rely on later to challenge the sale.

**3. Section 13(4) possession.** After 60 days, the bank can take possession.

- **Symbolic possession** is a paper exercise — the Authorised Officer visits, pastes a notice, and draws up a panchnama.
- **Physical possession** means actually emptying and locking the property. Because the bank cannot use force itself, it usually applies under **Section 14** to the District Magistrate or Chief Metropolitan Magistrate, who orders police assistance. This is where most of the delay lives; Section 14 applications can sit for months.

> **Why this matters for the product:** BAANKNET already lets users filter by **Possession Type: Physical / Symbolic / Other**, and buyers care enormously. A symbolically-possessed flat may still have the defaulting family living in it, and the buyer inherits the eviction fight.

**4. Rule 8(1)–(2) publicity.** Within 7 days of taking possession, the possession notice must be published in two leading newspapers in the locality, one of them in the vernacular language. This is the *first* public trace of an asset — often months before the auction. Catching these early is a genuine competitive edge.

**5. Rule 8(5) valuation and reserve price.** The Authorised Officer obtains a valuation from an approved valuer and, in consultation with the bank, fixes the **Reserve Price** — the floor below which the property will not be sold. Rule 8(5) permits sale by quotations, public tender, **public auction including e-auction**, or private treaty. In practice it is almost always e-auction.

**6. Rule 8(6) and Rule 9(1) — the 30-day rule.** The borrower gets a 30-day sale notice, and no sale may take place in the first instance until 30 days after that notice.

The Supreme Court settled the mechanics in **M. Rajendran v. KPK Oils and Proteins (2025 INSC 1137, 22 September 2025)**: it is *one composite notice*, not two, and the 30 days run from whichever event happens last — service on the borrower, newspaper publication, affixation, or uploading to the website. Same-day service and publication is permissible as long as the 30-day gap to the auction is maintained.

**7. Section 13(8) — right of redemption.** Until 2016, a borrower could pay up and reclaim the property right up to the moment of sale. The 2016 amendment moved that deadline much earlier: redemption dies **on publication of the sale notice**. In *M. Rajendran*, the Court held that "publication" means the completion of service / publication / affixation / uploading, so the right is extinguished at the *end of the 30-day Rule 9(1) window*. The Court also flagged that Section 13(8) and Rules 8–9 are now inconsistent and urged the government to amend them — so watch for a rule change here.

**8. Rule 9(3)–(4) payment.** The winner pays **25% of the sale price immediately** (inclusive of EMD) and the **balance 75% within 15 days**, extendable only by written agreement between bank, borrower and purchaser. Missing the deadline means the deposit is forfeited and the property is re-auctioned. The Supreme Court reiterated this in a June 2026 judgment (2026 INSC 633).

**9. Rule 9(6) Sale Certificate** is issued, followed by delivery of possession.

**Appeals.** The borrower can challenge enforcement before the **Debts Recovery Tribunal (DRT) under Section 17** within 45 days, and appeal onward to the **DRAT under Section 18** — but only after depositing 50% of the debt (reducible to 25%). Civil courts are barred under Section 34. This is why a listed auction can vanish overnight on a DRT stay order, and why the system must model that state.

## A.4 What SARFAESI does *not* cover

Section 31 carves out, broadly: pledges (gold loans), liens, aircraft and ships, hire-purchase or lease arrangements where no security interest exists, unpaid seller's rights, **agricultural land**, security for a financial asset not exceeding ₹1 lakh, and cases where the amount still due is less than 20% of principal plus interest.

*Verify the exact current thresholds with a lawyer before encoding them anywhere.*

## A.5 Vehicles work completely differently

Vehicle hypothecation *is* a security interest, so SARFAESI technically applies. But banks almost never use it for a ₹6 lakh car — the Section 14 magistrate route costs more than the car is worth. Instead they repossess under the **contractual repossession clause**, governed by RBI's Fair Practices Code and conduct rules.

The current framework is the **RBI (Commercial Banks – Responsible Business Conduct) Directions, 2025**, with parallel NBFC Directions and a comprehensive 2026 recovery-agent framework applying to NBFCs from **1 January 2027**. The substance has been stable since the 2008/2009 circulars. The loan agreement must contain a legally valid, clearly-disclosed possession clause specifying:

1. Notice period before taking possession
2. Circumstances under which the notice period can be waived
3. The procedure for taking possession of the security
4. **A final chance for the borrower to repay before sale / auction**
5. The procedure for returning possession to the borrower
6. The procedure for sale / auction of the property

Banks remain fully liable for outsourced recovery agents, who require antecedent verification, training, identification and a code of conduct. Force, intimidation, harassment and public humiliation are prohibited, and courts have repeatedly struck down forcible seizure and arbitrary notice-waiver clauses.

**Practically:** repossession, then a **pre-sale notice** giving a last chance to clear dues, then sale — usually at a **yard auction** run by specialists (Shriram, Mahindra First Choice, CarTradeExchange, and B2B salvage platforms) rather than a public SARFAESI e-auction. Surplus goes back to the borrower; a shortfall remains recoverable as unsecured debt.

Vehicle auction data is therefore **much harder to source** than property data and is largely dealer-only. Treat it as phase 3, not phase 1.

---

# Part B — Where the auction data actually lives

This is the most valuable map in this document. There are six distinct source types.

**1. BAANKNET** (`baanknet.com`) — all 12 public sector banks plus IBBI. Browsable without login. Structured HTML, filters, an Auction ID, and attached notice documents. The single richest source.

**2. E-auction service providers.** This is the key realisation: private banks do not build auction technology, they outsource it. A handful of providers carry most of the market.

- **C1 India** — `bankeauctions.com` (HDFC, Axis and many others), plus the consumer front-end `eauctionsindia.com`
- **e-Procurement Technologies** — `auctiontiger.net`, with per-bank subdomains such as `hdfcbank.auctiontiger.net`
- **MSTC** — `mstcecommerce.com`
- Smaller players: Prov Infosolutions, Antares, NexxaGlobal

Scraping six providers yields far more coverage than scraping sixty bank websites.

**3. Bank websites.** Every bank publishes sale notices as PDFs — `hdfc.bank.in/.../auction-notices/`, `axis.bank.in/docs/.../auction-notices/`, ICICI's notices section. Often the *earliest* published copy, and the authoritative one. Mostly unstructured PDFs.

**4. Newspapers.** Rule 8 mandates publication in two newspapers, one vernacular. Notices appear in Business Standard, Financial Express, Sakal, Eenadu, Dinamalar and hundreds of regional dailies — including possession notices that never reach any website. Highest coverage, hardest to ingest, and the place to eventually differentiate.

**5. DRT / DRAT.** Recovery officers auction attached properties via `drt.gov.in` tribunal sites and MSTC / e-auction platforms. Separate legal track, different document formats.

**6. IBBI / IBC liquidation.** Liquidators publish Form G and asset sale notices on `ibbi.gov.in`. Well-structured, genuinely public, and explicitly intended for wide circulation. **This is the best place to start** — it is the friendliest source both legally and technically.

---

# Part C — What a real auction notice looks like (and why this is hard)

Below is a genuine extract from the HDFC Bank sale notice dated 15 January 2026, after running it through a normal PDF text extractor:

```
| HDFC Bank Ltd., Delhi M/s Colocube Technologies Private Limited | Mortgagor /
Guarantor: Suresh Kumar Nabanita Chanda Guarantor: Mr. Kumar | Mr. Item No.1
Residential Property with roof rights, Part of Property No. 72, admeasuring
242.33 square yards, situated at Krishna Mani Sarva Hitkari CHBS Ltd, known as
Kailash Hills, East of Kailash, New Delhi | Rs.3,38,94,383.15/- viz Entire 3rd
Floor Date of Demand Notice: 28-Jul-2022 Dues as on 27-Jul-2022 ... | 27/01/2026
03:00 04:00 PM with further the costs and of full and final | Rs.3,37,55,000/-
PM to Rs.33,75,500/- Rs.1,00,000/- | 05/02/2026 10:30 11:30 AM | 03/02/2026
4:00 PM AM to | up to Mr Anirudh Bhargav Mobile: 8802112088 |
```

Look carefully at what happened:

- `Rs.3,37,55,000/- PM to Rs.33,75,500/- Rs.1,00,000/-` is actually **three separate columns** — Reserve Price ₹3.3755 crore, EMD ₹33,75,500, Bid Increment ₹1,00,000 — plus the fragment `PM to` that leaked in from the adjacent inspection-time column.
- The words "Entire 3rd Floor" belong to the property description but landed inside the dues column.
- Text is interleaved across cell boundaries because the PDF stores glyph positions, not a table.

This single example tells you everything about the engineering problem. **Naive PDF text extraction will silently produce a listing with the wrong reserve price**, and a wrong reserve price on a ₹3 crore property is the kind of error that ends a business. Layout-aware extraction and confidence scoring are not optional polish — they are the core product.

Note also that auctions come in **batches**. One PDF, one Authorised Officer, one newspaper publication, but **four distinct properties** (Item No. 1–4), each with its own reserve price, EMD, inspection date and auction slot. The parser must emit N listings from 1 document. Items 3 and 4 in that notice share one borrower and one dues figure across two properties, and item 4's reserve price (₹3,50,00,000) and EMD (₹35,00,000) were flung into a completely different part of the page from its description. There is no clean rule that fixes this; spatial reasoning is required.

---

# Part D — How to build it

## D.1 The shape of the system

```
  SOURCES                    PIPELINE                        SERVING
  -------                    --------                        -------

  BAANKNET        \
  bankeauctions    \
  auctiontiger      >---->  [ FETCH LAYER ]
  MSTC             /        Scrapy + Playwright
  Bank PDF pages  /         polite, rate-limited
  IBBI Form G    /                  |
  Newspapers    /                   v
                          [ RAW STORE  (S3 / MinIO) ]
                          immutable HTML + PDF bytes
                                    |
                                    v
                          [ PARSE LAYER ]
                          pdfplumber / OCR /
                          layout model / LLM
                                    |
                                    v
                          [ NORMALISE ]
                          money, dates, geo, taxonomy
                                    |
                                    v
                          [ DEDUP + ENTITY RESOLUTION ]
                                    |
                                    v
                          < confidence score? >
                            /              \
                    high  /                 \  low
                         v                   v
              [ POSTGRES ]            [ HUMAN REVIEW QUEUE ]
              canonical listings   -->  corrections feed back
                    |    |
                    |    +---------> [ SEARCH INDEX ]  Typesense / OpenSearch
                    |                        |
                    +-----> [ FASTAPI ] <----+
                                 |
                    +------------+------------+
                    v                         v
            [ NEXT.JS PORTAL ]        [ ALERTS: email / WhatsApp ]
```

**The non-negotiable principle: never overwrite raw data.** Every fetch is stored immutably with its URL, timestamp and content hash. When your parser has a bug — and it will — you reparse history instead of re-crawling and losing evidence. This also gives you the audit trail you need if a bank ever disputes what you displayed.

## D.2 The data model

This is worth getting right on day one, because everything downstream depends on it.

```sql
-- Every fetch, immutable, never updated
CREATE TABLE source_documents (
    id              BIGSERIAL PRIMARY KEY,
    source_id       TEXT NOT NULL,          -- 'baanknet', 'hdfc_web', 'c1india'
    source_url      TEXT NOT NULL,
    fetched_at      TIMESTAMPTZ NOT NULL,
    content_sha256  TEXT NOT NULL,          -- change detection
    storage_key     TEXT NOT NULL,          -- S3 path to raw bytes
    mime_type       TEXT,
    http_status     INT,
    UNIQUE (source_url, content_sha256)     -- unchanged page = no new row
);

-- One row per (document, property) pair. A 4-property notice gives 4 rows.
CREATE TABLE extracted_listings (
    id                  BIGSERIAL PRIMARY KEY,
    source_document_id  BIGINT REFERENCES source_documents(id),
    item_index          INT,                -- "Item No. 2" in the notice
    raw_payload         JSONB NOT NULL,     -- whatever the extractor emitted
    extractor_version   TEXT NOT NULL,      -- to reprocess when you improve it
    confidence          NUMERIC(3,2),
    review_status       TEXT DEFAULT 'pending'
);

-- The deduplicated, user-facing entity
CREATE TABLE listings (
    id                  UUID PRIMARY KEY,
    bank_id             INT REFERENCES banks(id),
    branch_name         TEXT,
    asset_type          TEXT NOT NULL,      -- residential|commercial|industrial|
                                            -- agricultural|vehicle|plant_machinery|gold
    asset_subtype       TEXT,               -- flat|plot|villa|shop|warehouse
    title               TEXT,
    description         TEXT,
    address_raw         TEXT,
    state               TEXT, district TEXT, city TEXT, locality TEXT, pincode TEXT,
    latitude            NUMERIC(9,6), longitude NUMERIC(9,6),
    geocode_confidence  NUMERIC(3,2),
    area_value          NUMERIC, area_unit TEXT,  -- sqft|sqm|sqyd|acre|guntha|bigha|cent
    area_sqft_norm      NUMERIC,            -- always populate for range filtering
    reserve_price       NUMERIC(18,2),
    emd_amount          NUMERIC(18,2),
    bid_increment       NUMERIC(18,2),
    outstanding_dues    NUMERIC(18,2),
    auction_start_at    TIMESTAMPTZ,
    auction_end_at      TIMESTAMPTZ,
    bid_submission_deadline TIMESTAMPTZ,
    inspection_from     TIMESTAMPTZ, inspection_to TIMESTAMPTZ,
    possession_type     TEXT,               -- physical|symbolic|unknown
    auction_platform    TEXT,               -- bankeauctions|auctiontiger|baanknet|mstc
    platform_auction_id TEXT,
    demand_notice_date  DATE,
    authorised_officer_name  TEXT,
    authorised_officer_phone TEXT,
    status              TEXT NOT NULL,      -- upcoming|live|closed|cancelled|
                                            -- postponed|sold|unsold|withdrawn|stayed
    legal_basis         TEXT,               -- sarfaesi|drt|ibc_liquidation|contractual
    round_number        INT DEFAULT 1,      -- 2nd/3rd auction = discounted RP
    first_seen_at       TIMESTAMPTZ, last_verified_at TIMESTAMPTZ,
    canonical_source_url TEXT NOT NULL,     -- ALWAYS link back to the original
    data_quality_flags  TEXT[]
);

-- Full history: this is your moat
CREATE TABLE listing_revisions (
    id           BIGSERIAL PRIMARY KEY,
    listing_id   UUID REFERENCES listings(id),
    changed_at   TIMESTAMPTZ NOT NULL,
    field_name   TEXT NOT NULL,
    old_value    TEXT, new_value TEXT,
    source_document_id BIGINT REFERENCES source_documents(id)
);
```

Three design decisions worth explaining:

**`area_sqft_norm` alongside the raw area.** Indian notices use square yards, square metres, square feet, acres, cents, gunthas, bighas, ares and kanals — sometimes two units in one line. Store what the notice said *and* a normalised value, because "show me 800–1200 sqft flats" is a filter users will absolutely want.

**`round_number`.** When a first auction fails to attract a bid at reserve price, banks re-auction at a reduced reserve. A property on its third round at 40% below original valuation is the single most interesting signal a distressed-asset buyer can get. Nobody surfaces this well. You should.

**`listing_revisions`.** Every price cut, date postponement and cancellation, permanently. Within a year this becomes a dataset — *"properties in Pune re-auction on average 1.8 times, at a mean 17% discount"* — that nobody else has and that you can sell.

## D.3 Ingestion: crawling, politely

**Framework.** Use **Scrapy** for the bulk of it: scheduling, retries, throttling, URL deduplication and a pipeline architecture all come free. Add **Playwright** (via `scrapy-playwright`) only for pages that genuinely require JavaScript — it is roughly 50× more expensive per page.

**Always look for the hidden API first.** Modern portals like BAANKNET are React front-ends talking to a JSON backend. Open DevTools, go to Network, filter XHR, apply a search filter and watch. If you find `POST /api/property/search` returning clean JSON, you have skipped the entire HTML-parsing problem. This is the highest-leverage 30 minutes you will spend on the project.

**One adapter per source, behind a common interface:**

```python
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime


@dataclass
class RawDocument:
    source_url: str
    content: bytes
    mime_type: str
    fetched_at: datetime
    metadata: dict  # anything the listing page already told you


class SourceAdapter(ABC):
    source_id: str
    politeness_delay: float = 2.0
    respects_robots: bool = True

    @abstractmethod
    def discover(self) -> list[str]:
        """Return URLs of listing/notice pages to fetch this run."""

    @abstractmethod
    def fetch(self, url: str) -> RawDocument: ...

    @abstractmethod
    def extract(self, doc: RawDocument) -> list[dict]:
        """One dict per property. A 4-property notice returns 4 dicts."""
```

When a bank redesigns its site — and one will, every few months — you fix one adapter, not the pipeline.

**Politeness is a legal and operational requirement, not a courtesy.** Concretely:

- Honour `robots.txt`
- Set a real `User-Agent` identifying you with a contact URL, e.g. `AuctionPortalBot/1.0 (+https://yoursite.in/bot; crawler@yoursite.in)`
- One concurrent request per domain, with a 2–5 second delay
- Crawl at night
- Exponential backoff on HTTP 429 / 503
- **Never** touch anything behind a login or CAPTCHA
- Cap total requests per domain per day

A crawler that looks like a careful researcher gets ignored. One that looks like a denial-of-service attack gets IP-banned and a legal notice.

**Scheduling.** Start with **cron + Celery**. Move to **Prefect** or **Airflow** when you have more than roughly 15 sources and need dependency graphs, backfills and a retry UI. Do not start with Airflow — it is a great deal of machinery for four scrapers.

Cadence by source, driven by how fast the data decays:

| Source | Frequency | Why |
|---|---|---|
| BAANKNET, C1, AuctionTiger listings | Every 6 hours | Live status changes, cancellations |
| Listings auctioning within 7 days | Hourly | Postponements land late and matter most |
| Bank notice PDF index pages | Daily | New notices drop in batches |
| IBBI Form G | Daily | Predictable |
| Full re-verification sweep | Weekly | Catch silent edits |

## D.4 Extraction: the hard part

Use a **cascade**, cheapest first, escalating only when needed. Running an LLM over every document is slow and expensive; running regex over everything is wrong. The cascade gives you both.

**Tier 0 — structured source.** JSON API or clean HTML table. Deterministic parsing. Confidence 0.95+. Aim to get 60–70% of volume here.

**Tier 1 — digital PDF, layout-aware.** Use **`pdfplumber`** — and critically, its `extract_table()` with explicit strategies, not `extract_text()`. `extract_text()` is what produced the mangled HDFC output in Part C.

```python
import pdfplumber

with pdfplumber.open(path) as pdf:
    for page in pdf.pages:
        tables = page.extract_tables(
            {
                "vertical_strategy": "lines",  # use ruled lines, not whitespace
                "horizontal_strategy": "lines",
                "intersection_tolerance": 5,
            }
        )
        # Fall back to word positions when the PDF has no ruling lines
        if not tables:
            words = page.extract_words(keep_blank_chars=False, use_text_flow=False)
            # cluster by x0 to recover columns
```

Where ruling lines exist, this works well. Where the notice uses a borderless layout, cluster words by x-coordinate to infer columns yourself.

**Tier 2 — scanned PDF, OCR.** Many regional-branch notices are photocopies scanned to PDF. Detect this by extracting text and finding almost none (under roughly 100 characters per page). Then OCR. Options, cheapest to best:

- **Tesseract** — free, needs preprocessing (deskew, denoise, binarise via OpenCV), mediocre on tables
- **PaddleOCR / Surya** — free, open-source, notably better on tables and on Indic scripts
- **Google Document AI**, **AWS Textract**, **Azure Document Intelligence** — paid (roughly ₹1–8 per page) and dramatically better, with real table structure output

**Recommendation: start with a cloud Document AI service.** At likely volumes (a few thousand pages per month) it costs a few thousand rupees and saves weeks. Optimise to self-hosted PaddleOCR once you know the volume and can measure the accuracy trade-off.

Vernacular OCR matters: Rule 8 *requires* one vernacular newspaper, so you will encounter Hindi, Marathi, Tamil, Telugu, Kannada, Bengali and Gujarati. Tesseract's Indic models are weak; PaddleOCR and the cloud services are markedly better.

**Tier 3 — LLM structured extraction.** For anything the deterministic tiers cannot handle confidently. Send the layout-preserved text (with coordinates where available) to an LLM constrained to a JSON schema:

```python
from pydantic import BaseModel, Field
from typing import Literal


class ExtractedProperty(BaseModel):
    item_number: str | None = Field(description="e.g. 'Item No. 1'")
    borrower_name: str | None
    property_description: str
    state: str | None
    city: str | None
    reserve_price_inr: float | None = Field(
        description="Reserve/floor price in rupees. NOT the EMD, NOT the "
        "outstanding dues. If ambiguous, return null."
    )
    emd_inr: float | None = Field(
        description="Earnest Money Deposit, typically 10% of reserve price."
    )
    bid_increment_inr: float | None
    auction_datetime_ist: str | None
    possession_type: Literal["physical", "symbolic", "unknown"]
    extraction_notes: str = Field(description="Anything ambiguous or that you were unsure about.")
```

Three rules make this reliable:

1. **Make `null` always allowed and explicitly encouraged.** An LLM that guesses a reserve price is far worse than one that abstains — the abstention goes to a human, the guess goes to production.

2. **Validate with business rules, not just the schema.** EMD is conventionally around 10% of reserve price; if the extracted ratio falls outside 5–20%, flag it. In the HDFC example, ₹33,75,500 ÷ ₹3,37,55,000 = exactly 10.0% — a clean confirmation that the columns were split correctly. That one check would have caught the mangled parse. Similarly: the auction date must be at least 30 days after the sale notice date (Rule 9(1)), and reserve price is almost always less than outstanding dues.

3. **Run the two best candidates and compare.** Where the deterministic parse and the LLM parse agree on reserve price, confidence is high and the listing auto-publishes. Where they disagree, it goes to human review. This consensus check is cheap and catches most catastrophic errors.

**Budget for human review from day one.** No extraction pipeline hits 100%. A realistic target is 85–92% auto-published with 8–15% flagged. One person reviewing a well-designed queue — PDF rendered on the left, editable extracted fields on the right, keyboard shortcuts — handles 200–400 listings a day. Every correction becomes training data; after six months you will have thousands of verified pairs to fine-tune on. This internal review tool is as important as the public site, and beginners always underbuild it.

## D.5 Normalisation

Indian data has specific gremlins.

**Money.** `Rs.3,37,55,000/-`, `₹ 3.3755 Cr`, `Rs. 337.55 Lakhs`, `INR 33755000`. Handle Indian digit grouping (2,2,3 — not 3,3,3), the lakh/crore multipliers, `/-` suffixes, and Devanagari numerals. Store as `NUMERIC`, never float.

**Dates.** `27/01/2026` is DD/MM, not MM/DD — a genuine hazard, since both parse successfully. Also `28-Jul-2022`, `15.01.2026`, and `05/02/2026 10:30 AM to 11:30 AM` (a range in one cell). Always store `TIMESTAMPTZ` in **Asia/Kolkata**.

**Geography.** The hardest one. Notices give free text like *"Krishna Mani Sarva Hitkari CHBS Ltd, known as Kailash Hills, East of Kailash, New Delhi"* — no pincode, a society name, a colloquial locality. Pipeline:

1. Regex out any 6-digit pincode
2. Look it up in the **India Post pincode dataset** (free; gives district and state, and is the most reliable anchor available)
3. Fuzzy-match city against a canonical list from **LGD (Local Government Directory)** codes
4. Geocode the remainder

For geocoding, **Nominatim / OpenStreetMap** is free but weak on Indian addresses; **MapmyIndia / Mappls** is meaningfully better on Indian data and worth the cost. Always store `geocode_confidence`, and never show a map pin below your threshold — a wrongly-placed ₹3 crore property is worse than no pin.

Also handle renames (Bangalore / Bengaluru, Gurgaon / Gurugram), and build a **locality alias table** rather than trying to solve it in code.

**Taxonomy.** Map each bank's vocabulary to your own. "Flat", "Apartment", "Residential Flat", "Dwelling Unit" all become `residential/flat`. Maintain this as a database table with an admin UI, not a hardcoded dictionary — you will edit it weekly.

## D.6 Deduplication

The same property reaches you through BAANKNET, the bank's PDF, `bankeauctions.com`, `eauctionsindia.com` and a newspaper, with different wording each time. Worse, the same property genuinely reappears months later as a re-auction — and that is *not* a duplicate, it is a new round of the same asset.

**Stage 1 — blocking.** Do not compare every pair; with 100,000 listings that is 5 billion comparisons. Generate cheap keys and only compare within a block:

- `(bank_id, platform_auction_id)` — exact match, an instant win when present
- `(state, city, round(reserve_price, -5))`
- MinHash / LSH over the normalised property description
- `(pincode, round(area_sqft_norm, -2))`

**Stage 2 — scoring within blocks.** Weighted similarity over: reserve price (an exact match is a very strong signal — these are odd numbers like ₹3,37,55,000 that do not collide by chance), EMD, normalised address, borrower name (fuzzy, via `rapidfuzz`), auction date, area, and cosine similarity of sentence embeddings of the description (`sentence-transformers` plus **pgvector**, keeping everything in Postgres). Above 0.85, auto-merge; 0.65–0.85, human review; below that, treat as distinct.

For the re-auction case, the discriminator is the auction date: same property fingerprint, auction date more than roughly 30 days later, typically a lower reserve price — that is a new `round_number` on the existing asset, not a duplicate listing.

**Source precedence when merging.** When sources conflict, trust in this order: the bank's own PDF notice, then BAANKNET, then the official e-auction platform, then third-party aggregators. Keep every variant in `extracted_listings` so you can always show provenance and explain where a number came from.

Useful libraries: **`rapidfuzz`** (string distance), **`splink`** or **`dedupe`** (probabilistic record linkage), **`datasketch`** (MinHash / LSH).

## D.7 Keeping it fresh

Statuses matter more than you would think. A user who drives to an inspection for a cancelled auction never comes back.

- **Content hashing.** Same URL plus same SHA-256 means skip entirely. Cheap, and it cuts your processing bill by around 90%.
- **Corrigenda.** Banks publish "Corrigendum to Sale Notice dated X" changing dates or prices. Detect the word and link it to the parent notice.
- **Disappearance is not cancellation.** If a listing vanishes from a source, do not delete it. Mark `last_verified_at` as stale and, after N consecutive misses, set `status = 'unknown'`. Sources have outages.
- **Post-auction status.** After the auction date passes, flip to `closed` and try to determine `sold` or `unsold`. BAANKNET and some platforms publish results; often you will infer `unsold` from the property reappearing in a later notice. Sold prices are the most commercially valuable data you can accumulate.
- **Show the user your own freshness.** *"Last verified 2 hours ago · View original notice"* builds more trust than any amount of design polish.

## D.8 Serving

**Search.** Postgres full-text search is genuinely fine up to roughly 50,000 listings and saves you a service. Beyond that, or when you want typo tolerance and fast faceting, move to **Typesense** (easiest, great faceting, low RAM) or **Meilisearch**. Reach for **OpenSearch / Elasticsearch** only if you need heavy analytics — it is a lot of operational weight for a small team.

The requested facets map to index fields directly: bank, asset type, state, city, price range, auction date range, possession type, platform. Add these that users will want but did not ask for: **days until auction**, **auction round number**, **price versus locality median**, and **new since your last visit**.

**Backend.** **FastAPI** (Python). Keeping the API in the same language as the scrapers means one set of models, one test suite and one deployment story. **Django** is a reasonable alternative if you want the free admin panel for your review queue — genuinely worth considering given how much admin UI you will need.

**Frontend.** **Next.js** with server-side rendering. SSR matters commercially here: people search *"SBI auction property Pune"* on Google, and SSR plus structured data markup is how you capture that traffic. This will be your main acquisition channel.

**Alerts.** This is your retention mechanism and likely your revenue. Saved searches trigger email or WhatsApp when a matching listing appears or a reserve price drops. Use Celery Beat to evaluate saved searches against new listings. The WhatsApp Business API has real per-message costs — budget for it.

## D.9 Infrastructure

Do not over-engineer. This runs comfortably on modest hardware.

```
Docker Compose (start)  ->  Kubernetes (only if you actually need it)

  postgres          Primary DB. Managed (RDS / Neon / Supabase) - don't self-host.
  redis             Celery broker + response cache
  minio / S3        Raw HTML/PDF archive. Cheap, grows forever.
  fastapi           API, 2+ replicas behind a load balancer
  nextjs            Frontend
  celery-worker     Scrapers and parsers. Scale this horizontally.
  celery-beat       Scheduler
  typesense         Search (when you outgrow Postgres FTS)
```

- **Hosting.** AWS Mumbai (`ap-south-1`) or Azure India. Keeping data in India removes a whole category of cross-border questions. Render or Railway are fine to start and cheaper to operate with no DevOps person.
- **Monitoring.** Sentry for errors, Prometheus plus Grafana for metrics. Track **per-source scrape success rate** as a first-class metric — it is your early warning that a bank redesigned their site. Alert when any source returns zero new listings for 48 hours.
- **CI/CD.** GitHub Actions. Crucially, **test parsers against a fixture corpus** — keep roughly 50 real PDFs with hand-verified expected output, and run every parser change against them. This is the single practice that separates a demo from production.
- **Cost estimate, early production.** Roughly ₹15,000–40,000 per month (compute, managed Postgres, S3, OCR/LLM API calls, geocoding, WhatsApp). The dominant variable cost is document AI calls.

---

# Part E — Legal, regulatory and privacy

*This is an engineering perspective, not legal advice. Get an Indian technology and IP lawyer to review before launch.*

## E.1 Is scraping legal in India?

There is no statute prohibiting it and no definitive Indian precedent. Legality turns on *how* and *what*.

- **IT Act, 2000, Section 43(b)** — civil liability (compensation up to ₹1 crore) for downloading, copying or extracting data from a computer system "without permission". **Section 66** makes it a criminal offence when done dishonestly or fraudulently. The pivot is "without permission", and it is untested for openly-published public pages. Critically: **never** bypass a login, CAPTCHA, paywall or rate limit. That is where you move from a grey area into clear exposure.

- **Copyright Act, 1957** — facts are not copyrightable, but *compilations* are protected where there is originality in selection and arrangement. **Eastern Book Company v. D.B. Modak (2007)** is the key Supreme Court authority: EBC could not claim copyright in judgment text, but *could* in its headnotes and editorial additions. Applied here, a reserve price, an auction date and a property address are bare facts you may restate. Another aggregator's curated description, their photographs and their site layout are not. So: **extract facts, write your own descriptions, never bulk-copy another aggregator's database.**

- **Terms of Service** — most auction platforms prohibit automated access. Whether a browsewrap ToS binds a non-registering visitor is unsettled in India, but if you *register an account* and click "I agree", you are in clear contract territory. Read the ToS of each source, and treat "I registered and then scraped" as materially riskier than "I read a public page".

- **The asymmetry to exploit.** Notices published under a *statutory mandate* — Rule 8 newspaper publications, IBBI Form G, DRT notices, BAANKNET as a government-backed portal — exist precisely to achieve maximum public circulation. Republishing them with attribution and a link to the original is about as defensible as this gets. Third-party commercial aggregators are the riskiest source and add the least unique value. **Prioritise statutory sources; deprioritise scraping competitors.**

## E.2 Personal data and the DPDP Act

Auction notices contain borrower names, guarantor names, addresses and debt amounts. That is personal data, and it is sensitive in a reputational sense — publishing that someone defaulted is genuinely harmful to them.

**Current status (as of 26 September 2026).** The **DPDP Act, 2023** and **DPDP Rules, 2025** were notified on 13 November 2025 and commence in phases:

| Phase | Date | What commences |
|---|---|---|
| I | 13 Nov 2025 | Data Protection Board, administrative provisions |
| II | 13 Nov 2026 | Consent manager provisions |
| III | **13 May 2027** | All substantive obligations — notice, consent, security, breach reporting, data principal rights, retention limits |

Until Phase III, the older IT Act / SPDI Rules regime applies. So there is runway, but build compliant from the start rather than retrofit.

**Section 3(c)(ii)** is the likely exemption: the Act does not apply to personal data made publicly available either by the data principal themselves, or **by any person under a legal obligation to make it public**. Banks publishing Rule 8 sale notices are under exactly such an obligation, which is a strong argument. But the exemption plausibly covers the *original publication*; whether it extends to an indexed, searchable, permanently-retained aggregation of it is untested. Do not bet the company on it.

**Build these in regardless** — they cost little and they are what a regulator or judge would look for:

- **Suppress borrower and guarantor names from public pages by default.** They add near-zero value to a buyer, who cares about the property, the price and the date. Retain them internally for deduplication only.
- **Auto-expire aggressively.** Remove listings from public search within 90 days of the auction concluding. Someone's default should not be the top Google result for their name in 2032.
- **`noindex` on pages containing any personal data**, so search engines do not create a permanent shadow archive.
- **A published grievance / takedown process** with a named contact and a committed response time. Honour removal requests for concluded auctions without arguing.
- **Publish a data retention policy** and enforce it with a scheduled job.

## E.3 Liability for what you display

You are republishing facts that materially affect large financial decisions. If you show a stale auction date, a wrong reserve price, or a listing that was stayed by the DRT, and someone acts on it, you have a problem.

- **Prominent disclaimer** on every listing page, not buried in a footer: information is aggregated from public sources, may be inaccurate or outdated, is not an offer, and users must verify against the original notice and the bank before acting.
- **Always link to the source.** Every listing carries `canonical_source_url` and, ideally, the archived PDF. This shifts you from "publisher of a claim" toward "index pointing at the bank's own statement" — a much better position both legally and for user trust.
- **Show the timestamp.** "Verified 2 hours ago."
- **Never take money for the auction itself.** Do not handle EMD, do not pretend to register bidders, do not imply affiliation with any bank. Charge for search, alerts, analytics and lead generation — not for the transaction.
- **Trademarks.** Using "ICICI Bank" to factually identify whose auction it is, is nominative use and generally fine. Using bank logos prominently, or a design implying partnership, is not. Use plain text bank names.
- **IT Rules, 2021** intermediary obligations apply if you host user-generated content (reviews, comments) — you would need a grievance officer and defined takedown timelines. Simplest path early on: do not host UGC.
- **RERA.** If you ever move from *listing* to *facilitating* transactions for a commission, you may need real estate agent registration in each state. Stay on the information side of that line until you have taken advice.

---

# Part F — How to sequence this

The failure mode for a beginner is trying to build all ten sources at once. Do this instead.

**Phase 1 (weeks 1–4) — one source, end to end.** Pick **IBBI Form G** or **BAANKNET**: structured, public, statutorily published, friendliest legally. Build adapter, raw store, parser, Postgres, and a single Next.js search page. Ugly is fine. The goal is proving the whole pipeline end to end, because that teaches you where the real problems are — and they will not be where you expect.

**Phase 2 (weeks 5–10) — the PDF problem.** Add HDFC and Axis notice pages. This is where you build the OCR/LLM cascade, confidence scoring, and the human review queue. Assemble your 50-PDF fixture corpus now and never stop adding to it. Expect this phase to take twice as long as you estimate. Everyone's does.

**Phase 3 (weeks 11–16) — scale sources and dedup.** Add `bankeauctions.com` and `auctiontiger.net`. Now the same property arrives from three directions and deduplication becomes real. Build entity resolution, change tracking and the status lifecycle.

**Phase 4 (weeks 17–24) — product.** Proper search facets, maps, saved searches, email and WhatsApp alerts, SEO landing pages per city and asset type, and the first analytics ("this property is in round 3, reserve down 22% from original").

**Phase 5 — differentiation.** Newspaper ingestion (hardest, highest coverage), vehicle and machinery auctions, historical sold-price analytics, and an API for banks and investors.

## What to ask your senior for

In rough order of value:

1. **A budget line for a Document AI service** (Google Document AI / AWS Textract) and an LLM API key. This is the difference between six weeks of OCR frustration and two weeks of building product. Perhaps ₹10,000–20,000 per month to start.
2. **A lawyer's hour** — someone with Indian IP and technology law experience — to review the scraping approach, disclaimers, privacy policy and DPDP position *before* launch. The highest-ROI money you will spend.
3. **A managed Postgres instance and an S3 bucket** in `ap-south-1`. Do not self-host the database.
4. **Introductions.** If the organisation has any relationship with a bank's recovery department, an ARC, or one of the e-auction service providers, an official data feed beats scraping on every axis — reliability, legality, latency, cost. Banks generally *want* more bidders, because more bidders mean higher realisation. You are offering them something they want.
5. **A few hours a week of someone's time for review-queue duty**, at least for the first few months, plus a subscription to a business daily or two for newspaper notice access.
6. **MapmyIndia / Mappls geocoding API credits** — materially better than free alternatives on Indian addresses.

---

## The three things that actually determine whether this works

Strip away the technology and it comes down to:

1. **Coverage** — do you have listings the free portals do not?
2. **Accuracy** — is your reserve price right, every time?
3. **Freshness** — is that auction still happening?

Every architectural decision in this document serves one of those three. When deciding whether something is worth building, check it against that list.
