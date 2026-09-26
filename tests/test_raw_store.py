"""Tests for the immutable raw archive."""

from datetime import UTC, datetime

from auction_portal.fetching.models import RawDocument
from auction_portal.storage.raw_store import RawStore


def make_doc(content=b"notice", source_id="hdfc", mime="application/pdf", day=26):
    return RawDocument(
        source_id=source_id,
        url="https://bank.test/notice.pdf",
        content=content,
        mime_type=mime,
        http_status=200,
        fetched_at=datetime(2026, 9, day, 12, 0, tzinfo=UTC),
    )


def test_save_writes_the_exact_bytes(settings):
    store = RawStore(settings)
    doc = make_doc(b"%PDF-1.4 auction notice")

    key = store.save(doc)

    assert store.read(key) == b"%PDF-1.4 auction notice"


def test_storage_path_is_date_partitioned(settings):
    key = RawStore(settings).save(make_doc())
    assert key.startswith("hdfc/2026/09/26/")
    assert key.endswith(".pdf")


def test_filename_is_the_content_hash(settings):
    doc = make_doc()
    key = RawStore(settings).save(doc)
    assert doc.sha256 in key


def test_metadata_sidecar_records_provenance(settings):
    store = RawStore(settings)
    key = store.save(make_doc())

    meta = store.metadata(key)

    assert meta["url"] == "https://bank.test/notice.pdf"
    assert meta["source_id"] == "hdfc"
    assert meta["http_status"] == 200
    assert meta["sha256"]
    assert meta["fetched_at"].startswith("2026-09-26")
    assert "content" not in meta  # bytes live in the file, not the sidecar


def test_saving_identical_content_twice_is_a_no_op(settings):
    store = RawStore(settings)
    doc = make_doc(b"same bytes")

    first = store.save(doc)
    second = store.save(doc)

    assert first == second
    assert store.count() == 1


def test_different_content_produces_a_different_file(settings):
    """A corrigendum changing the reserve price must not overwrite the original."""
    store = RawStore(settings)

    original = store.save(make_doc(b"Reserve Price Rs.3,37,55,000"))
    revised = store.save(make_doc(b"Reserve Price Rs.2,90,00,000"))

    assert original != revised
    assert store.count() == 2
    # The original is still readable, unchanged.
    assert store.read(original) == b"Reserve Price Rs.3,37,55,000"


def test_contains_hash_finds_content_from_any_date(settings):
    store = RawStore(settings)
    doc = make_doc(b"content", day=1)
    store.save(doc)

    assert store.contains_hash("hdfc", doc.sha256)
    assert not store.contains_hash("hdfc", "0" * 64)
    assert not store.contains_hash("other_bank", doc.sha256)


def test_count_can_be_filtered_by_source(settings):
    store = RawStore(settings)
    store.save(make_doc(b"a", source_id="hdfc"))
    store.save(make_doc(b"b", source_id="hdfc"))
    store.save(make_doc(b"c", source_id="ibbi"))

    assert store.count() == 3
    assert store.count("hdfc") == 2
    assert store.count("ibbi") == 1


def test_no_partial_files_left_behind(settings):
    """Writes are atomic, so a crash cannot leave a truncated archive."""
    store = RawStore(settings)
    store.save(make_doc())
    assert not any(settings.raw_dir.rglob("*.part"))


def test_count_is_zero_on_a_fresh_archive(settings):
    assert RawStore(settings).count() == 0
