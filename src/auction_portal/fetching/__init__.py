"""Fetching: everything that touches the network.

Deliberately isolated from parsing and storage. This layer's only job is to
retrieve bytes politely and hand them on unmodified.
"""

from auction_portal.fetching.client import Fetcher
from auction_portal.fetching.models import FetchOutcome, FetchResult, RawDocument
from auction_portal.fetching.robots import RobotsChecker
from auction_portal.fetching.throttle import DomainThrottle

__all__ = [
    "DomainThrottle",
    "FetchOutcome",
    "FetchResult",
    "Fetcher",
    "RawDocument",
    "RobotsChecker",
]
