"""
Tests for /api/v1/health.

Per Desktop PRD §5 / §26 truthfulness contract: a degraded backend must
surface as a non-2xx response so the shell's overlay can show the operator
the real state, not a misleading "ok" with a broken DB underneath.
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base, get_db
from app.main import app


@pytest.fixture
def client_with_healthy_db():
    """TestClient backed by a fresh in-memory SQLite engine."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(bind=engine)
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    def _override_get_db():
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = _override_get_db
    yield TestClient(app)
    app.dependency_overrides.clear()


@pytest.fixture
def client_with_broken_db():
    """TestClient whose DB session always raises on execute()."""

    class _BrokenSession:
        def execute(self, *_args, **_kwargs):
            raise RuntimeError("database unreachable")

        def close(self):
            pass

    def _override_get_db():
        db = _BrokenSession()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = _override_get_db
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_health_returns_200_when_db_ok(client_with_healthy_db):
    resp = client_with_healthy_db.get("/api/v1/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["service"] == "flashpoint"
    assert body["db_status"] == "ok"
    assert body["timestamp"].endswith("Z")


def test_health_returns_503_when_db_unreachable(client_with_broken_db):
    resp = client_with_broken_db.get("/api/v1/health")
    assert resp.status_code == 503
    body = resp.json()
    assert body["service"] == "flashpoint"
    assert body["db_status"] == "error"
    assert body["timestamp"].endswith("Z")
