"""Tests for per-domain rate limiting."""

import time

import pytest

from auction_portal.fetching.throttle import DomainThrottle


def test_rejects_impolite_default_delay():
    with pytest.raises(ValueError, match="at least 1 second"):
        DomainThrottle(0.2)


def test_first_request_to_a_domain_is_immediate():
    throttle = DomainThrottle(2.0)
    assert throttle.time_until_allowed("https://bank.test/a") == 0.0


def test_second_request_to_same_domain_must_wait():
    throttle = DomainThrottle(2.0)
    throttle.record_request("https://bank.test/a")
    assert throttle.time_until_allowed("https://bank.test/b") > 1.5


def test_different_domains_do_not_block_each_other():
    """A slow crawl of one bank must not hold up another."""
    throttle = DomainThrottle(2.0)
    throttle.record_request("https://bank-one.test/a")
    assert throttle.time_until_allowed("https://bank-two.test/a") == 0.0


def test_subdomains_are_treated_as_separate_hosts():
    throttle = DomainThrottle(2.0)
    throttle.record_request("https://hdfcbank.auctiontiger.test/a")
    assert throttle.time_until_allowed("https://sbi.auctiontiger.test/a") == 0.0


def test_wait_actually_sleeps():
    throttle = DomainThrottle(1.0)
    throttle.record_request("https://bank.test/a")
    started = time.monotonic()
    throttle.wait("https://bank.test/b")
    assert time.monotonic() - started >= 0.9


def test_site_requested_delay_is_honoured_when_stricter():
    throttle = DomainThrottle(2.0)
    throttle.set_domain_delay("https://bank.test/a", 10.0)
    assert throttle.delay_for("https://bank.test/a") == 10.0


def test_site_requested_delay_cannot_make_us_faster():
    """A site saying 'Crawl-delay: 0' does not license us to hammer it."""
    throttle = DomainThrottle(3.0)
    throttle.set_domain_delay("https://bank.test/a", 0.5)
    assert throttle.delay_for("https://bank.test/a") == 3.0


def test_relative_url_is_rejected():
    with pytest.raises(ValueError, match="absolute"):
        DomainThrottle(1.0).time_until_allowed("/notices/auction.pdf")
