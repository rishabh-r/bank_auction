# Auction Portal

A centralised search portal for Indian bank auction listings — properties and
other assets sold by banks under the SARFAESI Act, 2002, aggregated from
publicly available sources into one searchable place.

Background research, the regulatory framework and the full build plan are in
[`docs/bank-auction-portal-full.pdf`](docs/bank-auction-portal-full.pdf)
(20 pages) with a 5-page summary alongside it.

---

## Status

**Milestone 3 of 6 — Database.** Documents are downloaded, archived and
recorded in PostgreSQL. Nothing is parsed or published yet.

| # | Milestone | State |
|---|-----------|-------|
| 1 | Foundation — repo, config, tests | **done** |
| 2 | Fetch & archive one source | **done** |
| 3 | Database | **done** |
| 4 | First real source adapter | next |
| 5 | Search UI | |
| 6 | Scheduling, second source, deploy | |

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
# Show the loaded configuration
.\.venv\Scripts\python.exe -m auction_portal config

# Check the database connection and migration state
.\.venv\Scripts\python.exe -m auction_portal db

# Fetch and archive a document
.\.venv\Scripts\python.exe -m auction_portal fetch <url> --source-id hdfc_web

# Archive statistics
.\.venv\Scripts\python.exe -m auction_portal stats
```

Fetching the same URL twice reports `304` or `UNCHANGED` and stores nothing
new. That is the intended behaviour, and it is what keeps later parsing and
OCR costs down.

---

## Layout

```
src/auction_portal/
    config.py          Settings, loaded and validated from .env
    logging_setup.py   Logging configuration
    archiver.py        Fetch -> detect change -> archive -> record
    cli.py             Command line interface
    fetching/
        models.py      RawDocument, FetchResult
        robots.py      robots.txt compliance
        throttle.py    Per-domain rate limiting
        client.py      HTTP client: retries, backoff, conditional GET
    storage/
        raw_store.py   Immutable content-addressed archive
    db/
        models.py      Tables: source_documents, url_state
        session.py     Engine and transaction handling
        repository.py  Database reads and writes
    sources/           One adapter per data source (Milestone 4)
migrations/            Alembic schema migrations
scripts/               setup_postgres.py
tests/                 Test suite
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

1. **Raw downloaded data is never modified or deleted.** Parsers are rewritten
   often; re-downloading is not an option. Everything fetched is archived
   immutably and every later stage re-runs from that archive.
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
