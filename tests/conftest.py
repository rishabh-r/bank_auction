"""Shared test fixtures."""

import pytest

from auction_portal.config import Settings


@pytest.fixture
def settings(tmp_path):
    """Settings pointed at a throwaway directory, with no real network delay."""
    return Settings(
        contact_email="bot@example.com",
        contact_url="https://example.com/bot",
        data_dir=tmp_path,
        crawler_delay_seconds=1.0,
        crawler_max_retries=2,
        crawler_respect_robots=False,  # enabled explicitly in robots tests
    )
