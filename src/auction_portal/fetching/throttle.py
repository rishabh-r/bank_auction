"""Per-domain rate limiting.

We wait between requests to the same host. Tracked per domain so that a slow
crawl of one bank does not hold up another.
"""

import logging
import threading
import time
from urllib.parse import urlparse

log = logging.getLogger(__name__)


class DomainThrottle:
    """Enforces a minimum interval between requests to any single domain."""

    def __init__(self, default_delay: float):
        if default_delay < 1.0:
            raise ValueError("crawl delay must be at least 1 second")
        self._default_delay = default_delay
        self._last_request: dict[str, float] = {}
        self._overrides: dict[str, float] = {}
        self._lock = threading.Lock()

    def set_domain_delay(self, url: str, delay: float) -> None:
        """Apply a stricter delay for one domain, e.g. from robots.txt Crawl-delay."""
        domain = self._domain(url)
        effective = max(delay, self._default_delay)
        if self._overrides.get(domain) != effective:
            log.debug("delay for %s set to %.1fs", domain, effective)
        self._overrides[domain] = effective

    def delay_for(self, url: str) -> float:
        return self._overrides.get(self._domain(url), self._default_delay)

    def time_until_allowed(self, url: str) -> float:
        """Seconds we still need to wait before requesting this URL."""
        domain = self._domain(url)
        with self._lock:
            last = self._last_request.get(domain)
        if last is None:
            return 0.0
        elapsed = time.monotonic() - last
        return max(0.0, self.delay_for(url) - elapsed)

    def wait(self, url: str) -> float:
        """Block until it is polite to request this URL. Returns seconds waited."""
        waited = self.time_until_allowed(url)
        if waited > 0:
            log.debug("waiting %.1fs before %s", waited, self._domain(url))
            time.sleep(waited)
        self.record_request(url)
        return waited

    def record_request(self, url: str) -> None:
        with self._lock:
            self._last_request[self._domain(url)] = time.monotonic()

    @staticmethod
    def _domain(url: str) -> str:
        netloc = urlparse(url).netloc.lower()
        if not netloc:
            raise ValueError(f"URL must be absolute, got: {url!r}")
        return netloc
