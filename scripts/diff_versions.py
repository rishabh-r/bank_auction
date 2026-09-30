"""Compare two archived copies of the same URL.

Used to work out why a page that has not really changed still produces
different bytes on every fetch, which would otherwise fill the archive
with near-identical copies.
"""

import difflib
import sys

sys.path.insert(0, "src")

from sqlalchemy import select  # noqa: E402

from auction_portal.db.models import SourceDocument  # noqa: E402
from auction_portal.db.session import get_sessionmaker  # noqa: E402
from auction_portal.storage.raw_store import RawStore  # noqa: E402


def main() -> None:
    store = RawStore()
    sessions = get_sessionmaker()

    with sessions() as session:
        url = session.scalar(
            select(SourceDocument.source_url)
            .where(SourceDocument.source_url.like("%property-detail%"))
            .group_by(SourceDocument.source_url)
            .having(__import__("sqlalchemy").func.count() > 1)
            .limit(1)
        )
        if not url:
            print("no url has more than one archived version")
            return

        docs = list(
            session.scalars(
                select(SourceDocument)
                .where(SourceDocument.source_url == url)
                .order_by(SourceDocument.fetched_at)
            )
        )

    print(f"{url}\n{len(docs)} versions\n")

    older = store.read(docs[0].storage_key).decode("utf-8", errors="replace")
    newer = store.read(docs[-1].storage_key).decode("utf-8", errors="replace")
    print(f"first : {docs[0].fetched_at}  {len(older):,} chars")
    print(f"last  : {docs[-1].fetched_at}  {len(newer):,} chars\n")

    if older == newer:
        print("identical - the difference must be elsewhere")
        return

    # Show only the changed fragments, trimmed. Whole lines are useless
    # here because the HTML is one enormous line.
    shown = 0
    matcher = difflib.SequenceMatcher(None, older, newer, autojunk=False)
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal" or shown >= 12:
            continue
        shown += 1
        print(f"--- {tag} ---")
        print(f"  was: {older[max(0, i1 - 60) : i2 + 60][:220]!r}")
        print(f"  now: {newer[max(0, j1 - 60) : j2 + 60][:220]!r}")
        print()


if __name__ == "__main__":
    main()
