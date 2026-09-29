"""Database connections and sessions."""

import logging
from collections.abc import Iterator
from contextlib import contextmanager
from functools import lru_cache

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import NullPool

from auction_portal.config import Settings, get_settings

log = logging.getLogger(__name__)


def build_engine(url: str, echo: bool = False, serverless: bool = False) -> Engine:
    if serverless:
        # Serverless functions are short-lived and numerous. Holding a
        # pool per instance would exhaust the database's connection limit
        # long before traffic justified it, so each request opens and
        # closes its own connection and we let the provider's pooler do
        # the pooling.
        return create_engine(url, echo=echo, poolclass=NullPool, pool_pre_ping=True)

    return create_engine(
        url,
        echo=echo,
        # Verify a pooled connection is alive before handing it out, so a
        # database restart or an idle timeout does not surface as an error
        # in the middle of a crawl.
        pool_pre_ping=True,
        pool_size=5,
        max_overflow=10,
    )


# No arguments: Settings is not hashable, and get_settings() is already
# cached, so there is nothing to parameterise. Tests inject their own
# session factory rather than reconfiguring this one.
@lru_cache(maxsize=1)
def get_engine() -> Engine:
    settings: Settings = get_settings()
    log.debug("connecting to %s", settings.safe_database_url)
    return build_engine(
        settings.database_url.get_secret_value(),
        echo=settings.db_echo,
        serverless=settings.db_serverless,
    )


@lru_cache(maxsize=1)
def get_sessionmaker() -> sessionmaker[Session]:
    return sessionmaker(bind=get_engine(), expire_on_commit=False)


@contextmanager
def session_scope(factory: sessionmaker[Session] | None = None) -> Iterator[Session]:
    """A transaction. Commits on success, rolls back on any exception.

    Using this everywhere means a failure mid-crawl can never leave the
    database holding half of an update.
    """
    session = (factory or get_sessionmaker())()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
