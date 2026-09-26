"""robots.txt compliance.

Checked before every request. A site that has asked not to be crawled is not
crawled - this is both basic courtesy and a material part of our legal
position (see Part E of the project docs).
"""

import logging
import time
from dataclasses import dataclass
from urllib.parse import urljoin, urlparse
from urllib.robotparser import RobotFileParser

import httpx

log = logging.getLogger(__name__)

# Re-read a site's robots.txt at most this often.
_CACHE_TTL_SECONDS = 3600


@dataclass(slots=True)
class _CachedRules:
    parser: RobotFileParser | None
    fetched_at: float
    # Some sites publish a Crawl-delay directive; we honour it when it is
    # stricter than our own configured delay.
    crawl_delay: float | None = None

    def is_stale(self) -> bool:
        return (time.monotonic() - self.fetched_at) > _CACHE_TTL_SECONDS


class RobotsChecker:
    """Fetches and caches robots.txt per domain."""

    def __init__(self, user_agent: str, timeout: float = 10.0, enabled: bool = True):
        self._user_agent = user_agent
        self._timeout = timeout
        self._enabled = enabled
        self._cache: dict[str, _CachedRules] = {}

    def is_allowed(self, url: str) -> bool:
        """May we fetch this URL?"""
        if not self._enabled:
            return True
        rules = self._rules_for(url)
        if rules.parser is None:
            # No usable robots.txt. Per the standard, absence means allowed.
            return True
        return rules.parser.can_fetch(self._user_agent, url)

    def crawl_delay_for(self, url: str) -> float | None:
        """Site-requested delay in seconds, if it published one."""
        if not self._enabled:
            return None
        return self._rules_for(url).crawl_delay

    def _rules_for(self, url: str) -> _CachedRules:
        origin = self._origin(url)
        cached = self._cache.get(origin)
        if cached is not None and not cached.is_stale():
            return cached

        rules = self._load(origin)
        self._cache[origin] = rules
        return rules

    def _load(self, origin: str) -> _CachedRules:
        robots_url = urljoin(origin, "/robots.txt")
        now = time.monotonic()

        try:
            response = httpx.get(
                robots_url,
                timeout=self._timeout,
                headers={"User-Agent": self._user_agent},
                follow_redirects=True,
            )
        except httpx.HTTPError as exc:
            # Unreachable robots.txt. Treat as "no rules" rather than blocking
            # ourselves entirely, but log it so repeated failures are visible.
            log.warning("robots.txt unreachable for %s: %s", origin, exc)
            return _CachedRules(parser=None, fetched_at=now)

        if response.status_code == 404:
            log.debug("no robots.txt at %s - crawling permitted", origin)
            return _CachedRules(parser=None, fetched_at=now)

        if response.status_code >= 400:
            log.warning("robots.txt returned %s for %s", response.status_code, origin)
            return _CachedRules(parser=None, fetched_at=now)

        parser = RobotFileParser()
        parser.parse(response.text.splitlines())

        delay = parser.crawl_delay(self._user_agent)
        return _CachedRules(
            parser=parser,
            fetched_at=now,
            crawl_delay=float(delay) if delay is not None else None,
        )

    @staticmethod
    def _origin(url: str) -> str:
        parts = urlparse(url)
        if not parts.scheme or not parts.netloc:
            raise ValueError(f"URL must be absolute, got: {url!r}")
        return f"{parts.scheme}://{parts.netloc}"
