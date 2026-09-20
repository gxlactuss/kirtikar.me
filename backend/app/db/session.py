from typing import Generator
from sqlalchemy import create_engine
from sqlalchemy.pool import NullPool, StaticPool
from sqlalchemy.orm import sessionmaker, Session

from app.core.config import settings

def _engine_options(url: str) -> dict:
    """Connection options for the configured database.

    SQLite is here so the API can be run locally without a PostgreSQL server -
    handy on a laptop and for pointing a phone at a dev machine. FastAPI serves
    sync endpoints from a thread pool, so SQLite's default same-thread guard has
    to be lifted and the connection shared rather than pooled per thread.
    """
    if url.startswith("sqlite"):
        return {
            # `timeout` is how long a writer waits for the lock rather than
            # failing outright. The pipeline writes from a background thread
            # while the site polls /status every few seconds, so two writers
            # meeting is routine; the default of 5s is enough on a laptop and
            # not enough on a small shared container.
            "connect_args": {"check_same_thread": False, "timeout": 30},
            "poolclass": StaticPool if ":memory:" in url else NullPool,
        }
    return {"pool_pre_ping": True}


engine = create_engine(settings.DATABASE_URL, **_engine_options(settings.DATABASE_URL))

SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
)


def get_db() -> Generator[Session, None, None]:
    """Dependency for providing request-scoped database sessions."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
