"""Tests for database access, against a real PostgreSQL test database."""

from datetime import UTC, datetime

import pytest
from sqlalchemy.exc import IntegrityError

from auction_portal.db.models import SourceDocument
from auction_portal.db.repository import DocumentRepository
from auction_portal.fetching.models import RawDocument

URL = "https://bank.test/notices/auction.pdf"


def make_doc(content=b"notice v1", url=URL, source_id="testbank", etag=None):
    return RawDocument(
        source_id=source_id,
        url=url,
        content=content,
        mime_type="application/pdf",
        http_status=200,
        fetched_at=datetime.now(UTC),
        etag=etag,
    )


def test_recording_a_document_creates_both_rows(db_session):
    repo = DocumentRepository(db_session)
    doc = make_doc()

    record, changed = repo.record_document(doc, "key/1.pdf")
    db_session.flush()

    assert changed is True
    assert record.content_sha256 == doc.sha256
    assert record.size_bytes == len(doc.content)

    state = repo.get_url_state(URL)
    assert state.content_sha256 == doc.sha256
    assert state.fetch_count == 1
    assert state.unchanged_streak == 0


def test_recording_identical_content_twice_adds_no_row(db_session):
    """Idempotency: a retried task must not duplicate anything."""
    repo = DocumentRepository(db_session)
    doc = make_doc()

    repo.record_document(doc, "key/1.pdf")
    db_session.flush()
    _, changed = repo.record_document(doc, "key/1.pdf")
    db_session.flush()

    assert changed is False
    assert repo.count_documents() == 1
    assert repo.get_url_state(URL).fetch_count == 2
    assert repo.get_url_state(URL).unchanged_streak == 1


def test_changed_content_creates_a_second_document(db_session):
    """A corrigendum must not destroy the notice it corrects."""
    repo = DocumentRepository(db_session)

    original = make_doc(b"Reserve Price Rs.3,37,55,000")
    repo.record_document(original, "key/original.pdf")
    db_session.flush()

    revised = make_doc(b"Reserve Price Rs.2,90,00,000")
    _, changed = repo.record_document(revised, "key/revised.pdf")
    db_session.flush()

    assert changed is True
    assert repo.count_documents() == 2
    # The original row is still there, untouched.
    assert repo.get_document_by_hash(URL, original.sha256) is not None
    # url_state now points at the newer one.
    assert repo.get_url_state(URL).content_sha256 == revised.sha256
    assert repo.get_url_state(URL).unchanged_streak == 0


def test_unique_constraint_blocks_duplicate_rows(db_session):
    """The database itself is the last line of defence, not just our code."""
    db_session.add(
        SourceDocument(
            source_id="x",
            source_url=URL,
            fetched_at=datetime.now(UTC),
            content_sha256="a" * 64,
            storage_key="k1",
        )
    )
    db_session.flush()

    db_session.add(
        SourceDocument(
            source_id="x",
            source_url=URL,
            fetched_at=datetime.now(UTC),
            content_sha256="a" * 64,
            storage_key="k2",
        )
    )
    with pytest.raises(IntegrityError):
        db_session.flush()
    # The transaction is now poisoned; unwind it so teardown can run.
    db_session.rollback()


def test_touch_records_a_304_check(db_session):
    repo = DocumentRepository(db_session)
    repo.record_document(make_doc(), "key/1.pdf")
    db_session.flush()

    repo.touch_url(URL)
    repo.touch_url(URL)
    db_session.flush()

    state = repo.get_url_state(URL)
    assert state.fetch_count == 3
    assert state.unchanged_streak == 2


def test_touch_on_unknown_url_is_harmless(db_session):
    DocumentRepository(db_session).touch_url("https://never.seen/x.pdf")


def test_same_content_at_different_urls_is_kept_separately(db_session):
    """Two banks can publish byte-identical notices; both must be recorded."""
    repo = DocumentRepository(db_session)
    repo.record_document(make_doc(url="https://a.test/n.pdf"), "k/a.pdf")
    repo.record_document(make_doc(url="https://b.test/n.pdf"), "k/b.pdf")
    db_session.flush()

    assert repo.count_documents() == 2
    assert repo.count_urls() == 2


def test_counts_can_be_filtered_by_source(db_session):
    repo = DocumentRepository(db_session)
    repo.record_document(make_doc(b"a", "https://x.test/1", "hdfc"), "k/1")
    repo.record_document(make_doc(b"b", "https://x.test/2", "hdfc"), "k/2")
    repo.record_document(make_doc(b"c", "https://x.test/3", "ibbi"), "k/3")
    db_session.flush()

    assert repo.count_documents() == 3
    assert repo.count_documents("hdfc") == 2
    assert repo.documents_per_source() == {"hdfc": 2, "ibbi": 1}


def test_etag_is_stored_for_the_next_conditional_request(db_session):
    repo = DocumentRepository(db_session)
    repo.record_document(make_doc(etag='"v1"'), "key/1.pdf")
    db_session.flush()

    assert repo.get_url_state(URL).etag == '"v1"'


def test_recent_documents_are_newest_first(db_session):
    repo = DocumentRepository(db_session)
    for n in range(3):
        repo.record_document(make_doc(f"doc{n}".encode(), f"https://x.test/{n}"), f"k/{n}")
    db_session.flush()

    recent = repo.recent_documents(limit=2)
    assert len(recent) == 2
    assert recent[0].fetched_at >= recent[1].fetched_at
