"""Logging configuration.

Call configure_logging() once at the start of any entry point. Everywhere
else, just use logging.getLogger(__name__) and log normally.
"""

import logging
import sys

from auction_portal.config import get_settings

_LOG_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)-32s | %(message)s"
_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

_configured = False


def configure_logging(level: str | None = None) -> None:
    """Set up root logging. Safe to call more than once."""
    global _configured
    if _configured:
        return

    settings = get_settings()
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter(_LOG_FORMAT, datefmt=_DATE_FORMAT))

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level or settings.log_level)

    # Third-party libraries are chatty at DEBUG; keep them at WARNING.
    for noisy in ("urllib3", "httpx", "httpcore", "asyncio"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    _configured = True
