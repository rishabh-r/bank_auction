"""Tests for application configuration."""

import pytest
from pydantic import ValidationError

from auction_portal.config import Settings, get_settings

VALID = {
    "contact_email": "bot@example.com",
    "contact_url": "https://example.com/bot",
}


def test_settings_load_from_env_file():
    """The real .env parses and produces a usable Settings object."""
    settings = get_settings()
    assert settings.environment in ("development", "production")
    assert settings.contact_email


def test_get_settings_is_cached():
    """Settings are loaded once, not re-parsed on every call."""
    assert get_settings() is get_settings()


def test_user_agent_identifies_us():
    """Our User-Agent must carry a contact route, not be anonymous."""
    settings = Settings(**VALID)
    ua = settings.user_agent
    assert ua.startswith("AuctionPortalBot/")
    assert "bot@example.com" in ua
    assert "example.com/bot" in ua


def test_raw_dir_sits_under_data_dir(tmp_path):
    settings = Settings(**VALID, data_dir=tmp_path)
    assert settings.raw_dir == tmp_path / "raw"


def test_ensure_directories_creates_raw_dir(tmp_path):
    settings = Settings(**VALID, data_dir=tmp_path)
    assert not settings.raw_dir.exists()
    settings.ensure_directories()
    assert settings.raw_dir.is_dir()


def test_ensure_directories_is_idempotent(tmp_path):
    """Running twice must not fail. Every task in this system is re-runnable."""
    settings = Settings(**VALID, data_dir=tmp_path)
    settings.ensure_directories()
    settings.ensure_directories()
    assert settings.raw_dir.is_dir()


def test_crawler_delay_cannot_be_impolite():
    """A sub-second delay is rejected at startup, not discovered in production."""
    with pytest.raises(ValidationError):
        Settings(**VALID, crawler_delay_seconds=0.1)


def test_invalid_email_is_rejected():
    with pytest.raises(ValidationError):
        Settings(contact_email="not-an-email", contact_url="https://example.com/bot")


def test_unknown_setting_is_rejected():
    """A typo'd key must fail loudly rather than be silently ignored."""
    with pytest.raises(ValidationError):
        Settings(**VALID, crawler_delay_second=3.0)  # note: missing 's'
