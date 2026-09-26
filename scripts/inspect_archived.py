"""Inspect an archived document without re-fetching it.

Reads from data/raw, so it costs the source nothing. Useful when working
out what an adapter should extract.

    python scripts/inspect_archived.py <source_id> [required_key]
"""

import json
import pathlib
import sys

sys.path.insert(0, "src")

from auction_portal.sources.flight import extract_payload, find_objects  # noqa: E402

INTERESTING = (
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
    "price",
    "reserve",
    "emd",
    "brand",
    "model",
    "registration",
    "possession",
    "npa",
    "auction",
)


def main(source_id: str = "baanknet", key: str = "propertyDetailId") -> None:
    files = sorted(pathlib.Path(f"data/raw/{source_id}").rglob("*.html"))
    if not files:
        print(f"nothing archived for {source_id}")
        return

    path = files[0]
    html = path.read_text("utf-8", errors="replace")
    payload = extract_payload(html)
    print(f"file    : {path.name}")
    print(f"payload : {len(payload):,} chars\n")

    records = find_objects(payload, key)
    if not records:
        print(f"no object contains {key!r}")
        print("keys present in the largest objects:")
        for probe in ("vehicleId", "auctionId", "reservePrice", "id"):
            found = find_objects(payload, probe)
            if found:
                print(f"  {probe}: {len(found)} objects -> {list(max(found, key=len))[:30]}")
        return

    record = max(records, key=len)
    print(f"record has {len(record)} fields\n")
    for name in sorted(record):
        if any(token in name.lower() for token in INTERESTING):
            value = record[name]
            rendered = json.dumps(value, ensure_ascii=False) if isinstance(value, dict) else value
            print(f"  {name:<26} = {str(rendered)[:95]}")


if __name__ == "__main__":
    main(*sys.argv[1:])
