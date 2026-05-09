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
from app.utils.time import utcnow_naive


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


def _hotspot(**overrides):
    values = {
        "id": 1,
        "name": "Philadelphia Metro",
        "centroid_lat": 39.9526,
        "centroid_lon": -75.1652,
        "event_count": 2,
        "confidence_score": 0.7,
        "severity_score": 0.6,
        "momentum_score": 0.5,
        "priority_score": 0.62,
        "trend_state": "stable",
        "status_label": "Active Hotspot",
        "last_computed_at": datetime(2026, 5, 7, 13, 0, 0),
    }
    values.update(overrides)
    return Hotspot(**values)


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


def test_hotspot_briefing_endpoint_returns_404_for_missing_hotspot():
    engine = _engine()
    db = _session(engine)
    client = _client(engine)
    try:
        response = client.get("/api/v1/hotspots/999/briefing")
        assert response.status_code == 404
        assert response.json()["detail"] == "Hotspot not found"
    finally:
        app.dependency_overrides.clear()
        db.close()
        Base.metadata.drop_all(bind=engine)


def test_hotspot_briefing_returns_grounded_facts_timeline_and_citations():
    engine = _engine()
    db = _session(engine)
    db.add(_hotspot())
    event = _event(
        source_id="briefing-1",
        title="Transit protest disrupts downtown service",
        source_name="eventregistry",
        source_url="https://example.test/event",
        occurred_at=datetime(2026, 5, 7, 12, 15, 0),
        severity_score=0.82,
        confidence_score=0.74,
    )
    db.add(event)
    db.flush()
    db.add(EventSource(
        event_id=event.id,
        source_type="eventregistry",
        source_record_id="article-1",
        source_name="WHYY",
        source_url="https://example.test/article-1",
        source_title="Transit protest disrupts downtown service",
        source_published_at=datetime(2026, 5, 7, 12, 20, 0),
        source_trust_weight=1.0,
        location_precision="city",
    ))
    db.commit()

    client = _client(engine)
    try:
        response = client.get("/api/v1/hotspots/1/briefing")
        assert response.status_code == 200
        body = response.json()
        assert body["hotspot_id"] == 1
        assert "Philadelphia Metro" in body["headline"]
        assert "confirmed event density" in body["why_it_matters"]
        assert any(fact["label"] == "Representative event" for fact in body["key_facts"])
        assert body["timeline"][0]["display_title"] == "Transit protest disrupts downtown service"
        assert body["timeline"][0]["citation_ids"]
        assert any(citation["source_name"] == "WHYY" and citation["counted"] for citation in body["citations"])
    finally:
        app.dependency_overrides.clear()
        db.close()
        Base.metadata.drop_all(bind=engine)


def test_hotspot_briefing_keeps_zero_weight_sources_provenance_only():
    engine = _engine()
    db = _session(engine)
    db.add(_hotspot())
    event = _event(source_id="briefing-zero", source_count=1)
    db.add(event)
    db.flush()
    db.add(EventSource(
        event_id=event.id,
        source_type="bluesky",
        source_record_id="social-copy",
        source_name="Bluesky",
        source_title="Social copy of the protest report",
        source_published_at=datetime(2026, 5, 7, 12, 30, 0),
        source_trust_weight=0.0,
        location_precision="city",
    ))
    db.commit()

    client = _client(engine)
    try:
        response = client.get("/api/v1/hotspots/1/briefing")
        assert response.status_code == 200
        body = response.json()
        social = next(citation for citation in body["citations"] if citation["source_type"] == "bluesky")
        counted_sources = next(fact for fact in body["key_facts"] if fact["label"] == "Counted sources")
        assert social["counted"] is False
        assert social["note"] == "provenance only"
        assert counted_sources["value"] == "1"
        assert any("not counted as corroboration" in caveat for caveat in body["caveats"])
    finally:
        app.dependency_overrides.clear()
        db.close()
        Base.metadata.drop_all(bind=engine)


def test_hotspot_briefing_uses_event_fallback_citation_without_source_rows():
    engine = _engine()
    db = _session(engine)
    db.add(_hotspot())
    db.add(_event(
        source_id="briefing-fallback",
        title="Downtown protest grows",
        source_name="gdelt",
        source_url="https://example.test/gdelt-event",
    ))
    db.commit()

    client = _client(engine)
    try:
        response = client.get("/api/v1/hotspots/1/briefing")
        assert response.status_code == 200
        body = response.json()
        assert body["citations"] == [{
            "id": 1,
            "event_id": 1,
            "source_type": "gdelt",
            "source_name": "gdelt",
            "title": "Downtown protest grows",
            "url": "https://example.test/gdelt-event",
            "published_at": "2026-05-07T12:00:00",
            "counted": True,
            "note": "confirmed event source",
        }]
    finally:
        app.dependency_overrides.clear()
        db.close()
        Base.metadata.drop_all(bind=engine)


def test_hotspot_briefing_excludes_unlinked_observations_from_claims():
    engine = _engine()
    db = _session(engine)
    db.add(_hotspot())
    db.add(_event(source_id="briefing-confirmed", title="Confirmed downtown protest"))
    _lead(db, record_id="unlinked-rumor", confidence=0.72)
    db.query(Observation).filter(Observation.evidence_id.isnot(None)).one().title = "Unverified courthouse rumor"
    db.commit()

    client = _client(engine)
    try:
        response = client.get("/api/v1/hotspots/1/briefing")
        assert response.status_code == 200
        body = response.json()
        serialized = str(body)
        assert "Confirmed downtown protest" in serialized
        assert "Unverified courthouse rumor" not in serialized
        assert len(body["timeline"]) == 1
    finally:
        app.dependency_overrides.clear()
        db.close()
        Base.metadata.drop_all(bind=engine)


def test_hotspot_briefing_why_now_compares_current_and_prior_windows():
    engine = _engine()
    db = _session(engine)
    now = utcnow_naive()
    db.add(_hotspot(trend_state="escalating", momentum_score=0.7))
    db.add(_event(source_id="why-now-current-1", occurred_at=now - timedelta(hours=2), severity_score=0.8))
    db.add(_event(source_id="why-now-current-2", occurred_at=now - timedelta(hours=4), severity_score=0.6))
    db.add(_event(source_id="why-now-prior", occurred_at=now - timedelta(hours=30), severity_score=0.2))
    db.commit()

    client = _client(engine)
    try:
        response = client.get("/api/v1/hotspots/1/briefing")
        assert response.status_code == 200
        body = response.json()
        assert body["why_now"]["current_24h_count"] == 2
        assert body["why_now"]["previous_24h_count"] == 1
        assert body["why_now"]["change_count"] == 1
        assert body["why_now"]["severity_change"] == 0.5
        assert body["why_now"]["trend_explanation"].startswith("Escalating:")
        assert "an escalating trend" in body["why_it_matters"]
        assert "a escalating" not in body["why_it_matters"]
    finally:
        app.dependency_overrides.clear()
        db.close()
        Base.metadata.drop_all(bind=engine)


def test_hotspot_briefing_groups_what_happened_and_preserves_referenced_citations_under_cap():
    engine = _engine()
    db = _session(engine)
    now = utcnow_naive()
    db.add(_hotspot(event_count=36))
    for index in range(36):
        event = _event(
            source_id=f"grouped-{index}",
            title=f"Confirmed event {index}",
            event_type="protest" if index < 24 else "violence",
            city="Philadelphia" if index % 2 == 0 else "Camden",
            state="PA" if index % 2 == 0 else "NJ",
            occurred_at=now - timedelta(hours=index + 1),
            severity_score=0.9 if index % 5 == 0 else 0.4,
        )
        db.add(event)
        db.flush()
        db.add(EventSource(
            event_id=event.id,
            source_type="eventregistry",
            source_record_id=f"grouped-source-{index}",
            source_name=f"Outlet {index}",
            source_url=f"https://example.test/{index}",
            source_title=f"Confirmed event source {index}",
            source_published_at=event.occurred_at,
            source_trust_weight=1.0,
            location_precision="city",
        ))
    db.commit()

    client = _client(engine)
    try:
        response = client.get("/api/v1/hotspots/1/briefing")
        assert response.status_code == 200
        body = response.json()
        assert len(body["citations"]) <= 30
        assert body["what_happened"]["timeline_groups"]
        assert body["what_happened"]["dominant_event_types"][0]["label"] == "protest"
        returned_ids = {citation["id"] for citation in body["citations"]}
        referenced_ids = set()
        for fact in body["key_facts"]:
            referenced_ids.update(fact["citation_ids"])
        for driver in body["why_now"]["drivers"]:
            referenced_ids.update(driver["citation_ids"])
        for group in body["what_happened"]["timeline_groups"]:
            referenced_ids.update(group["citation_ids"])
            for event in group["representative_events"]:
                referenced_ids.update(event["citation_ids"])
        assert referenced_ids
        assert referenced_ids <= returned_ids
        assert body["source_assessment"]["citation_count_total"] > body["source_assessment"]["citation_count_returned"]
    finally:
        app.dependency_overrides.clear()
        db.close()
        Base.metadata.drop_all(bind=engine)


def test_hotspot_briefing_source_assessment_counts_families_not_provenance_only():
    engine = _engine()
    db = _session(engine)
    db.add(_hotspot())
    event = _event(source_id="source-assess", source_name="gdelt")
    db.add(event)
    db.flush()
    db.add(EventSource(
        event_id=event.id,
        source_type="eventregistry",
        source_record_id="news-source",
        source_name="WHYY",
        source_trust_weight=1.0,
    ))
    db.add(EventSource(
        event_id=event.id,
        source_type="bluesky",
        source_record_id="social-copy",
        source_name="Bluesky",
        source_trust_weight=0.0,
    ))
    db.commit()

    client = _client(engine)
    try:
        response = client.get("/api/v1/hotspots/1/briefing")
        assert response.status_code == 200
        body = response.json()
        assert body["source_assessment"]["counted_source_families"] == ["gdelt", "news"]
        assert body["source_assessment"]["counted_source_count"] == 2
        assert body["source_assessment"]["provenance_only_count"] == 1
        assert any(citation["source_type"] == "bluesky" and not citation["counted"] for citation in body["citations"])
    finally:
        app.dependency_overrides.clear()
        db.close()
        Base.metadata.drop_all(bind=engine)


def test_hotspot_briefing_empty_hotspot_returns_depth_sections_with_caveat():
    engine = _engine()
    db = _session(engine)
    db.add(_hotspot(event_count=0, confidence_score=0.4))
    db.commit()

    client = _client(engine)
    try:
        response = client.get("/api/v1/hotspots/1/briefing")
        assert response.status_code == 200
        body = response.json()
        assert body["why_now"]["current_24h_count"] == 0
        assert body["what_happened"]["timeline_groups"] == []
        assert body["source_assessment"]["counted_source_count"] == 0
        assert "No active confirmed events" in body["what_happened"]["summary"]
        assert any("no active confirmed member events" in caveat.lower() for caveat in body["caveats"])
    finally:
        app.dependency_overrides.clear()
        db.close()
        Base.metadata.drop_all(bind=engine)


def test_event_api_marks_generic_state_level_gdelt_classification_without_url_inference():
    engine = _engine()
    db = _session(engine)
    db.add(_event(
        source_id="generic-gdelt",
        title="Violence — Tennessee",
        event_type="violence",
        city="Tennessee",
        state="TN",
        source_name="gdelt",
        source_url="https://example.test/specific-looking-url-slug",
        location_precision="state",
    ))
    db.commit()

    client = _client(engine)
    try:
        response = client.get("/api/v1/events/?limit=10")
        assert response.status_code == 200
        event = response.json()["items"][0]
        assert event["display_title"] == "State-level GDELT violence classification - Tennessee"
        assert event["specificity_level"] == "low_location"
        assert event["is_generic_classification"] is True
        assert "specific-looking-url-slug" not in event["display_title"]
    finally:
        app.dependency_overrides.clear()
        db.close()
        Base.metadata.drop_all(bind=engine)


def test_event_api_prefers_concrete_source_title_over_generic_event_title():
    engine = _engine()
    db = _session(engine)
    event = _event(
        source_id="generic-with-source-title",
        title="Violence — Nashville",
        event_type="violence",
        city="Nashville",
        state="TN",
        source_name="gdelt",
        location_precision="city",
    )
    db.add(event)
    db.flush()
    db.add(EventSource(
        event_id=event.id,
        source_type="eventregistry",
        source_record_id="specific-source-title",
        source_name="Local outlet",
        source_title="Protesters block downtown street after council vote",
        source_trust_weight=1.0,
        location_precision="city",
    ))
    db.commit()

    client = _client(engine)
    try:
        response = client.get(f"/api/v1/events/{event.id}")
        assert response.status_code == 200
        body = response.json()
        assert body["display_title"] == "Protesters block downtown street after council vote"
        assert body["specificity_level"] == "specific"
        assert body["is_generic_classification"] is False
    finally:
        app.dependency_overrides.clear()
        db.close()
        Base.metadata.drop_all(bind=engine)


def test_hotspot_briefing_prefers_explainable_representative_over_generic_high_severity():
    engine = _engine()
    db = _session(engine)
    db.add(_hotspot(name="Tennessee region", event_count=2))
    generic = _event(
        source_id="generic-high-severity",
        title="Violence — Tennessee",
        event_type="violence",
        city="Tennessee",
        state="TN",
        source_name="gdelt",
        severity_score=1.0,
        confidence_score=0.5,
        location_precision="state",
    )
    specific = _event(
        source_id="specific-lower-severity",
        title="Protesters block downtown street after council vote",
        event_type="protest",
        city="Nashville",
        state="TN",
        source_name="eventregistry",
        severity_score=0.72,
        confidence_score=0.74,
        location_precision="city",
    )
    db.add(generic)
    db.add(specific)
    db.commit()

    client = _client(engine)
    try:
        response = client.get("/api/v1/hotspots/1/briefing")
        assert response.status_code == 200
        body = response.json()
        representative = next(fact for fact in body["key_facts"] if fact["label"] == "Representative event")
        assert "Protesters block downtown street" in representative["value"]
        first_rep = body["what_happened"]["timeline_groups"][0]["representative_events"][0]
        assert first_rep["display_title"] == "Protesters block downtown street after council vote"
        assert first_rep["specificity_level"] == "specific"
    finally:
        app.dependency_overrides.clear()
        db.close()
        Base.metadata.drop_all(bind=engine)


def test_hotspot_briefing_flags_tennessee_like_low_specificity_volume():
    engine = _engine()
    db = _session(engine)
    db.add(_hotspot(name="Tennessee region", event_count=8, confidence_score=0.5))
    for index in range(8):
        db.add(_event(
            source_id=f"tn-generic-{index}",
            title="Violence — Tennessee",
            event_type="violence",
            city="Tennessee",
            state="TN",
            source_name="gdelt",
            location_precision="state",
            occurred_at=utcnow_naive() - timedelta(hours=index + 1),
            severity_score=0.95,
        ))
    db.commit()

    client = _client(engine)
    try:
        response = client.get("/api/v1/hotspots/1/briefing")
        assert response.status_code == 200
        body = response.json()
        assert body["specificity_assessment"]["low_specificity"] is True
        assert body["specificity_assessment"]["incident_specific_count"] == 0
        assert body["specificity_assessment"]["classified_count"] == 8
        assert body["specificity_assessment"]["low_location_count"] == 8
        assert body["caveats"][0].startswith("High volume, but low incident specificity")
        assert "High volume, but low incident specificity" in body["why_it_matters"]
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
