"""Shared test fixtures."""

import pytest
from sqlalchemy import text
from sqlalchemy.orm import sessionmaker

from auction_portal.config import Settings
from auction_portal.db.models import Base
from auction_portal.db.session import build_engine


@pytest.fixture
def settings(tmp_path):
    """Settings pointed at a throwaway directory and the test database."""
    return Settings(
        contact_email="bot@example.com",
        contact_url="https://example.com/bot",
        data_dir=tmp_path,
        crawler_delay_seconds=1.0,
        crawler_max_retries=2,
        crawler_respect_robots=False,  # enabled explicitly in robots tests
    )


@pytest.fixture(scope="session")
def engine():
    """Engine for the dedicated test database.

    Skips the whole suite politely if no database is running, rather than
    failing with a confusing connection error.
    """
    settings = Settings(contact_email="bot@example.com", contact_url="https://example.com/bot")
    url = settings.test_database_url.get_secret_value()
    engine = build_engine(url)
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
    except Exception as exc:
        pytest.skip(
            f"test database unavailable ({type(exc).__name__}). "
            "Start it with: python scripts/setup_postgres.py --start"
        )
    yield engine
    engine.dispose()


@pytest.fixture
def db_session_factory(engine):
    """A clean schema for every test.

    Dropping and recreating is fast here and guarantees no test can be
    affected by another's leftovers.
    """
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    yield sessionmaker(bind=engine, expire_on_commit=False)
    Base.metadata.drop_all(engine)


@pytest.fixture
def db_session(db_session_factory):
    session = db_session_factory()
    try:
        yield session
        session.commit()
    finally:
        session.close()
