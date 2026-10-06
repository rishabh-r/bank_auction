"""Copy listings from the local database to a remote one.

Used when moving to hosted Postgres, so coverage built up locally is not
thrown away and re-crawled over the following fortnight.

Copies the tables that represent collected data. Deliberately skips
source_documents and url_state: those point at an archive of raw files
that is not moving with us, and carrying the pointers without the files
would leave the remote database describing documents it cannot produce.
The collector rebuilds that state naturally as it crawls.

    python scripts/copy_to_remote.py            # dry run, reports counts
    python scripts/copy_to_remote.py --apply
"""

import argparse
import sys

sys.path.insert(0, "src")

from sqlalchemy import func, select  # noqa: E402

# The PostgreSQL dialect's insert, not the generic one: only this has
# on_conflict_do_nothing.
from sqlalchemy.dialects.postgresql import insert  # noqa: E402

from auction_portal.config import get_settings  # noqa: E402
from auction_portal.db.models import Listing, ListingRevision  # noqa: E402
from auction_portal.db.session import build_engine  # noqa: E402

LOCAL = "postgresql+psycopg://postgres:devpassword@localhost:5433/auction_portal"

#: Order matters: revisions reference listings.
TABLES = (Listing, ListingRevision)

BATCH = 500


def count(engine, model) -> int:
    with engine.connect() as connection:
        return connection.scalar(select(func.count()).select_from(model)) or 0


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="actually copy")
    parser.add_argument("--local", default=LOCAL)
    args = parser.parse_args()

    remote_url = get_settings().database_url.get_secret_value()
    if "localhost" in remote_url:
        sys.exit("DATABASE_URL still points at localhost; nothing to copy to.")

    source = build_engine(args.local)
    target = build_engine(remote_url)

    print(f"from : {args.local.split('@')[-1]}")
    print(f"to   : {remote_url.split('@')[-1].split('?')[0]}\n")

    for model in TABLES:
        print(
            f"  {model.__tablename__:20s} local {count(source, model):>6,}"
            f"   remote {count(target, model):>6,}"
        )

    if not args.apply:
        print("\nDry run. Re-run with --apply to copy.")
        return

    print()
    for model in TABLES:
        columns = [c.name for c in model.__table__.columns if c.name != "search_vector"]
        copied = 0

        with source.connect() as reader, target.begin() as writer:
            rows = reader.execute(select(*[model.__table__.c[c] for c in columns]))
            while chunk := rows.fetchmany(BATCH):
                payload = [dict(zip(columns, row, strict=True)) for row in chunk]
                # The archive is not moving with us, so these pointers
                # would reference rows that do not exist. Provenance is
                # preserved by canonical_url on the listing itself.
                for row in payload:
                    row["source_document_id"] = None
                # Existing rows win: re-running must not duplicate or
                # clobber anything the remote collector has since found.
                writer.execute(insert(model.__table__).on_conflict_do_nothing(), payload)
                copied += len(payload)
                print(f"\r  {model.__tablename__}: {copied:,}", end="")
        print()

    print("\nafter:")
    for model in TABLES:
        print(f"  {model.__tablename__:20s} {count(target, model):>6,}")


if __name__ == "__main__":
    main()
