"""Check the claims the testing guide makes, against a running portal.

The test suite proves these against fixtures. This proves them against
the live server holding real scraped data, which is what a reviewer will
actually be looking at.
"""

import sys

import httpx

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000"

failures: list[str] = []


def check(label: str, passed: bool, detail: str = "") -> None:
    mark = "PASS" if passed else "FAIL"
    print(f"  [{mark}] {label}" + (f"  -- {detail}" if detail else ""))
    if not passed:
        failures.append(label)


def main() -> int:
    client = httpx.Client(base_url=BASE, timeout=30, follow_redirects=True)

    home = client.get("/")
    check("A1 home page loads", home.status_code == 200)
    check("A5 disclaimer present", "may be inaccurate or out of date" in home.text)
    check("A5 states we are not a bank", "Not affiliated with any bank" in home.text)
    check(
        "A3 prices in Indian format", "Rs " in home.text and " Cr" in home.text or " L" in home.text
    )

    # B - searching
    hit = client.get("/", params={"q": "Gujarat"})
    miss = client.get("/", params={"q": "Antarctica"})
    check("B1 search returns results", hit.status_code == 200 and len(hit.text) > 5000)
    check("B3 no-match message, not an error", "Nothing matches those filters" in miss.text)

    # C - filtering
    filtered = client.get("/", params={"state": "Gujarat"})
    check("C1 state filter applies", "Gujarat" in filtered.text)
    check(
        "C2 other states still offered",
        "Telangana" in filtered.text or "Maharashtra" in filtered.text,
        "cannot switch state otherwise",
    )

    # F - the things that must not happen
    listings = client.get("/api/listings", params={"page_size": 100}).json()
    ids = [item["id"] for item in listings["listings"]]

    pages = [home.text, filtered.text]
    for listing_id in ids[:12]:
        pages.append(client.get(f"/listing/{listing_id}").text)

    combined = " ".join(pages).lower()
    check("F1 no 'borrower' anywhere", "borrower" not in combined)
    check("F2 no 'guarantor' anywhere", "guarantor" not in combined)
    check("F4 no bidding controls", "bid now" not in combined and "pay emd" not in combined)

    missing = client.get("/listing/999999")
    check(
        "F3 unknown listing is a clean 404",
        missing.status_code == 404 and "Listing not found" in missing.text,
    )

    serialised = str(listings).lower()
    check("G4 API exposes no borrower fields", "borrower" not in serialised)
    check("G2 API carries a disclaimer", "disclaimer" in listings)

    # E - provenance on every listing
    every_linked = all(
        item["source"]["notice_url"].startswith("https://") for item in listings["listings"]
    )
    check("E3 every listing links to its original notice", every_linked)

    every_verified = all(item["source"]["last_verified_at"] for item in listings["listings"])
    check("E4 every listing has a last-verified time", every_verified)

    health = client.get("/api/health").json()
    check("G3 health endpoint ok", health.get("status") == "ok", str(health))

    robots = client.get("/robots.txt").text
    check("robots.txt blocks the API", "Disallow: /api/" in robots)

    client.close()

    print()
    if failures:
        print(f"{len(failures)} CHECK(S) FAILED: {', '.join(failures)}")
        return 1
    print("All manual claims verified against live data.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
