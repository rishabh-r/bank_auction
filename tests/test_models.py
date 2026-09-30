"""Tests for fetched-document models."""

from datetime import UTC, datetime

import pytest

from auction_portal.fetching.models import FetchOutcome, FetchResult, RawDocument


def make_doc(content: bytes = b"hello", mime: str = "text/html") -> RawDocument:
    return RawDocument(
        source_id="test",
        url="https://example.com/notice",
        content=content,
        mime_type=mime,
        http_status=200,
        fetched_at=datetime(2026, 9, 26, 12, 0, tzinfo=UTC),
    )


def test_identical_bytes_give_identical_hash():
    assert make_doc(b"same").sha256 == make_doc(b"same").sha256


def test_one_changed_byte_changes_the_hash():
    """The whole change-detection scheme rests on this."""
    assert make_doc(b"Rs.3,37,55,000").sha256 != make_doc(b"Rs.3,37,54,000").sha256


def test_hash_is_the_known_sha256_of_the_content():
    # echo -n "hello" | sha256sum
    expected = "2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824"
    assert make_doc(b"hello").sha256 == expected


@pytest.mark.parametrize(
    ("mime", "extension"),
    [
        ("application/pdf", ".pdf"),
        ("text/html; charset=utf-8", ".html"),
        ("application/json", ".json"),
        ("TEXT/HTML", ".html"),
        ("application/octet-stream", ".bin"),
        ("something/unknown", ".bin"),
    ],
)
def test_extension_from_mime_type(mime, extension):
    assert make_doc(mime=mime).extension == extension


def test_visitor_counter_does_not_count_as_a_change():
    """BAANKNET renders a site-wide visitor counter into every page, so
    two fetches of an untouched listing differ by a few digits. Treating
    that as a change archived a fresh copy of every page every hour -
    about 630 MB a day carrying no information.
    """
    before = b'<span>Visitor Count:</span><span class="ml-1">2800055</span>'
    after = b'<span>Visitor Count:</span><span class="ml-1">2813191</span>'

    assert make_doc(before).sha256 != make_doc(after).sha256  # bytes differ
    assert make_doc(before).canonical_sha256 == make_doc(after).canonical_sha256


def test_a_real_change_is_still_detected():
    """The stripping must be narrow enough that a republished notice
    still registers. Hiding a change is far worse than a duplicate."""
    before = b"<span>Visitor Count:</span><span>2800055</span> Reserve Price Rs.3,37,55,000"
    after = b"<span>Visitor Count:</span><span>2813191</span> Reserve Price Rs.2,90,00,000"

    assert make_doc(before).canonical_sha256 != make_doc(after).canonical_sha256


def test_canonical_hash_equals_plain_hash_when_nothing_is_volatile():
    doc = make_doc(b"an ordinary notice with no counter")
    assert doc.canonical_sha256 == doc.sha256


def test_document_is_immutable():
    """Archived bytes must never be editable in place."""
    doc = make_doc()
    with pytest.raises((AttributeError, TypeError)):
        doc.content = b"tampered"


def test_size_reported_in_bytes():
    assert make_doc(b"12345").size_bytes == 5


def test_fetch_result_flags_new_content():
    assert FetchResult(FetchOutcome.NEW, "https://x.test").is_new_content
    assert not FetchResult(FetchOutcome.UNCHANGED, "https://x.test").is_new_content
