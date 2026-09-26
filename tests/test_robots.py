"""Tests for robots.txt compliance."""

import httpx
import pytest

from auction_portal.fetching.robots import RobotsChecker

UA = "AuctionPortalBot/0.1 (+https://example.com/bot; bot@example.com)"

ROBOTS = """
User-agent: *
Disallow: /private/
Disallow: /admin
Crawl-delay: 7

User-agent: BadBot
Disallow: /
"""


@pytest.fixture
def mock_robots(monkeypatch):
    """Serve a canned robots.txt instead of hitting the network."""

    def install(body: str | None, status: int = 200, raise_error: bool = False):
        def fake_get(url, **kwargs):
            if raise_error:
                raise httpx.ConnectError("unreachable")
            return httpx.Response(
                status_code=status,
                text=body or "",
                request=httpx.Request("GET", url),
            )

        monkeypatch.setattr(httpx, "get", fake_get)

    return install


def test_allowed_path_is_permitted(mock_robots):
    mock_robots(ROBOTS)
    assert RobotsChecker(UA).is_allowed("https://bank.test/notices/auction.pdf")


def test_disallowed_path_is_blocked(mock_robots):
    mock_robots(ROBOTS)
    assert not RobotsChecker(UA).is_allowed("https://bank.test/private/data.json")


def test_site_crawl_delay_is_read(mock_robots):
    mock_robots(ROBOTS)
    assert RobotsChecker(UA).crawl_delay_for("https://bank.test/x") == 7.0


def test_missing_robots_txt_means_allowed(mock_robots):
    """404 is the normal case for most bank sites, and means 'no rules'."""
    mock_robots(None, status=404)
    assert RobotsChecker(UA).is_allowed("https://bank.test/anything")


def test_unreachable_robots_txt_does_not_crash(mock_robots):
    mock_robots(None, raise_error=True)
    assert RobotsChecker(UA).is_allowed("https://bank.test/anything")


def test_robots_is_fetched_once_per_domain(monkeypatch):
    """We must not request robots.txt before every single page."""
    calls = []

    def counting_get(url, **kwargs):
        calls.append(url)
        return httpx.Response(200, text=ROBOTS, request=httpx.Request("GET", url))

    monkeypatch.setattr(httpx, "get", counting_get)

    checker = RobotsChecker(UA)
    for n in range(5):
        checker.is_allowed(f"https://bank.test/notice-{n}.pdf")

    assert len(calls) == 1


def test_checking_can_be_disabled_for_tests(mock_robots):
    mock_robots(ROBOTS)
    checker = RobotsChecker(UA, enabled=False)
    assert checker.is_allowed("https://bank.test/private/data.json")
    assert checker.crawl_delay_for("https://bank.test/x") is None


def test_relative_url_is_rejected(mock_robots):
    mock_robots(ROBOTS)
    with pytest.raises(ValueError, match="absolute"):
        RobotsChecker(UA).is_allowed("/notices/auction.pdf")
