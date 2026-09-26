"""Quick check that a running portal is serving real data."""

import sys

import httpx

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000"


def main() -> None:
    health = httpx.get(f"{BASE}/api/health", timeout=20).json()
    print(f"health      : {health}")

    page = httpx.get(f"{BASE}/api/listings", params={"page_size": 3}, timeout=20).json()
    print(f"total       : {page['total']} listings across {page['total_pages']} pages")
    print()

    for item in page["listings"]:
        where = ", ".join(x for x in (item["city"], item["state"]) if x)
        print(f"  {item['reserve_price_display']:>13}   {where}")
        print(f"                  {item['bank_name']}  /  {item['asset_type']}")
        print(
            f"                  {item['possession_type']} possession"
            f"  /  {item['status']}"
            f"  /  EMD {item['emd_display']}"
        )
        print(f"                  {item['source']['notice_url']}")
        print()

    for path, params in (
        ("/", None),
        ("/", {"state": "Gujarat"}),
        ("/", {"q": "Mumbai"}),
        ("/robots.txt", None),
    ):
        response = httpx.get(f"{BASE}{path}", params=params, timeout=20)
        label = path + (f"?{httpx.QueryParams(params)}" if params else "")
        print(f"{label:<28} {response.status_code}  {len(response.text):>7,} chars")


if __name__ == "__main__":
    main()
