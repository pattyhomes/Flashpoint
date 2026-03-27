"""
Integration tests for the Event Registry ingestion pipeline.

Tests run against an in-memory SQLite database so that DB interactions are
real (adds, flushes, queries, commits) without touching the production DB file.

Session strategy: the pipeline function owns and closes its own session.
Post-run assertions use a fresh session opened from the same in-memory engine.

Mocked boundaries:
  - EventRegistrySource.fetch() — controlled article pairs
  - find_matching_event() — controlled per test (real fn not needed here)
  - is_syndicated_copy() — controlled per test
  - compute_hotspots() — not under test here
"""

from contextlib import contextmanager
from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import app.jobs.seed as seed_module
from app.database import Base
from app.models import Event, EventSource, IngestRun
from app.schemas import EventCreate


# ---------------------------------------------------------------------------
# In-memory engine fixture (shared within a test via the same object)
# ---------------------------------------------------------------------------

@pytest.fixture
def db_engine():
    """Per-test in-memory SQLite engine with schema initialized."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(bind=engine)
    yield engine
    Base.metadata.drop_all(bind=engine)


def new_session(engine):
    """Open a fresh session from the test engine."""
    return sessionmaker(bind=engine)()


# ---------------------------------------------------------------------------
# Article / EventCreate factories
# ---------------------------------------------------------------------------

_BASE_TIME = datetime(2025, 3, 15, 12, 0, 0)


def make_event_create(
    source_id: str = "er-test-001",
    title: str = "Protesters march outside state capitol building",
    lat: float = 47.6097,
    lon: float = -122.3331,
    city: str = "Seattle",
    state: str = "WA",
    event_type: str = "protest",
    confidence_score: float = 0.54,
    severity_score: float = 0.40,
    location_precision: str = "city",
    occurred_at: datetime = _BASE_TIME,
) -> EventCreate:
    return EventCreate(
        source_id=source_id,
        title=title,
        summary="Hundreds gathered near the capitol.",
        event_type=event_type,
        latitude=lat,
        longitude=lon,
        city=city,
        state=state,
        country="US",
        occurred_at=occurred_at,
        source_name="eventregistry",
        source_url="https://seattletimes.com/article/123",
        source_count=1,
        confidence_score=confidence_score,
        severity_score=severity_score,
        location_precision=location_precision,
        raw_payload_json=(
            '{"er_uri": "test-001", "er_event_uri": "eng-001", '
            '"source_outlet": "Seattle Times", "precision": "city", '
            '"classification_score": 0.72, "categories": []}'
        ),
    )


def make_raw_article(
    uri: str = "test-001",
    title: str = "Protesters march outside state capitol building",
    outlet: str = "Seattle Times",
    url: str = "https://seattletimes.com/article/123",
) -> dict:
    return {
        "uri": uri,
        "title": title,
        "url": url,
        "eventUri": "eng-001",
        "source": {"title": outlet, "uri": "seattletimes.com"},
        "body": "Hundreds gathered near the capitol.",
        "dateTimePub": _BASE_TIME.isoformat(),
        "location": {
            "lat": 47.6097, "long": -122.3331,
            "type": "city",
            "label": {"eng": "Seattle, Washington, United States"},
        },
        "categories": [],
        "concepts": [],
    }


# ---------------------------------------------------------------------------
# Pipeline runner helper
# ---------------------------------------------------------------------------

def _run_pipeline(
    db_engine,
    article_pairs,
    *,
    create_new: bool = True,
    max_new: int = 10,
    find_match_event_id: int | None = None,   # if set, query this event from the pipeline's own db
    is_syndicated_return: bool = False,
):
    """
    Run run_eventregistry_ingestion() with a controlled environment.

    The pipeline function creates and closes its own session (from the
    patched SessionLocal). Assertions must use a fresh session afterward.

    find_match_event_id: when set, find_matching_event returns the event
    with this ID queried from the pipeline's own session — ensuring the
    ORM modification is committed by the pipeline's db.commit().
    """
    Session = sessionmaker(bind=db_engine)

    def _find_match(title, lat, lon, occurred_at, event_type, db, **kwargs):
        if find_match_event_id is not None:
            return db.get(Event, find_match_event_id)
        return None

    with (
        patch("app.jobs.seed.SessionLocal", side_effect=lambda: Session()),
        patch(
            "app.services.ingestion.eventregistry_source.EventRegistrySource.fetch",
            return_value=article_pairs,
        ),
        patch("app.jobs.seed.compute_hotspots"),
        patch("app.jobs.seed.find_matching_event", side_effect=_find_match),
        patch("app.jobs.seed.is_syndicated_copy", return_value=is_syndicated_return),
        patch("app.config.settings.event_registry_create_new_events", create_new),
        patch("app.config.settings.event_registry_max_new_events_per_run", max_new),
        patch("app.config.settings.event_registry_max_confidence_uncorroborated", 0.58),
    ):
        seed_module.run_eventregistry_ingestion()


def _seed_existing_event(db_engine) -> int:
    """Insert a pre-existing event and return its id."""
    session = new_session(db_engine)
    ev = Event(
        source_id="gdelt-existing-001",
        title="Protesters march outside state capitol building",
        event_type="protest",
        latitude=47.6097,
        longitude=-122.3331,
        city="Seattle", state="WA", country="US",
        occurred_at=_BASE_TIME,
        source_name="gdelt",
        source_count=1,
        confidence_score=0.50,
        severity_score=0.40,
        is_active=True,
    )
    session.add(ev)
    session.commit()
    event_id = ev.id
    session.close()
    return event_id


# ---------------------------------------------------------------------------
# Test: CREATE_NEW_EVENTS=false skips novel events
# ---------------------------------------------------------------------------

class TestDiscoveryGated:
    def test_no_new_events_when_discovery_disabled(self, db_engine):
        pair = (make_event_create(), make_raw_article())
        _run_pipeline(db_engine, [pair], create_new=False)

        session = new_session(db_engine)
        events = session.query(Event).filter(Event.source_name == "eventregistry").all()
        session.close()
        assert len(events) == 0

    def test_ingest_run_recorded_even_when_no_events_inserted(self, db_engine):
        pair = (make_event_create(), make_raw_article())
        _run_pipeline(db_engine, [pair], create_new=False)

        session = new_session(db_engine)
        run = session.query(IngestRun).filter(IngestRun.ingest_source == "eventregistry").first()
        session.close()
        assert run is not None
        assert run.status == "success"
        assert run.events_inserted == 0


# ---------------------------------------------------------------------------
# Test: CREATE_NEW_EVENTS=true creates event + EventSource
# ---------------------------------------------------------------------------

class TestDiscoveryEnabled:
    def test_creates_event_and_event_source(self, db_engine):
        pair = (make_event_create(), make_raw_article())
        _run_pipeline(db_engine, [pair], create_new=True)

        session = new_session(db_engine)
        events = session.query(Event).filter(Event.source_name == "eventregistry").all()
        assert len(events) == 1
        ev = events[0]
        assert ev.event_type == "protest"
        assert ev.source_id == "er-test-001"

        sources = session.query(EventSource).filter(EventSource.event_id == ev.id).all()
        session.close()
        assert len(sources) == 1
        assert sources[0].source_trust_weight == 1.0

    def test_confidence_capped_for_city_precision(self, db_engine):
        ec = make_event_create(confidence_score=0.80, location_precision="city")
        pair = (ec, make_raw_article())
        _run_pipeline(db_engine, [pair], create_new=True)

        session = new_session(db_engine)
        ev = session.query(Event).filter(Event.source_name == "eventregistry").first()
        session.close()
        assert ev is not None
        assert ev.confidence_score <= 0.58

    def test_ingest_run_records_inserted_count(self, db_engine):
        pair = (make_event_create(), make_raw_article())
        _run_pipeline(db_engine, [pair], create_new=True)

        session = new_session(db_engine)
        run = session.query(IngestRun).filter(IngestRun.ingest_source == "eventregistry").first()
        session.close()
        assert run is not None
        assert run.status == "success"
        assert run.events_inserted == 1

    def test_exact_duplicate_source_id_skipped(self, db_engine):
        # Pre-insert an event with the same source_id using a fresh session
        pre_session = new_session(db_engine)
        pre_session.add(Event(
            source_id="er-test-001",
            title="Pre-existing event",
            event_type="protest",
            latitude=47.6097, longitude=-122.3331,
            city="Seattle", state="WA", country="US",
            occurred_at=_BASE_TIME,
            source_name="eventregistry",
            source_count=1,
            confidence_score=0.54,
            severity_score=0.40,
        ))
        pre_session.commit()
        pre_session.close()

        pair = (make_event_create(), make_raw_article())
        _run_pipeline(db_engine, [pair], create_new=True)

        session = new_session(db_engine)
        events = session.query(Event).all()
        session.close()
        assert len(events) == 1  # only the pre-existing one


# ---------------------------------------------------------------------------
# Test: MAX_NEW_EVENTS_PER_RUN limit
# ---------------------------------------------------------------------------

class TestMaxNewEventsLimit:
    def test_respects_max_new_events_limit(self, db_engine):
        pairs = [
            (
                make_event_create(source_id=f"er-test-{i:03d}", title=f"Unique protest article identifier alpha-{i}"),
                make_raw_article(uri=f"test-{i:03d}", title=f"Unique protest article identifier alpha-{i}"),
            )
            for i in range(5)
        ]
        # find_matching_event returns None → all go to discovery path
        _run_pipeline(db_engine, pairs, create_new=True, max_new=2)

        session = new_session(db_engine)
        events = session.query(Event).filter(Event.source_name == "eventregistry").all()
        session.close()
        assert len(events) == 2


# ---------------------------------------------------------------------------
# Test: Corroboration path
# ---------------------------------------------------------------------------

class TestCorroborationPath:
    def test_corroboration_creates_event_source_record(self, db_engine):
        event_id = _seed_existing_event(db_engine)

        pair = (
            make_event_create(source_id="er-corroboration-001"),
            make_raw_article(uri="corroboration-001", outlet="Portland Tribune"),
        )
        _run_pipeline(
            db_engine, [pair],
            create_new=False,
            find_match_event_id=event_id,
            is_syndicated_return=False,
        )

        session = new_session(db_engine)
        sources = session.query(EventSource).filter(EventSource.event_id == event_id).all()
        session.close()
        assert len(sources) == 1
        assert sources[0].source_trust_weight == 1.0

    def test_corroboration_increments_source_count(self, db_engine):
        event_id = _seed_existing_event(db_engine)

        seed_session = new_session(db_engine)
        initial_count = seed_session.get(Event, event_id).source_count
        seed_session.close()

        pair = (
            make_event_create(source_id="er-corroboration-002"),
            make_raw_article(uri="corroboration-002", outlet="Portland Tribune"),
        )
        _run_pipeline(
            db_engine, [pair],
            create_new=False,
            find_match_event_id=event_id,
            is_syndicated_return=False,
        )

        session = new_session(db_engine)
        updated = session.get(Event, event_id)
        result_count = updated.source_count
        session.close()
        assert result_count == initial_count + 1

    def test_syndicated_copy_does_not_increment_source_count(self, db_engine):
        event_id = _seed_existing_event(db_engine)

        seed_session = new_session(db_engine)
        initial_count = seed_session.get(Event, event_id).source_count
        seed_session.close()

        pair = (
            make_event_create(source_id="er-syndicated-001"),
            make_raw_article(uri="syndicated-001", outlet="AP News"),
        )
        _run_pipeline(
            db_engine, [pair],
            create_new=False,
            find_match_event_id=event_id,
            is_syndicated_return=True,   # syndicated!
        )

        session = new_session(db_engine)
        updated = session.get(Event, event_id)
        assert updated.source_count == initial_count  # no uplift

        sources = session.query(EventSource).filter(EventSource.event_id == event_id).all()
        session.close()
        assert len(sources) == 1
        assert sources[0].source_trust_weight == 0.0  # stored, but zero weight


# ---------------------------------------------------------------------------
# Test: IngestRun status tracking
# ---------------------------------------------------------------------------

class TestIngestRunTracking:
    def test_ingest_run_uses_eventregistry_as_source(self, db_engine):
        _run_pipeline(db_engine, [], create_new=False)

        session = new_session(db_engine)
        run = session.query(IngestRun).first()
        session.close()
        assert run is not None
        assert run.ingest_source == "eventregistry"

    def test_ingest_run_has_finished_at_on_success(self, db_engine):
        _run_pipeline(db_engine, [], create_new=False)

        session = new_session(db_engine)
        run = session.query(IngestRun).first()
        session.close()
        assert run.finished_at is not None
        assert run.status == "success"
