"""Copy an archived document into the test fixture corpus.

The fixture corpus is real documents with hand-verified expected output.
Every parser change runs against it in CI, which is what stops a fix for
one source silently breaking another.

    python scripts/make_fixture.py <external_id> <name>
"""

import shutil
import sys
from pathlib import Path

sys.path.insert(0, "src")

from auction_portal.sources.flight import extract_payload, find_objects  # noqa: E402

RAW = Path("data/raw/baanknet")
FIXTURES = Path("tests/fixtures/baanknet")


def main(external_id: str, name: str) -> None:
    FIXTURES.mkdir(parents=True, exist_ok=True)

    for path in sorted(RAW.rglob("*.html")):
        html = path.read_text("utf-8", errors="replace")
        records = find_objects(extract_payload(html), "propertyDetailId")
        if not records:
            continue
        if str(max(records, key=len).get("propertyDetailId")) != external_id:
            continue

        target = FIXTURES / f"{name}.html"
        shutil.copy2(path, target)
        print(f"{external_id} -> {target}  ({target.stat().st_size / 1024:.0f} KB)")
        return

    print(f"no archived document found for property {external_id}")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
