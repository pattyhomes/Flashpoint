from datetime import datetime
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.jobs.seed as seed_module
from app.database import Base
from app.models import Event, EvidenceItem, IngestRun, Observation
from app.schemas import EventCreate
from app.services.article_metadata import ArticleMetadata
from app.services.ingestion.base import ObservationCandidate


@pytest.fixture
def db_engine():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    yield engine
    Base.metadata.drop_all(bind=engine)


def new_session(engine):
    return sessionmaker(bind=engine)()


def make_event(source_id="gdelt-100", source_name="gdelt"):
    return EventCreate(
        source_id=source_id,
        title="Protest — Philadelphia",
        summary="A protest was reported in Philadelphia.",
        event_type="protest",
        city="Philadelphia",
        state="PA",
        country="US",
        latitude=39.9526,
        longitude=-75.1652,
        occurred_at=datetime(2026, 5, 7, 12, 0, 0),
        source_url="https://example.com/source",
        source_name=source_name,
        source_count=2,
        confidence_score=0.68,
        severity_score=0.42,
        location_precision="city",
        raw_payload_json='{"source": "test"}',
    )


def make_raw_article(uri="er-100"):
    return {
        "uri": uri,
        "title": "Protest reported in Philadelphia",
        "url": "https://example.com/source",
        "source": {"title": "Local News"},
        "body": "A protest was reported in Philadelphia.",
        "dateTimePub": "2026-05-07T12:00:00",
        "eventUri": "eng-100",
    }


def test_gdelt_ingestion_records_evidence_and_promoted_observation(db_engine):
    Session = sessionmaker(bind=db_engine)
    with (
        patch("app.jobs.seed.SessionLocal", side_effect=lambda: Session()),
        patch("app.services.ingestion.gdelt_source.GdeltSource.fetch", return_value=[make_event()]),
        patch("app.jobs.seed.fetch_article_metadata", return_value=ArticleMetadata("Protest reported in Philadelphia", "A protest was reported in Philadelphia.", "https://example.com/source")),
        patch("app.jobs.seed.compute_hotspots"),
    ):
        seed_module.run_gdelt_ingestion()

    session = new_session(db_engine)
    assert session.query(Event).count() == 1
    evidence = session.query(EvidenceItem).one()
    observation = session.query(Observation).one()
    run = session.query(IngestRun).filter(IngestRun.ingest_source == "gdelt").one()
    session.close()

    assert evidence.source_type == "gdelt"
    assert evidence.source_record_id == "gdelt-100"
    assert evidence.trust_tier == "news"
    assert observation.status == "promoted"
    assert observation.promoted_event_id is not None
    assert run.events_inserted == 1


def test_eventregistry_novel_article_with_discovery_disabled_becomes_lead_only(db_engine):
    Session = sessionmaker(bind=db_engine)
    pair = (make_event(source_id="er-100", source_name="eventregistry"), make_raw_article())

    with (
        patch("app.jobs.seed.SessionLocal", side_effect=lambda: Session()),
        patch("app.services.ingestion.eventregistry_source.EventRegistrySource.fetch", return_value=[pair]),
        patch("app.jobs.seed.compute_hotspots"),
        patch("app.jobs.seed.find_matching_event", return_value=None),
        patch("app.config.settings.event_registry_create_new_events", False),
    ):
        seed_module.run_eventregistry_ingestion()

    session = new_session(db_engine)
    assert session.query(Event).count() == 0
    evidence = session.query(EvidenceItem).one()
    observation = session.query(Observation).one()
    session.close()

    assert evidence.source_type == "eventregistry"
    assert evidence.source_record_id == "er-100"
    assert observation.status == "lead"
    assert observation.promoted_event_id is None


def test_eventregistry_corroboration_records_linked_observation(db_engine):
    Session = sessionmaker(bind=db_engine)
    session = new_session(db_engine)
    event = Event(
        source_id="gdelt-existing",
        title="Protest — Philadelphia",
        event_type="protest",
        latitude=39.9526,
        longitude=-75.1652,
        city="Philadelphia",
        state="PA",
        country="US",
        occurred_at=datetime(2026, 5, 7, 12, 0, 0),
        source_name="gdelt",
        source_count=1,
        confidence_score=0.5,
        severity_score=0.4,
        is_active=True,
    )
    session.add(event)
    session.commit()
    event_id = event.id
    session.close()

    pair = (make_event(source_id="er-link-100", source_name="eventregistry"), make_raw_article("er-link-100"))

    def _find_match(*args, db, **kwargs):
        return db.get(Event, event_id)

    with (
        patch("app.jobs.seed.SessionLocal", side_effect=lambda: Session()),
        patch("app.services.ingestion.eventregistry_source.EventRegistrySource.fetch", return_value=[pair]),
        patch("app.jobs.seed.compute_hotspots"),
        patch("app.jobs.seed.find_matching_event", side_effect=_find_match),
        patch("app.jobs.seed.is_syndicated_copy", return_value=False),
        patch("app.config.settings.event_registry_create_new_events", False),
    ):
        seed_module.run_eventregistry_ingestion()

    session = new_session(db_engine)
    observation = session.query(Observation).one()
    updated = session.get(Event, event_id)
    session.close()

    assert observation.status == "linked"
    assert observation.linked_event_id == event_id
    assert updated.source_count == 2


def test_observation_source_auto_promotion_recomputes_hotspots(db_engine):
    Session = sessionmaker(bind=db_engine)
    candidate = ObservationCandidate(
        source_type="acled",
        source_record_id="acled-1",
        source_url="https://example.com/acled",
        source_name="ACLED",
        source_title="Protest reported in Philadelphia",
        excerpt="A protest was reported in Philadelphia.",
        published_at=datetime(2026, 5, 7, 12, 0, 0),
        trust_tier="acled",
        raw_payload={"id": "acled-1"},
        status="lead",
        title="Protest reported in Philadelphia",
        summary="A protest was reported in Philadelphia.",
        candidate_event_type="protest",
        latitude=39.9526,
        longitude=-75.1652,
        city="Philadelphia",
        state="PA",
        observed_at=datetime(2026, 5, 7, 12, 0, 0),
        confidence_score=0.75,
        severity_score=0.45,
        location_precision="city",
    )

    with (
        patch("app.jobs.seed.SessionLocal", side_effect=lambda: Session()),
        patch("app.services.ingestion.acled_source.AcledSource.fetch", return_value=[candidate]),
        patch("app.jobs.seed.compute_hotspots") as compute_hotspots,
    ):
        seed_module.run_observation_source_ingestion("acled")

    session = new_session(db_engine)
    assert session.query(Event).count() == 1
    observation = session.query(Observation).one()
    session.close()

    assert observation.status == "promoted"
    compute_hotspots.assert_called_once()
