from datetime import datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app
from app.models import Event, EvidenceItem, Observation
from app.services.intelligence import (
    dismiss_observation,
    link_observation_to_event,
    promote_observation,
    record_evidence,
    record_observation,
)


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


@pytest.fixture
def db(db_engine):
    Session = sessionmaker(bind=db_engine)
    session = Session()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def client(db_engine):
    Session = sessionmaker(bind=db_engine)

    def override_db():
        session = Session()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = override_db
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def test_record_evidence_is_idempotent_by_source_record(db):
    first = record_evidence(
        db,
        source_type="bluesky",
        source_record_id="at://did:plc:test/app.bsky.feed.post/1",
        source_url="https://bsky.app/profile/test/post/1",
        source_name="Bluesky",
        source_title="Police presence downtown",
        excerpt="Police presence downtown near the march route.",
        trust_tier="weak",
        raw_payload={"id": 1},
    )
    second = record_evidence(
        db,
        source_type="bluesky",
        source_record_id="at://did:plc:test/app.bsky.feed.post/1",
        source_url="https://bsky.app/profile/test/post/1",
        source_name="Bluesky",
        source_title="Police presence downtown",
        excerpt="Police presence downtown near the march route.",
        trust_tier="weak",
        raw_payload={"id": 1},
    )

    assert first.id == second.id
    assert db.query(EvidenceItem).count() == 1


def test_weak_lead_observation_does_not_create_event(db):
    evidence = record_evidence(
        db,
        source_type="mastodon",
        source_record_id="status-1",
        source_name="Mastodon",
        source_title="March forming near city hall",
        excerpt="Crowd forming near city hall.",
        trust_tier="weak",
    )
    observation = record_observation(
        db,
        evidence=evidence,
        status="lead",
        title="March forming near city hall",
        candidate_event_type="protest",
        latitude=39.9526,
        longitude=-75.1652,
        city="Philadelphia",
        state="PA",
        observed_at=datetime(2026, 5, 7, 12, 0, 0),
        confidence_score=0.32,
        severity_score=0.2,
    )

    assert observation.status == "lead"
    assert db.query(Event).count() == 0


def test_promoting_observation_creates_confirmed_event_and_source(db):
    evidence = record_evidence(
        db,
        source_type="eventregistry",
        source_record_id="er-1",
        source_url="https://example.com/story",
        source_name="Local News",
        source_title="Protest blocks downtown avenue",
        excerpt="A protest blocked a downtown avenue.",
        trust_tier="news",
    )
    observation = record_observation(
        db,
        evidence=evidence,
        status="lead",
        title="Protest blocks downtown avenue",
        summary="A protest blocked a downtown avenue.",
        candidate_event_type="protest",
        latitude=39.9526,
        longitude=-75.1652,
        city="Philadelphia",
        state="PA",
        observed_at=datetime(2026, 5, 7, 12, 0, 0),
        confidence_score=0.58,
        severity_score=0.45,
    )

    event = promote_observation(db, observation.id)

    assert event.id is not None
    assert event.source_id == f"obs-{observation.id}"
    assert event.source_count == 1
    assert observation.status == "promoted"
    assert observation.promoted_event_id == event.id


def test_dismiss_observation_hides_it_from_lead_queue(db):
    evidence = record_evidence(
        db,
        source_type="bluesky",
        source_record_id="post-2",
        source_name="Bluesky",
        source_title="Possible road blockage",
        trust_tier="weak",
    )
    observation = record_observation(
        db,
        evidence=evidence,
        status="lead",
        title="Possible road blockage",
        candidate_event_type="disruption",
        confidence_score=0.2,
    )

    dismiss_observation(db, observation.id)

    assert observation.status == "dismissed"


def test_link_observation_corroborates_existing_event(db):
    event = Event(
        source_id="gdelt-existing",
        title="Protesters gather outside courthouse",
        event_type="protest",
        latitude=38.9072,
        longitude=-77.0369,
        city="Washington",
        state="DC",
        country="US",
        occurred_at=datetime(2026, 5, 7, 12, 0, 0),
        source_name="gdelt",
        source_count=1,
        confidence_score=0.5,
        severity_score=0.4,
        is_active=True,
    )
    db.add(event)
    db.flush()
    evidence = record_evidence(
        db,
        source_type="eventregistry",
        source_record_id="er-link-1",
        source_url="https://example.com/link",
        source_name="Local News",
        source_title="Courthouse protest grows",
        trust_tier="news",
    )
    observation = record_observation(
        db,
        evidence=evidence,
        status="lead",
        title="Courthouse protest grows",
        candidate_event_type="protest",
        confidence_score=0.52,
    )

    linked = link_observation_to_event(db, observation.id, event.id)

    assert linked.id == event.id
    assert linked.source_count == 2
    assert linked.confidence_score == pytest.approx(0.58)
    assert observation.status == "linked"
    assert observation.linked_event_id == event.id


def test_observation_api_workflow(client, db):
    evidence = record_evidence(
        db,
        source_type="bluesky",
        source_record_id="post-api",
        source_name="Bluesky",
        source_title="March reported near campus",
        excerpt="March reported near campus.",
        trust_tier="weak",
    )
    observation = record_observation(
        db,
        evidence=evidence,
        status="lead",
        title="March reported near campus",
        candidate_event_type="protest",
        latitude=40.7128,
        longitude=-74.006,
        city="New York",
        state="NY",
        observed_at=datetime(2026, 5, 7, 12, 0, 0),
        confidence_score=0.34,
        severity_score=0.25,
    )
    db.commit()

    listed = client.get("/api/v1/observations/?status=lead")
    assert listed.status_code == 200
    assert listed.json()[0]["id"] == observation.id
    assert listed.json()[0]["evidence"]["source_type"] == "bluesky"

    dismissed = client.post(f"/api/v1/observations/{observation.id}/dismiss")
    assert dismissed.status_code == 200
    assert dismissed.json()["status"] == "dismissed"

    listed = client.get("/api/v1/observations/?status=lead")
    assert listed.status_code == 200
    assert listed.json() == []
