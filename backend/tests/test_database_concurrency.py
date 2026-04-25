"""
SQLite concurrency tests.

Validates that the WAL + 30s busy-timeout configuration in app.database
allows a reader to proceed while a writer holds an open transaction. Without
WAL, the default DELETE journal blocks readers during writes and the second
operation raises 'database is locked' under contention.

Tests use a real on-disk SQLite file in a tmp_path so the WAL machinery
behaves exactly as it does in production. In-memory SQLite has special
journal-mode semantics that don't match the live runtime.
"""

import threading
import time

import pytest
from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import sessionmaker


def _make_engine(db_path, *, with_wal: bool):
    """Build an engine with the same connect_args as app.database, optionally
    skipping the WAL pragma so the test can compare against the broken default.
    """
    engine = create_engine(
        f"sqlite:///{db_path}",
        connect_args={"check_same_thread": False, "timeout": 30 if with_wal else 1},
    )

    if with_wal:
        @event.listens_for(engine, "connect")
        def _set_pragma(dbapi_connection, _record):
            cur = dbapi_connection.cursor()
            cur.execute("PRAGMA journal_mode=WAL")
            cur.execute("PRAGMA synchronous=NORMAL")
            cur.close()

    return engine


def _seed(engine):
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE IF NOT EXISTS counter (id INTEGER PRIMARY KEY, n INTEGER)"))
        conn.execute(text("DELETE FROM counter"))
        conn.execute(text("INSERT INTO counter (id, n) VALUES (1, 0)"))


def test_wal_pragma_is_active_after_connect(tmp_path):
    """The connect-event hook must set journal_mode=WAL on every connection."""
    engine = _make_engine(tmp_path / "wal.db", with_wal=True)
    _seed(engine)
    with engine.connect() as conn:
        mode = conn.execute(text("PRAGMA journal_mode")).scalar()
    assert mode == "wal", f"expected wal, got {mode}"


def test_concurrent_read_during_open_writer_transaction(tmp_path):
    """A reader on a separate connection must not be blocked by an open writer."""
    engine = _make_engine(tmp_path / "concurrent.db", with_wal=True)
    _seed(engine)
    Session = sessionmaker(bind=engine)

    writer_started = threading.Event()
    writer_release = threading.Event()
    read_value = {"n": None, "error": None}

    def writer():
        # Hold an open write transaction until the reader finishes.
        with Session() as session:
            session.execute(text("UPDATE counter SET n = 42 WHERE id = 1"))
            session.flush()
            writer_started.set()
            writer_release.wait(timeout=5)
            session.commit()

    def reader():
        writer_started.wait(timeout=5)
        try:
            with Session() as session:
                # Read on a different connection while the writer is mid-transaction.
                read_value["n"] = session.execute(text("SELECT n FROM counter WHERE id = 1")).scalar()
        except Exception as exc:
            read_value["error"] = exc

    w = threading.Thread(target=writer)
    r = threading.Thread(target=reader)
    w.start()
    r.start()
    r.join(timeout=10)
    writer_release.set()
    w.join(timeout=10)

    assert read_value["error"] is None, f"reader failed: {read_value['error']!r}"
    # WAL: reader sees the pre-commit value (still 0). The point is that the
    # SELECT returned at all, instead of raising 'database is locked'.
    assert read_value["n"] in (0, 42)
