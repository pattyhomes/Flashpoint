from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.config import settings


def _resolve_database_url(url: str) -> str:
    """Resolve relative SQLite paths from the repo root, not process CWD."""
    if url == "sqlite:///:memory:":
        return url
    prefix = "sqlite:///"
    if not url.startswith(prefix) or url.startswith("sqlite:////"):
        return url
    raw_path = url.removeprefix(prefix)
    if raw_path.startswith("../data/"):
        repo_root = Path(__file__).resolve().parents[2]
        resolved = repo_root / "data" / raw_path.removeprefix("../data/")
        resolved.parent.mkdir(parents=True, exist_ok=True)
        return f"{prefix}{resolved}"
    db_path = Path(raw_path)
    if db_path.is_absolute():
        return url
    repo_root = Path(__file__).resolve().parents[2]
    resolved = repo_root / db_path
    resolved.parent.mkdir(parents=True, exist_ok=True)
    return f"{prefix}{resolved}"


# check_same_thread=False is required for SQLite when used with FastAPI.
# timeout=30 lets a second writer wait for the lock instead of failing
# immediately with "database is locked" — APScheduler ingest jobs and
# request handlers share this engine.
engine = create_engine(
    _resolve_database_url(settings.database_url),
    connect_args={"check_same_thread": False, "timeout": 30},
)


@event.listens_for(engine, "connect")
def _set_sqlite_pragma(dbapi_connection, _connection_record):
    """Enable WAL mode on every SQLite connection.

    WAL allows concurrent readers alongside a single writer (vs the
    default DELETE journal which blocks readers during writes). This is
    the canonical fix for 'database is locked' errors when multiple
    workers share a SQLite file. synchronous=NORMAL is the standard WAL
    pairing — durable enough for the ingest workload, faster than FULL.
    """
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA synchronous=NORMAL")
    cursor.close()


SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


def get_db():
    """FastAPI dependency: yields a database session, closes it when done."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    """Create all tables on app startup. Safe to call repeatedly."""
    from app import models  # noqa: F401 — registers models with Base
    Base.metadata.create_all(bind=engine)
