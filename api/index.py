"""Vercel entry point.

Vercel looks for an ASGI application called `app` in this file. Only the
read side of the project runs here: serving pages and the JSON API.

The collector deliberately does not run on Vercel. A crawl takes over an
hour and writes an archive to disk, and serverless functions have neither
the time nor a filesystem. See docs/VERCEL.md.

`src` is added to the path rather than installing the package, so the
templates and stylesheet resolve from the deployed source tree.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from auction_portal.web.app import app  # noqa: E402

__all__ = ["app"]
