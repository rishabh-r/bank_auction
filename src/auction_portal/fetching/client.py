"""The HTTP client.

Responsibilities, and nothing beyond them:
  - refuse to fetch what robots.txt disallows
  - wait its turn (per-domain throttle)
  - identify itself honestly
  - retry transient failures with exponential backoff, honouring Retry-After
  - avoid re-downloading unchanged content (conditional GET)

It does not parse, store, or interpret anything.
"""

import logging
import random
import time

import httpx

from auction_portal.config import Settings, get_settings
from auction_portal.fetching.models import FetchOutcome, FetchResult, RawDocument
from auction_portal.fetching.robots import RobotsChecker
from auction_portal.fetching.throttle import DomainThrottle

log = logging.getLogger(__name__)

# Status codes worth trying again: rate limiting and transient server faults.
RETRYABLE_STATUS = frozenset({429, 500, 502, 503, 504, 507, 522, 524})

# Never wait longer than this for a single retry, even if asked to.
MAX_BACKOFF_SECONDS = 120.0


class Fetcher:
    """Polite HTTP client for auction sources."""

    def __init__(
        self,
        settings: Settings | None = None,
        client: httpx.Client | None = None,
        robots: RobotsChecker | None = None,
        throttle: DomainThrottle | None = None,
    ):
        self._settings = settings or get_settings()
        self._owns_client = client is None
        self._client = client or httpx.Client(
            timeout=self._settings.crawler_timeout_seconds,
            follow_redirects=True,
        )
        self._robots = robots or RobotsChecker(
            user_agent=self._settings.user_agent,
            timeout=self._settings.crawler_timeout_seconds,
            enabled=self._settings.crawler_respect_robots,
        )
        self._throttle = throttle or DomainThrottle(self._settings.crawler_delay_seconds)

    def fetch(
        self,
        url: str,
        source_id: str,
        etag: str | None = None,
        last_modified: str | None = None,
    ) -> FetchResult:
        """Retrieve one URL.

        Pass etag/last_modified from a previous fetch to let the server tell
        us "not modified" instead of resending the body.
        """
        if not self._robots.is_allowed(url):
            log.warning("robots.txt disallows %s - skipping", url)
            return FetchResult(outcome=FetchOutcome.BLOCKED_BY_ROBOTS, url=url)

        if (site_delay := self._robots.crawl_delay_for(url)) is not None:
            self._throttle.set_domain_delay(url, site_delay)

        # Set per request, not on the client, so we always identify ourselves
        # regardless of how the client was constructed.
        headers: dict[str, str] = {
            "User-Agent": self._settings.user_agent,
            "Accept": "*/*",
            "Accept-Language": "en-IN,en;q=0.9",
        }
        if etag:
            headers["If-None-Match"] = etag
        if last_modified:
            headers["If-Modified-Since"] = last_modified

        last_error: str | None = None

        for attempt in range(self._settings.crawler_max_retries + 1):
            self._throttle.wait(url)

            try:
                response = self._client.get(url, headers=headers)
            except httpx.HTTPError as exc:
                last_error = f"{type(exc).__name__}: {exc}"
                log.warning("attempt %d for %s failed: %s", attempt + 1, url, last_error)
                if attempt < self._settings.crawler_max_retries:
                    time.sleep(self._backoff(attempt))
                continue

            if response.status_code == 304:
                log.info("not modified: %s", url)
                return FetchResult(outcome=FetchOutcome.NOT_MODIFIED, url=url)

            if response.status_code in RETRYABLE_STATUS:
                last_error = f"HTTP {response.status_code}"
                if attempt < self._settings.crawler_max_retries:
                    wait = self._retry_after(response) or self._backoff(attempt)
                    log.warning("%s for %s - retrying in %.1fs", last_error, url, wait)
                    time.sleep(wait)
                    continue
                log.error("%s for %s - giving up", last_error, url)
                break

            if response.status_code >= 400:
                # 404, 403 and friends: a real answer, not a transient fault.
                log.error("HTTP %s for %s", response.status_code, url)
                return FetchResult(
                    outcome=FetchOutcome.FAILED,
                    url=url,
                    error=f"HTTP {response.status_code}",
                )

            document = RawDocument(
                source_id=source_id,
                url=str(response.url),
                content=response.content,
                mime_type=response.headers.get("content-type", "application/octet-stream"),
                http_status=response.status_code,
                etag=response.headers.get("etag"),
                last_modified=response.headers.get("last-modified"),
            )
            log.info(
                "fetched %s (%s, %.1f KB, sha256=%s)",
                url,
                document.mime_type.split(";")[0],
                document.size_bytes / 1024,
                document.sha256[:12],
            )
            return FetchResult(outcome=FetchOutcome.NEW, url=url, document=document)

        return FetchResult(outcome=FetchOutcome.FAILED, url=url, error=last_error)

    @staticmethod
    def _backoff(attempt: int) -> float:
        """Exponential backoff with jitter, so retries do not synchronise."""
        base = min(2.0**attempt, MAX_BACKOFF_SECONDS)
        return base * (0.5 + random.random() / 2)  # noqa: S311 - not cryptographic

    @staticmethod
    def _retry_after(response: httpx.Response) -> float | None:
        """Honour a server's explicit Retry-After instruction."""
        value = response.headers.get("retry-after")
        if not value:
            return None
        try:
            return min(float(value), MAX_BACKOFF_SECONDS)
        except ValueError:
            return None  # HTTP-date form; fall back to our own backoff

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def __enter__(self) -> "Fetcher":
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()
