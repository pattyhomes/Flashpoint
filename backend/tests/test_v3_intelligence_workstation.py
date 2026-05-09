from datetime import datetime, timedelta

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app
from app.models import Event, EventSource, EvidenceItem, Hotspot, IngestRun, Observation
from app.services.intelligence import (
    apply_observation_automation,
    eligible_map_signals,
    record_evidence,
    record_observation,
)


def _engine():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    return engine


def _session(engine):
    return sessionmaker(bind=engine)()


def _client(engine):
    Session = sessionmaker(bind=engine)

    def override_db():
        session = Session()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = override_db
    return TestClient(app)


def _event(**overrides):
    values = {
        "source_id": "evt-1",
        "title": "Downtown protest grows",
        "summary": "A protest was reported downtown.",
        "event_type": "protest",
        "city": "Philadelphia",
        "state": "PA",
        "country": "US",
        "latitude": 39.9526,
        "longitude": -75.1652,
        "occurred_at": datetime(2026, 5, 7, 12, 0, 0),
        "source_name": "gdelt",
        "source_count": 1,
        "confidence_score": 0.52,
        "severity_score": 0.46,
        "cluster_id": 1,
        "trend_state": "stable",
        "is_active": True,
        "location_precision": "city",
    }
    values.update(overrides)
    return Event(**values)


def _lead(db, *, source_type="bluesky", record_id="lead-1", trust_tier="weak", confidence=0.5, status="lead"):
    evidence = record_evidence(
        db,
        source_type=source_type,
        source_record_id=record_id,
        source_name=source_type,
        source_title="Downtown protest reported",
        excerpt="People are reporting a protest downtown.",
        published_at=datetime(2026, 5, 7, 12, 5, 0),
        trust_tier=trust_tier,
    )
    return record_observation(
        db,
        evidence=evidence,
        status=status,
        title="Downtown protest reported",
        summary="People are reporting a protest downtown.",
        candidate_event_type="protest",
        latitude=39.953,
        longitude=-75.166,
        city="Philadelphia",
        state="PA",
        observed_at=datetime(2026, 5, 7, 12, 5, 0),
        confidence_score=confidence,
        severity_score=0.35,
        location_precision="city",
    )


def test_map_signal_endpoint_returns_only_eligible_unconfirmed_leads():
    engine = _engine()
    db = _session(engine)
    good = _lead(db, record_id="good", confidence=0.51)
    _lead(db, record_id="too-low", confidence=0.2)
    _lead(db, source_type="nws", record_id="context", trust_tier="context", confidence=0.9)
    linked = _lead(db, record_id="linked", confidence=0.7)
    linked.status = "linked"
    linked.linked_event_id = 99
    state_level = _lead(db, record_id="state", confidence=0.7)
    state_level.location_precision = "state"
    db.commit()

    client = _client(engine)
    try:
        response = client.get("/api/v1/observations/map-signals")
        assert response.status_code == 200
        body = response.json()
        assert [item["id"] for item in body] == [good.id]
        assert body[0]["source_family"] == "social"
        assert body[0]["signal_weight"] > 0
    finally:
        app.dependency_overrides.clear()
        db.close()
        Base.metadata.drop_all(bind=engine)


def test_eligible_social_volume_does_not_auto_create_confirmed_event():
    engine = _engine()
    db = _session(engine)
    first = _lead(db, source_type="bluesky", record_id="social-1", confidence=0.7)
    second = _lead(db, source_type="mastodon", record_id="social-2", confidence=0.72)

    apply_observation_automation(db, first)
    apply_observation_automation(db, second)

    assert db.query(Event).count() == 0
    assert db.query(Observation).filter(Observation.status == "lead").count() == 2
    db.close()
    Base.metadata.drop_all(bind=engine)


def test_independent_source_families_auto_promote_and_link_observations():
    engine = _engine()
    db = _session(engine)
    social = _lead(db, source_type="bluesky", record_id="social", confidence=0.66)
    news = _lead(db, source_type="eventregistry", record_id="news", trust_tier="news", confidence=0.64)

    apply_observation_automation(db, social)
    event = apply_observation_automation(db, news)

    assert event is not None
    assert event.source_count == 1
    assert social.status == "linked"
    assert social.linked_event_id == event.id
    assert news.status == "promoted"
    assert news.promoted_event_id == event.id
    db.close()
    Base.metadata.drop_all(bind=engine)


def test_observation_auto_links_to_matching_existing_event():
    engine = _engine()
    db = _session(engine)
    event = _event()
    db.add(event)
    db.flush()
    lead = _lead(db, source_type="eventregistry", record_id="news-link", trust_tier="news", confidence=0.62)

    linked = apply_observation_automation(db, lead)

    assert linked.id == event.id
    assert lead.status == "linked"
    assert event.source_count == 2
    assert event.confidence_score > 0.52
    db.close()
    Base.metadata.drop_all(bind=engine)


def test_social_observation_link_is_provenance_only_for_existing_event():
    engine = _engine()
    db = _session(engine)
    event = _event()
    db.add(event)
    db.flush()
    lead = _lead(db, source_type="bluesky", record_id="social-link", confidence=0.72)

    linked = apply_observation_automation(db, lead)
    source = db.query(EventSource).filter(EventSource.event_id == event.id).one()

    assert linked.id == event.id
    assert lead.status == "linked"
    assert event.source_count == 1
    assert event.confidence_score == 0.52
    assert source.source_trust_weight == 0.0
    db.close()
    Base.metadata.drop_all(bind=engine)


def test_hotspot_trend_endpoint_returns_24_hourly_buckets():
    engine = _engine()
    db = _session(engine)
    hotspot = Hotspot(
        id=1,
        name="Philadelphia Metro",
        centroid_lat=39.9526,
        centroid_lon=-75.1652,
        event_count=2,
        confidence_score=0.7,
        severity_score=0.6,
        momentum_score=0.5,
        priority_score=0.62,
        trend_state="stable",
        status_label="Active Hotspot",
        last_computed_at=datetime(2026, 5, 7, 13, 0, 0),
    )
    db.add(hotspot)
    db.add(_event(source_id="trend-1", cluster_id=1, occurred_at=datetime(2026, 5, 7, 12, 15, 0), severity_score=0.4))
    db.add(_event(source_id="trend-2", cluster_id=1, occurred_at=datetime(2026, 5, 7, 12, 45, 0), severity_score=0.8))
    db.add(_event(source_id="old", cluster_id=1, occurred_at=datetime(2026, 5, 6, 10, 0, 0), severity_score=1.0))
    db.commit()

    client = _client(engine)
    try:
        response = client.get("/api/v1/hotspots/1/trend?hours=24&now=2026-05-07T13:00:00")
        assert response.status_code == 200
        body = response.json()
        assert body["hotspot_id"] == 1
        assert len(body["buckets"]) == 24
        bucket = next(item for item in body["buckets"] if item["bucket_start"].startswith("2026-05-07T12:00:00"))
        assert bucket["event_count"] == 2
        assert bucket["max_severity"] == 0.8
    finally:
        app.dependency_overrides.clear()
        db.close()
        Base.metadata.drop_all(bind=engine)


def test_hotspot_trends_endpoint_returns_bulk_24_hourly_buckets():
    engine = _engine()
    db = _session(engine)
    db.add(Hotspot(
        id=1,
        name="Philadelphia Metro",
        centroid_lat=39.9526,
        centroid_lon=-75.1652,
        event_count=2,
        confidence_score=0.7,
        severity_score=0.6,
        momentum_score=0.5,
        priority_score=0.62,
        trend_state="stable",
        status_label="Active Hotspot",
        last_computed_at=datetime(2026, 5, 7, 13, 0, 0),
    ))
    db.add(Hotspot(
        id=2,
        name="Los Angeles Metro",
        centroid_lat=34.0522,
        centroid_lon=-118.2437,
        event_count=1,
        confidence_score=0.6,
        severity_score=0.5,
        momentum_score=0.4,
        priority_score=0.55,
        trend_state="declining",
        status_label="Active Hotspot",
        last_computed_at=datetime(2026, 5, 7, 13, 0, 0),
    ))
    db.add(_event(source_id="bulk-trend-1", cluster_id=1, occurred_at=datetime(2026, 5, 7, 12, 15, 0), severity_score=0.4))
    db.add(_event(source_id="bulk-trend-2", cluster_id=2, occurred_at=datetime(2026, 5, 7, 11, 45, 0), severity_score=0.7))
    db.commit()

    client = _client(engine)
    try:
        response = client.get("/api/v1/hotspots/trends?ids=1,2,999&hours=24&now=2026-05-07T13:00:00")
        assert response.status_code == 200
        body = response.json()
        assert [trend["hotspot_id"] for trend in body["trends"]] == [1, 2]
        assert all(len(trend["buckets"]) == 24 for trend in body["trends"])
        first = next(trend for trend in body["trends"] if trend["hotspot_id"] == 1)
        bucket = next(item for item in first["buckets"] if item["bucket_start"].startswith("2026-05-07T12:00:00"))
        assert bucket["event_count"] == 1
        assert bucket["max_severity"] == 0.4
    finally:
        app.dependency_overrides.clear()
        db.close()
        Base.metadata.drop_all(bind=engine)


def test_reset_and_seed_clears_v3_evidence_observation_and_source_rows():
    import app.jobs.seed as seed_module

    engine = _engine()
    Session = sessionmaker(bind=engine)
    db = Session()
    event = _event()
    db.add(event)
    db.flush()
    evidence = record_evidence(
        db,
        source_type="bluesky",
        source_record_id="stale",
        source_name="Bluesky",
        source_title="Stale lead",
        trust_tier="weak",
    )
    record_observation(db, evidence=evidence, status="lead", title="Stale lead")
    db.add(EventSource(event_id=event.id, source_type="bluesky", source_record_id="stale", source_trust_weight=0.0))
    db.commit()
    db.close()

    class EmptySource:
        def fetch(self):
            return []

    from unittest.mock import patch

    with (
        patch("app.jobs.seed.SessionLocal", side_effect=lambda: Session()),
        patch("app.jobs.seed.MockSource", return_value=EmptySource()),
        patch("app.jobs.seed.compute_hotspots"),
    ):
        seed_module.reset_and_seed()

    db = Session()
    assert db.query(Event).count() == 0
    assert db.query(EventSource).count() == 0
    assert db.query(Observation).count() == 0
    assert db.query(EvidenceItem).count() == 0
    db.close()
    Base.metadata.drop_all(bind=engine)


def test_system_status_includes_app_telemetry_counts():
    engine = _engine()
    db = _session(engine)
    db.add(_event())
    db.add(
        Hotspot(
            name="Philadelphia Metro",
            centroid_lat=39.9526,
            centroid_lon=-75.1652,
            event_count=1,
            confidence_score=0.7,
            severity_score=0.6,
            momentum_score=0.5,
            priority_score=0.62,
            trend_state="stable",
            status_label="Active Hotspot",
            last_computed_at=datetime(2026, 5, 7, 13, 0, 0),
        )
    )
    _lead(db, record_id="mapped", confidence=0.52)
    _lead(db, record_id="low", confidence=0.2)
    db.add(IngestRun(started_at=datetime(2026, 5, 7, 12, 30, 0), finished_at=datetime(2026, 5, 7, 12, 31, 0), status="success", ingest_source="bluesky"))
    db.commit()

    client = _client(engine)
    try:
        response = client.get("/api/v1/system/status")
        assert response.status_code == 200
        body = response.json()
        assert body["event_count"] == 1
        assert body["hotspot_count"] == 1
        assert body["lead_count"] == 2
        assert body["exception_count"] == 2
        assert body["mapped_signal_count"] == 1
    finally:
        app.dependency_overrides.clear()
        db.close()
        Base.metadata.drop_all(bind=engine)
