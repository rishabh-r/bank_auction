"""Application configuration.

Every setting is read from the environment (or the .env file), never hardcoded.
Settings are validated at startup, so a misconfigured deployment fails loudly
and immediately rather than halfway through a crawl.
"""

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import EmailStr, Field, HttpUrl, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        # A typo'd key in .env raises an error instead of being silently ignored.
        extra="forbid",
    )

    environment: Literal["development", "production"] = "development"
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"

    # Where downloaded auction documents are archived. Kept outside the
    # repository because it is large and always re-fetchable.
    data_dir: Path = PROJECT_ROOT / "data"

    # --- Crawler identity -------------------------------------------------
    # We identify ourselves honestly on every request. A crawler that can be
    # contacted usually gets left alone; an anonymous one gets blocked.
    bot_name: str = "AuctionPortalBot"
    bot_version: str = "0.1"
    contact_email: EmailStr
    contact_url: HttpUrl

    # --- Crawler politeness -----------------------------------------------
    crawler_delay_seconds: float = Field(default=3.0, ge=1.0)
    crawler_timeout_seconds: float = Field(default=30.0, gt=0)
    crawler_max_retries: int = Field(default=3, ge=0, le=10)
    crawler_respect_robots: bool = True

    # URLs per source per scheduled run.
    #
    # Sized against the crawl delay: at one request every 3 seconds, 1500
    # URLs is about 75 minutes of work, four times a day. That reaches full
    # coverage of BAANKNET's ~72,000 properties in roughly a fortnight,
    # while averaging well under one request per second - a rate a national
    # portal will not notice. Lower it if a source asks us to slow down.
    crawl_batch_size: int = Field(default=1500, ge=1)

    # --- Database ---------------------------------------------------------
    # Contains a password, so it is handled as a secret.
    database_url: SecretStr = SecretStr(
        "postgresql+psycopg://postgres:devpassword@localhost:5433/auction_portal"
    )
    # Used only by the test suite, which wipes it between runs.
    test_database_url: SecretStr = SecretStr(
        "postgresql+psycopg://postgres:devpassword@localhost:5433/auction_portal_test"
    )
    db_echo: bool = False  # set true to log every SQL statement

    # Set true on serverless hosts such as Vercel. Each instance then
    # opens and closes its own connection instead of holding a pool,
    # which would otherwise exhaust the database's connection limit
    # across many short-lived instances.
    db_serverless: bool = False

    # Read by docker-compose.yml, not by the application. Declared here so
    # that a .env copied from .env.example still validates - extra="forbid"
    # would otherwise reject it.
    postgres_password: SecretStr | None = None

    # --- API keys ---------------------------------------------------------
    # SecretStr keeps the value out of logs, tracebacks and repr() output.
    # Read it deliberately with .get_secret_value(); it cannot leak by accident.
    # Not needed until Phase 2 (LLM-assisted extraction from PDF notices).
    openai_api_key: SecretStr | None = None

    @field_validator("openai_api_key", mode="before")
    @classmethod
    def _blank_is_unset(cls, value: object) -> object:
        """Treat `OPENAI_API_KEY=` in .env as absent rather than an empty key."""
        return None if value in ("", None) else value

    @property
    def safe_database_url(self) -> str:
        """Connection string with the password masked, for logs and CLI output."""
        url = self.database_url.get_secret_value()
        if "://" in url and "@" in url:
            scheme, rest = url.split("://", 1)
            credentials, host = rest.rsplit("@", 1)
            user = credentials.split(":", 1)[0]
            return f"{scheme}://{user}:***@{host}"
        return url

    @property
    def raw_dir(self) -> Path:
        """Immutable archive of everything downloaded. Never overwritten."""
        return self.data_dir / "raw"

    @property
    def user_agent(self) -> str:
        """The User-Agent sent with every outbound request."""
        return f"{self.bot_name}/{self.bot_version} (+{self.contact_url}; {self.contact_email})"

    @property
    def is_production(self) -> bool:
        return self.environment == "production"

    def ensure_directories(self) -> None:
        """Create runtime directories if they do not yet exist."""
        self.raw_dir.mkdir(parents=True, exist_ok=True)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Load settings once and reuse. Import this, not Settings directly."""
    return Settings()
