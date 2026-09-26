"""Inspect an archived HTML document without re-fetching it.

Reads from data/raw, so it costs the source nothing. Useful when working
out what an adapter should extract.
"""

import json
import pathlib
import re
import sys

sys.path.insert(0, "src")

from auction_portal.sources.flight import extract_payload, find_objects  # noqa: E402

LD_JSON = re.compile(r"""<script[^>]+application/ld\+json[^>]*>(.*?)</script>""", re.DOTALL)
TITLE = re.compile(r"<title>(.*?)</title>", re.DOTALL)
DESCRIPTION = re.compile(r"""<meta\s+name=["']description["']\s+content=["'](.*?)["']""", re.DOTALL)
LISTING_LINK = re.compile(r"""property-listing/([^"'<>\\]{2,70})""")


def main(pattern: str = "*.html") -> None:
    files = sorted(pathlib.Path("data/raw/baanknet").rglob(pattern))
    if not files:
        print("nothing archived yet")
        return

    path = files[0]
    html = path.read_text("utf-8", errors="replace")
    print(f"file: {path.name}  ({len(html):,} chars)\n")

    print("=== JSON-LD blocks ===")
    for raw in LD_JSON.findall(html):
        try:
            obj = json.loads(raw)
        except json.JSONDecodeError as exc:
            print(f"  (unparseable: {exc})")
            continue
        print(f"  @type={obj.get('@type')}  keys={list(obj)[:14]}")
        if any(k in obj for k in ("address", "about", "offers")):
            print(json.dumps(obj, indent=2, ensure_ascii=False)[:1600])

    print("\n=== title / description ===")
    for regex in (TITLE, DESCRIPTION):
        match = regex.search(html)
        if match:
            print(f"  {match.group(1).strip()[:300]}")

    print("\n=== property-listing links (breadcrumbs) ===")
    for link in sorted(set(LISTING_LINK.findall(html)))[:12]:
        print(f"  {link}")

    print("\n=== breadcrumb trail ===")
    for raw in LD_JSON.findall(html):
        try:
            obj = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if obj.get("@type") == "BreadcrumbList":
            for item in obj.get("itemListElement", []):
                print(f"  {item.get('position')}. {item.get('name')}  {item.get('item', '')}")

    print("\n=== location fields on the property record ===")
    payload = extract_payload(html)
    records = find_objects(payload, "propertyDetailId")
    if records:
        record = max(records, key=len)
        for key in sorted(record):
            if any(
                token in key.lower()
                for token in (
                    "city",
                    "state",
                    "district",
                    "local",
                    "pin",
                    "address",
                    "bank",
                    "branch",
                    "type",
                    "lat",
                    "long",
                )
            ):
                value = record[key]
                print(f"  {key:<28} = {str(value)[:90]!r}")

        print("\n=== nested objects in full ===")
        for key in (
            "propertySubType",
            "propertyTypeDetails",
            "propertyPossessionType",
            "propertyTypeOfAction",
            "district",
            "city",
            "auctions",
            "auction",
        ):
            if key in record:
                print(f"  {key}:")
                print(
                    "    "
                    + json.dumps(record[key], indent=2, ensure_ascii=False)[:900].replace(
                        "\n", "\n    "
                    )
                )


if __name__ == "__main__":
    main(*sys.argv[1:])
