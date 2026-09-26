# Centralised Bank Auction Portal — Executive Summary

**A 5-minute read. The full version runs to ~40 pages.**

---

## 1. The headline finding

**BAANKNET (baanknet.com), launched 3 January 2025 by the Department of Financial Services, already does this — for public sector banks.** All 12 PSBs (SBI, PNB, Bank of Baroda, Canara, Union and others) plus IBBI list properties there with search, filters, maps, reserve prices, EMD and integrated bidding.

**But it covers only the 12 PSBs.** ICICI, HDFC, Axis, Kotak, every NBFC, ARC, cooperative bank, DRT sale and IBC liquidation are *not* on it. Their listings are scattered across `bankeauctions.com`, `auctiontiger.net`, `mstcecommerce.com`, individual bank PDF pages and newspaper notices.

**Positioning:** not "bank auctions" but *"every distressed asset in India in one search"*. Index BAANKNET; go and get everything it does not cover.

---

## 2. The legal process, in one page

**How a loan becomes an auction (RBI IRACP Directions, 2025):**

Miss a payment → SMA-0 (up to 30 days) → SMA-1 (30–60) → SMA-2 (60–90) → **NPA at more than 90 days overdue**. Roughly three missed EMIs.

**Then SARFAESI Act, 2002 + Security Interest (Enforcement) Rules, 2002 take over:**

| Step | Provision | What happens |
|---|---|---|
| 1 | Sec 13(2) | Demand notice: repay **entire** outstanding in **60 days** |
| 2 | Sec 13(3A) | Borrower may object; bank replies with reasons in 15 days |
| 3 | Sec 13(4) | Bank takes possession — **symbolic** (paper) or **physical** |
| 4 | Sec 14 | Physical possession usually needs a District Magistrate order + police |
| 5 | Rule 8(1)–(2) | Possession notice in 2 newspapers (1 vernacular) within 7 days |
| 6 | Rule 8(5) | Approved valuer values it; **Reserve Price** fixed |
| 7 | Rule 8(6) | Sale notice served on borrower + published + uploaded |
| 8 | Rule 9(1) | **Minimum 30-day gap** between notice and auction |
| 9 | Rule 9(3)–(4) | Winner pays **25% immediately**, **balance 75% in 15 days** |
| 10 | Rule 9(6) | Sale Certificate issued |

**Key recent authority.** *M. Rajendran v. KPK Oils and Proteins* (2025 INSC 1137, 22 Sep 2025): one composite sale notice, and the 30 days run from whichever happens last — service, newspaper publication, affixation or website upload. The borrower's **right of redemption under Sec 13(8) dies at the end of that 30-day window** (narrowed by the 2016 amendment from the earlier "until sale").

**Appeals:** DRT under Sec 17 within 45 days; DRAT under Sec 18 with a 50% deposit. Civil courts barred (Sec 34). A DRT stay can kill a listed auction overnight.

**Not covered by SARFAESI:** gold loans (pledges), agricultural land, aircraft and ships, debts under ₹1 lakh, and where under 20% of principal + interest remains due.

**Vehicles are different.** Banks repossess cars under the **contractual repossession clause** (RBI Responsible Business Conduct Directions, 2025), not SARFAESI — the magistrate route costs more than the car. Sale happens at dealer yard auctions. Data is largely private. Treat as a later phase.

---

## 3. Where the data actually is

| Source | Coverage | Difficulty |
|---|---|---|
| **BAANKNET** | 12 PSBs + IBBI | Easy — structured, public, likely JSON API |
| **IBBI Form G** | IBC liquidations | Easy — best legal footing, start here |
| **C1 India** (`bankeauctions.com`) | HDFC, Axis, many others | Medium |
| **AuctionTiger** (`auctiontiger.net`) | HDFC and others, per-bank subdomains | Medium |
| **Bank websites** | Everyone, as PDFs | Hard — unstructured PDFs |
| **DRT / DRAT** | Tribunal-ordered sales | Hard |
| **Newspapers** | Widest of all, incl. possession notices | Hardest — but the real differentiator |

**Key insight:** private banks do not build auction technology, they outsource it. Scraping ~6 service providers beats scraping ~60 bank websites.

---

## 4. Why this is technically hard

A real HDFC notice (15 Jan 2026), run through a naive PDF text extractor, produced this:

```
... | Rs.3,37,55,000/- PM to Rs.33,75,500/- Rs.1,00,000/- | ...
```

That is **three columns collapsed into one** — Reserve Price ₹3.3755 crore, EMD ₹33,75,500, Bid Increment ₹1,00,000 — plus `PM to` leaked in from an adjacent column. Naive extraction silently produces **the wrong reserve price on a ₹3 crore property**.

The same PDF contained **four separate properties** (Item No. 1–4), each with its own price, EMD and auction slot. One document must yield N listings.

**Layout-aware extraction and confidence scoring are the core product, not polish.**

---

## 5. The build, in brief

**Pipeline:** Sources → polite fetch (Scrapy + Playwright) → **immutable raw store** (S3) → parse cascade → normalise → dedup → Postgres → search index → API → portal + alerts.

**Golden rule: never overwrite raw data.** Store every fetch with URL, timestamp and SHA-256. When the parser has a bug, reparse history instead of re-crawling.

**Extraction cascade** (cheapest first):

| Tier | Method | Target |
|---|---|---|
| 0 | JSON API / clean HTML | 60–70% of volume |
| 1 | `pdfplumber.extract_table()` with line strategies | Digital PDFs |
| 2 | OCR — cloud Document AI to start, PaddleOCR later | Scanned notices, vernacular |
| 3 | LLM with a strict JSON schema, `null` encouraged | The hard remainder |

**Validate with business rules, not just schema.** EMD should be ~10% of reserve price — in the HDFC example, ₹33,75,500 ÷ ₹3,37,55,000 = exactly 10.0%, which confirms the columns split correctly. Auction date must be ≥30 days after sale notice (Rule 9(1)). Reserve price is almost always below outstanding dues. Run a deterministic parse and an LLM parse; where they agree, auto-publish, where they disagree, send to human review.

**Plan for 8–15% human review.** One reviewer handles 200–400 listings/day. Build that internal tool properly — beginners always underbuild it.

**Deduplication:** blocking (on `platform_auction_id`, city + reserve price, MinHash over descriptions) then weighted scoring (reserve price exact match is a very strong signal). Critically, a **re-auction is not a duplicate** — it is a new `round_number` with a lower reserve price, and that is the most valuable signal for a buyer.

**Stack:** Postgres (managed) · Redis · S3/MinIO · Scrapy + Celery · FastAPI · Next.js with SSR (for SEO — your main acquisition channel) · Typesense when you outgrow Postgres FTS · Sentry + Grafana. Host in `ap-south-1` (Mumbai). Docker Compose first, Kubernetes only if genuinely needed.

**Running cost, early production:** roughly ₹15,000–40,000/month, dominated by document AI calls.

---

## 6. Legal, in brief

- **Scraping.** No Indian statute prohibits it and no definitive precedent exists. IT Act s.43(b) creates civil liability for extraction "without permission"; s.66 adds criminal liability for dishonest conduct. **Never bypass a login, CAPTCHA, paywall or rate limit** — that is the line between grey area and clear exposure.
- **Copyright.** Facts (price, date, address) are free to restate. *Eastern Book Company v. D.B. Modak* (2007): compilations attract copyright only in original selection and arrangement. So **extract facts, write your own descriptions, never bulk-copy a competitor's database.**
- **Prefer statutory sources.** Rule 8 notices, IBBI Form G, DRT notices and BAANKNET exist to be circulated widely. Republishing them with attribution is the most defensible position. Scraping commercial aggregators is the riskiest and adds the least value.
- **DPDP Act, 2023.** Notified 13 Nov 2025, phased: Data Protection Board live now, consent managers from 13 Nov 2026, **all substantive obligations from 13 May 2027**. Section 3(c)(ii) likely exempts data published under legal obligation, but that is untested for aggregation. Regardless: **hide borrower names by default**, auto-expire listings ~90 days after the auction, `noindex` any personal data, and publish a real takedown process.
- **Liability.** Prominent disclaimer on every listing, always link to the original notice, show a "last verified" timestamp, and **never handle EMD or imply bank affiliation**. Monetise search, alerts and analytics — not the transaction.

---

## 7. Roadmap

| Phase | Weeks | Goal |
|---|---|---|
| 1 | 1–4 | **One source end to end.** IBBI or BAANKNET. Ugly is fine — prove the pipeline. |
| 2 | 5–10 | **The PDF problem.** HDFC + Axis. OCR/LLM cascade, confidence scoring, review queue. Will take 2× your estimate. |
| 3 | 11–16 | **Scale + dedup.** C1 India, AuctionTiger. Entity resolution, status lifecycle. |
| 4 | 17–24 | **Product.** Facets, maps, saved searches, alerts, SEO pages, first analytics. |
| 5 | — | **Differentiate.** Newspapers, vehicles, sold-price history, API. |

## 8. What to ask your senior for

1. **Budget for a Document AI service + LLM API key** (~₹10–20k/month). Saves weeks.
2. **An hour with an Indian tech/IP lawyer** before launch. Highest-ROI spend on the list.
3. **Managed Postgres + S3 bucket** in `ap-south-1`. Do not self-host the database.
4. **Introductions** to any bank recovery department, ARC, or e-auction service provider. An official feed beats scraping on reliability, legality, latency and cost — and banks *want* more bidders, because more bidders mean higher realisation.
5. **A few hours a week of someone's time** for review-queue duty, plus a business daily subscription.
6. **MapmyIndia / Mappls geocoding credits** — much better than free options on Indian addresses.

---

## The three things that decide whether this works

1. **Coverage** — do you have listings the free portals do not?
2. **Accuracy** — is your reserve price right, every time?
3. **Freshness** — is that auction still happening?

Check every build decision against this list.
