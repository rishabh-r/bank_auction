# Auction Portal

> **Project handoff — 6 October 2026**
> Read this section first when continuing the project. This README is the
> durable context for the current implementation and deployment plan.

## Current state and handoff

### What the project is

An Indian bank-auction discovery portal. It fetches publicly accessible
BAANKNET property and repossessed-vehicle listings, stores normalized records
in PostgreSQL, and serves search pages plus a JSON API. It is an information
directory: users complete due diligence and participate in the auction on the
originating bank/auction platform. The portal does not sell assets or accept
EMD/payments.

### Current intended hosting arrangement

The user wants the portal and crawlers to keep running while their laptop is
off. The current design is:

```text
GitHub Actions (scheduled collection and maintenance)
                 │ writes
                 ▼
          Neon PostgreSQL
                 ▲ reads
                 │
            Vercel portal
```

- **Collector:** `.github/workflows/collect.yml` is scheduled four times
  daily at 07:40, 13:40, 19:40 and 01:40 India time (GitHub cron is UTC).
  The vehicle workflow is scheduled daily at 04:10 India time. On 6 October,
  GitHub-hosted requests to BAANKNET returned HTTP 403 for `robots.txt` and
  both property sitemaps. That run misleadingly showed green while discovering
  and fetching zero URLs because discovery errors are logged and swallowed.
  Do not treat that workflow as a functioning collector or run the vehicle
  workflow against the same blocked host. Pause/disable both scheduled
  workflows until BAANKNET approves cloud access or an official feed is
  arranged; confirm their current enabled/disabled state in GitHub.
- **Database:** Neon project `rapid-union-54468753`, production branch. The
  project was linked/configured from this checkout; `neon.ts` is deliberately
  `defineConfig({})`. Neon CLI setup/deploy was run. A live read-only check on
  6 October 2026 confirmed PostgreSQL 18.6, Alembic revision `0035c50fc4a9`,
  3,534 total listing rows (3,523 published), 261 archived source documents,
  and 258 URL-state rows. The property table's sequence had fallen behind
  imported IDs; `listings`, `listing_revisions`, and `source_documents`
  sequences were aligned to their row maxima before the successful local run.
  The app's local ignored `.env` has the Neon connection settings. Never copy
  a connection string or password into README, source control, logs, or chat.
- **Website:** live at
  [bank-auction-seven.vercel.app](https://bank-auction-seven.vercel.app/).
  `/api/health` returned `status: ok` and 3,523 published listings after the
  local crawl. Vercel environment variables are configured. `CONTACT_URL` is
  `https://bank-auction-seven.vercel.app/bot`. `docs/VERCEL.md` was written
  before the Actions collector was added; its laptop/VPS collector instructions
  are superseded here.
- **GitHub:** intended public repository is
  [`rishabh-r/bank_auction`](https://github.com/rishabh-r/bank_auction), as
  provided by the user. The `main` branch is pushed and tracks `origin/main`.
  GitHub Actions secrets are configured (the manual workflow ran with them).
  Before the public push, reachable Git history was scanned for common
  credential patterns.
- **Laptop independence:** the website and database do not depend on the
  laptop. The current successful collector path does depend on the laptop's
  network because GitHub-hosted runners receive 403 from BAANKNET. The user
  wants unattended crawling, so obtain an approved cloud-access method before
  claiming automated updates are live.

### Collector behavior and an accepted tradeoff

GitHub-hosted runners are temporary, so both collector workflows set
`ARCHIVE_ENABLED=false`. Structured listings are persisted in Neon; raw fetched
HTML/documents are not kept in durable storage. Consequently parser changes
require fetching the source again; local development can still archive files
under ignored `data/` and use `reparse`. This tradeoff was discussed and
accepted for the initial cloud test to avoid adding object storage. Preserve
that distinction when explaining the system. The collector uses a 3-second
request delay and obeys the source adapter's robots policy.

The property workflow runs `alembic upgrade head`, crawls BAANKNET with a
default limit of 250 URLs, then runs maintenance and a best-effort health
report. It accepts a `limit` input for manual workflow runs. Vehicle collection
is a separate daily workflow with a limit of 150. Both use the GitHub Actions
secrets `DATABASE_URL`, `CONTACT_EMAIL`, and `CONTACT_URL`. `DB_SERVERLESS` is
enabled for the short-lived runner and Vercel runtime. However, GitHub-hosted
requests to BAANKNET were refused (403), so scheduled cloud runs currently do
not update listings; the workflow's green result for zero discovered URLs is
misleading and should be fixed before re-enabling schedules.

### Latest manual crawl (6 October 2026)

- A manual local crawl reached BAANKNET from the laptop, read both sitemaps
  (71,907 property URLs), and processed a 250-URL batch with the configured
  3-second request delay and robots checks enabled.
- The first attempt exposed out-of-sync Neon sequences. It fetched 11 pages
  but listing writes failed; the 11 local raw pages were recovered by
  `auction_portal reparse baanknet` after aligning the three table sequences.
- The subsequent batch completed: 250 fetched, 156 new listings, 8 updated,
  85 unchanged, and 1 parse failure. Neon then showed 3,534 total rows and
  3,523 published. Raw pages are stored on this laptop under ignored `data/`.
- The local ignored `.env` now points the crawler's `CONTACT_URL` to the live
  `/bot` page. Do not commit `.env` or the local raw archive.

### What has been implemented

- Phase 1 milestones M1–M6 are implemented in the codebase: project foundation
  and config; polite fetching and archival; PostgreSQL schema/migrations;
  BAANKNET property and vehicle adapters; searchable server-rendered portal
  and JSON API; scheduling, maintenance, health reporting, packaging and user
  manual.
- Collectors for BAANKNET property listings (roughly 72,000 site-reported
  records across public-sector banks/IBBI) and repossessed vehicles (roughly
  400 site-reported records) are included. Treat those approximate source
  counts as context, not a live count.
- Search filters, listing confidence/withholding, status lifecycle, revision
  history and duplicate/re-auction reporting are implemented.
- Auction countdown text and date-derived `upcoming` / `live` / `closed`
  badges redraw in the browser every 15 seconds without reloading the page.
  Actual listing data still uses the existing 60-second version check and
  explicit Refresh / Not now notice; crawls update the database, not an
  already-rendered page automatically.
- The portal avoids storing borrower/guarantor names and links listings back
  to their source notice. It includes disclaimers and possession/legal-process
  warnings.
- Tests and source fixtures exist under `tests/`; docs include the research,
  deployment guides and customer user manual.
- Neon configuration support, a copy-to-remote utility, Vercel entry point,
  and GitHub scheduled workflows are in the repository.

### What is still pending

1. Confirm both GitHub Actions workflows are disabled while cloud BAANKNET
   access returns 403. Do not evade the block with proxies, IP rotation, or
   browser impersonation.
2. Ask BAANKNET/PSB Alliance for approved machine access, an official feed/API,
   or written guidance on cloud collection. Their support details are on
   [`PSB Alliance's BAANKNET page`](https://psballiance.com/baanknet.html).
3. Make sitemap discovery failures fail the workflow instead of returning a
   green zero-result run. Only resume cloud schedules after permitted access
   is confirmed and an end-to-end cloud crawl persists records in Neon.
4. Before public launch, complete a qualified Indian legal/privacy review,
   publish a real contact/about page, privacy notice and takedown route, and
   confirm source terms and robots policies.

### Credentials and safety for the next agent

- `.env`, `.neon`, `data/`, `.pgsql/`, and logs are local/secret/runtime
  material and must never be committed. `.env.example` contains placeholders
  and local development defaults only.
- A user-provided OpenAI API key appeared earlier in the conversation. It is
  not needed for Phase 1. Do not repeat, log, or commit it; if it is still
  active, advise the user to revoke/rotate it before any later Phase 2 use.
- The Neon connection URL is in local ignored configuration and provider
  secret settings. If database credentials were exposed, rotate them in Neon.
  Never display the full connection URL in command output.
- Before any public push: `git status --short`, inspect `git diff --cached`,
  inspect tracked files for secrets, and confirm ignored local files are not
  staged. Public repository means any accidentally committed secret should be
  treated as compromised and rotated, not merely deleted in a later commit.

### Useful next-agent starting point

1. Read this handoff. Use [`docs/VERCEL.md`](docs/VERCEL.md) for the Vercel
   configuration checklist, bearing in mind its collector section is older.
2. Inspect `git status --short --branch`, `git remote -v`, and the latest
   commits. `main` tracks `origin/main`; do not assume that a successful push
   means a deployment is live.
3. Confirm repository authentication and current cloud configuration without
   printing secret values.
4. Continue from the latest crawl note above. The site is live; GitHub-hosted
   BAANKNET access is blocked and the user's local network currently works.
   Never claim cloud automation is active until the 403 is resolved with an
   approved method and the workflow logs confirm saved rows.

---

A centralised search portal for Indian bank auction listings — properties and
other assets sold by banks under the SARFAESI Act, 2002, aggregated from
publicly available sources into one searchable place.

Background research, the regulatory framework and the full build plan are in
[`docs/bank-auction-portal-full.pdf`](docs/bank-auction-portal-full.pdf)
(20 pages) with a 5-page summary alongside it.

---

## Status

**Phase 1 implementation complete; portal live.** Vercel serves the site from
Neon, and a manual laptop crawl succeeded. GitHub-hosted BAANKNET collection
currently receives HTTP 403, so automated cloud listing updates are not
working. See the current-state handoff at the top of this README.

| # | Milestone | State |
|---|-----------|-------|
| 1 | Foundation — repo, config, tests | **done** |
| 2 | Fetch & archive one source | **done** |
| 3 | Database | **done** |
| 4 | First real source adapter | **done** |
| 5 | Search UI | **done** |
| 6 | Scheduling, second source, monitoring, packaging | **done** |

For the current Vercel + Neon + GitHub Actions plan, see the handoff above and
[`docs/VERCEL.md`](docs/VERCEL.md). The older VPS/container guidance in
[`docs/DEPLOYMENT.md`](docs/DEPLOYMENT.md) is background, not the current
hosting choice. A legal review is still required before public launch.

**Phase 2** is PDF and OCR extraction, which unlocks the private banks
(ICICI, HDFC, Axis). It is roughly as much work as everything above.

![Search page](docs/screenshots/search.png)

## Sources

| Source | Coverage | Status |
|---|---|---|
| [BAANKNET](https://baanknet.com) properties | 12 public sector banks + IBBI, ~72,000 properties | live |
| BAANKNET vehicles | repossessed cars and commercial vehicles, ~400 | live |
| Bank notice PDFs (HDFC, Axis, ICICI) | private banks | Phase 2 |
| C1 India, AuctionTiger, MSTC | private banks and NBFCs | Phase 3 |

Vehicles reach auction by a different legal route. A car is hypothecated,
not mortgaged, and banks almost never use SARFAESI for one — the Section
14 magistrate route costs more than the vehicle. They repossess under the
contractual repossession clause instead, governed by RBI's Responsible
Business Conduct Directions. The adapter records this as
`legal_basis = contractual`.

### Why BAANKNET first

- `robots.txt` is `User-agent: * / Disallow:` — everything is permitted
- it publishes sitemaps, so URLs come from the site telling crawlers what
  to fetch rather than from guesswork
- detail pages are server-rendered, so the structured record behind the
  page is available directly: no OCR, no LLM, no inference
- one source covers all 12 public sector banks

---

## Setup

Requires Python 3.12 or newer.

```powershell
# 1. Create an isolated environment
python -m venv .venv

# 2. Install the project and its development tools
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"

# 3. Create your local configuration
Copy-Item .env.example .env
#    then edit .env and set CONTACT_EMAIL and CONTACT_URL

# 4. Set up a project-local PostgreSQL server
.\.venv\Scripts\python.exe scripts\setup_postgres.py

# 5. Apply the database schema
.\.venv\Scripts\python.exe -m alembic upgrade head

# 6. Confirm everything works
.\.venv\Scripts\python.exe -m pytest
```

On macOS or Linux, replace `.\.venv\Scripts\python.exe` with `.venv/bin/python`.

### The local database

`scripts/setup_postgres.py` downloads the official PostgreSQL portable
binaries into `.pgsql/` and runs a server on **port 5433**. No administrator
rights, no Windows service, and nothing that can collide with another
PostgreSQL on the machine. Everything it creates is git-ignored.

```powershell
.\.venv\Scripts\python.exe scripts\setup_postgres.py --status
.\.venv\Scripts\python.exe scripts\setup_postgres.py --start
.\.venv\Scripts\python.exe scripts\setup_postgres.py --stop
.\.venv\Scripts\python.exe scripts\setup_postgres.py --reset   # delete it all
```

The server does not start automatically when Windows boots. Run `--start`
after a reboot.

---

## Usage

```powershell
# Run the portal, then open http://127.0.0.1:8000
.\.venv\Scripts\python.exe -m auction_portal serve

# Run crawls and maintenance automatically
.\.venv\Scripts\python.exe -m auction_portal schedule
.\.venv\Scripts\python.exe -m auction_portal schedule --dry-run   # list jobs

# Is anything broken? Exits non-zero if so, so it works as a cron check.
.\.venv\Scripts\python.exe -m auction_portal health

# Report duplicates and re-auctions
.\.venv\Scripts\python.exe -m auction_portal dedup

# Advance statuses and apply retention, once
.\.venv\Scripts\python.exe -m auction_portal maintain

# Show the loaded configuration
.\.venv\Scripts\python.exe -m auction_portal config

# Check the database connection and migration state
.\.venv\Scripts\python.exe -m auction_portal db

# Collect listings from a source
.\.venv\Scripts\python.exe -m auction_portal crawl baanknet --limit 50

# Browse what has been collected
.\.venv\Scripts\python.exe -m auction_portal listings --state Gujarat
.\.venv\Scripts\python.exe -m auction_portal listings --all   # include withheld

# Re-run parsing over archived documents. No network access at all.
.\.venv\Scripts\python.exe -m auction_portal reparse baanknet

# Fetch and archive a single document
.\.venv\Scripts\python.exe -m auction_portal fetch <url> --source-id hdfc_web

# Archive statistics
.\.venv\Scripts\python.exe -m auction_portal stats
```

Fetching the same URL twice reports `304` or `UNCHANGED` and stores nothing
new. On a durable local filesystem the raw-document archive enables offline
reparsing. In GitHub Actions, archiving is deliberately disabled because the
runner is temporary; production parsing improvements therefore require a
source re-fetch unless durable object storage is added.

`reparse` is the reason raw bytes are archived immutably: when the parser
improves, history is reprocessed offline instead of re-crawled. No source
is contacted and nothing is lost.

### Withheld listings

A listing is only published when its confidence reaches 0.70. Anything
below that is stored but hidden, so the portal shows fewer listings rather
than a wrong price. On the first real crawl this caught a property whose
bank had uploaded a reserve price of Rs 1.

Use `--all` to see withheld listings and the flags that withheld them.

### The portal

Pages are server-rendered rather than a single-page app. Most traffic to a
portal like this arrives from people searching "SBI auction property Pune",
so complete HTML on the first response — indexable, fast, working without
JavaScript — matters more than client-side interactivity.

A JSON API is available at `/api/listings`, documented at `/api/docs`.

What every page guarantees, and what the tests enforce:

- **No borrower or guarantor names.** They add nothing for a buyer, and
  publishing someone's default is a real harm. The names are not stored on
  the listing at all, so no template change can leak them.
- **A link to the original notice** on every listing, plus when it was
  first seen and last verified.
- **A disclaimer** on every page, and a clear statement that we are not a
  bank, run no auctions and handle no EMD payments.
- **A warning on symbolic possession**, because the buyer may inherit an
  eviction, and on DRT or IBC sales, because a different legal process
  applies.

---

## Running it from the editor

The commands above all have an equivalent in VS Code or Cursor, so none of
them has to be typed. The configuration lives in `.vscode/` and is
committed, so it works on a fresh clone once the venv exists.

Start the database first. It is not a Windows service and does not come up
on boot: press `Ctrl+Shift+P`, choose **Tasks: Run Task**, then **Start
database**. Do this once per reboot.

Then press `F5` and pick a configuration. **Portal (web server)** serves
the site at http://127.0.0.1:8000 with breakpoints working; there is an
auto-reload variant for when you are editing templates rather than
debugging, since uvicorn's reloader and the debugger do not coexist.
The rest of the list covers the scheduler, both crawlers, `reparse`, the
health check, the dedup report and `stats`. **Debug current test file**
runs pytest on whichever file is open.

The same **Tasks: Run Task** menu holds the things that are not
debugging: starting, stopping and checking the database, applying
migrations, running the tests, linting, formatting, and building the
documentation PDFs.

The Testing sidebar (the flask icon) discovers the suite and runs it, or
any single test, with a click. Failures link straight to the line.

---

## Running unattended

`auction_portal schedule` runs everything on a timer:

| Job | When | Why |
|---|---|---|
| Crawl each source | every 6 hours | new and changed listings |
| Refresh imminent auctions | hourly | auctions within 7 days get moved and cancelled at short notice |
| Advance statuses | every 15 min | upcoming to live to closed, on time |
| Expire old listings | daily 03:30 IST | stop publishing concluded auctions |
| Health check | every 2 hours | shout when a source looks broken |

### Monitoring

Scrapers fail **silently** — a changed selector returns zero results
without raising anything. So the alert is not "did it error" but "is the
parser still yielding listings".

A source is unhealthy when it discovers no URLs, fetches pages but parses
none of them, has most of its fetches fail, or produces no listings at
all for 48 hours. Note the last one counts listings *seen*, not listings
*created*: once a source is established most runs legitimately create
nothing, and alerting on that would cry wolf daily.

### Duplicates and re-auctions

`auction_portal dedup` reports two relationships:

- **Duplicates** — the same asset from two sources, to be merged.
- **Re-auctions** — the same asset months later at a lower reserve, to be
  linked and shown as price history.

Identity is judged only on properties of the *asset* — address, area,
locality, PIN code — and never on price or date. That matters: a
re-auction has by definition a later date and usually a lower price, so
scoring those as differences would make the matcher worst at exactly the
case it most needs to catch.

Results are reported, not merged. A wrong merge destroys two listings and
is far harder to notice than a missed one.

---

## Layout

```
src/auction_portal/
    config.py          Settings, loaded and validated from .env
    logging_setup.py   Logging configuration
    archiver.py        Fetch -> detect change -> archive -> record
    crawler.py         Runs a source adapter end to end; also reparse
    cli.py             Command line interface
    normalise/
        money.py       Indian rupee amounts (lakh/crore, 2-2-3 grouping)
        dates.py       Day-first Indian dates, IST handling
        area.py        sqft/sqyd/acre/hectare/guntha conversion
        geo.py         Coordinate validation against state bounding boxes
        text.py        Whitespace, mojibake, PIN codes, phone numbers
    search.py          Filters, facets, sorting, pagination
    dedup.py           Duplicate and re-auction detection
    maintenance.py     Status lifecycle, retention, health checks
    scheduler.py       Unattended job scheduling
    web/
        app.py         FastAPI: HTML pages and JSON API
        templates/     Server-rendered pages
        static/        Stylesheet
    fetching/
        models.py      RawDocument, FetchResult
        robots.py      robots.txt compliance
        throttle.py    Per-domain rate limiting
        client.py      HTTP client: retries, backoff, conditional GET
    storage/
        raw_store.py   Immutable content-addressed archive
    db/
        models.py      Tables: source_documents, url_state, listings,
                       listing_revisions
        session.py     Engine and transaction handling
        repository.py  Document reads and writes
        listing_repository.py  Listing upsert and change history
    sources/
        base.py        SourceAdapter interface, ParsedListing
        flight.py      Reading Next.js server-rendered payloads
        baanknet.py    BAANKNET property adapter
        baanknet_vehicle.py  BAANKNET vehicle adapter
Dockerfile             Container image
docker-compose.yml     postgres + web + scheduler
migrations/            Alembic schema migrations
scripts/               setup_postgres.py, probe.py, make_fixture.py
tests/                 Test suite
tests/fixtures/        Real archived pages with verified expected output
docs/                  Research and build plan
data/                  Downloaded documents (git-ignored, created at runtime)
.pgsql/                Local PostgreSQL server (git-ignored)
```

### Changing the schema

Never edit a table by hand. Change the models, then:

```powershell
.\.venv\Scripts\python.exe -m alembic revision --autogenerate -m "what changed"
.\.venv\Scripts\python.exe -m alembic upgrade head
```

The generated migration is committed to git, so every environment applies
the same change in the same order.

---

## Working on it

```powershell
.\.venv\Scripts\python.exe -m pytest          # run tests
.\.venv\Scripts\python.exe -m ruff check .    # lint
.\.venv\Scripts\python.exe -m ruff format .   # format
```

---

## Ground rules

These are deliberate and apply to every change:

1. **When archiving is enabled, raw downloaded data is immutable.** Local
   development archives documents for offline reparsing. The current GitHub
   Actions collectors disable raw archiving because their filesystems are
   temporary; see the handoff above for the accepted consequence.
2. **No secrets in the repository.** All configuration comes from `.env`,
   which is git-ignored. `.env.example` documents the required keys.
3. **Dependencies are pinned exactly.** Upgrades are a reviewed change to
   `pyproject.toml`, never an accident.
4. **Every piece of logic has a test**, written at the same time as the code.
5. **We crawl politely.** We identify ourselves with a contact address, honour
   `robots.txt`, rate-limit every request, and never bypass a login, CAPTCHA
   or paywall.

---

## Legal note

This project republishes information that banks are legally required to
publish (Rule 8, Security Interest (Enforcement) Rules, 2002). Every listing
links back to its original notice. Nothing here is an offer to sell, and no
auction payments are handled.

A legal review is required before the portal is made publicly available. See
Part E of the full document.
