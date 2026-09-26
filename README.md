# Auction Portal

A centralised search portal for Indian bank auction listings — properties and
other assets sold by banks under the SARFAESI Act, 2002, aggregated from
publicly available sources into one searchable place.

Background research, the regulatory framework and the full build plan are in
[`docs/bank-auction-portal-full.pdf`](docs/bank-auction-portal-full.pdf)
(20 pages) with a 5-page summary alongside it.

---

## Status

**Milestone 1 of 6 — Foundation.** Project scaffolding only; no data is
collected yet.

| # | Milestone | State |
|---|-----------|-------|
| 1 | Foundation — repo, config, tests | **done** |
| 2 | Fetch & archive one source | next |
| 3 | Database | |
| 4 | First real source adapter | |
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

# 4. Confirm everything works
.\.venv\Scripts\python.exe -m pytest
```

On macOS or Linux, replace `.\.venv\Scripts\python.exe` with `.venv/bin/python`.

---

## Layout

```
src/auction_portal/
    config.py          Settings, loaded and validated from .env
    logging_setup.py   Logging configuration
    sources/           One adapter per data source (Milestone 4)
tests/                 Test suite
docs/                  Research and build plan
data/                  Downloaded documents (git-ignored, created at runtime)
```

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
