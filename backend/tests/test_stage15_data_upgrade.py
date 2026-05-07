from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app
from app.models import Event, EventSource, EvidenceItem, IngestRun, Observation
from app.services.ingestion.base import ObservationCandidate
from app.services.intelligence import (
    apply_observation_automation,
    eligible_map_signals,
    link_observation_to_event,
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


@pytest.fixture
def db_engine():
    engine = _engine()
    try:
        yield engine
    finally:
        Base.metadata.drop_all(bind=engine)


def _lead(db, *, source_type="bluesky", record_id="lead-1", trust_tier="weak", location_confidence=0.8):
    evidence = record_evidence(
        db,
        source_type=source_type,
        source_record_id=record_id,
        source_name=source_type,
        source_title="Downtown protest reported in Philadelphia",
        excerpt="People are reporting a protest downtown in Philadelphia, PA.",
        published_at=datetime(2026, 5, 7, 12, 0, 0),
        trust_tier=trust_tier,
    )
    return record_observation(
        db,
        evidence=evidence,
        status="lead",
        title="Downtown protest reported in Philadelphia",
        summary="People are reporting a protest downtown in Philadelphia, PA.",
        candidate_event_type="protest",
        latitude=39.9526,
        longitude=-75.1652,
        city="Philadelphia",
        state="PA",
        observed_at=datetime(2026, 5, 7, 12, 0, 0),
        confidence_score=0.72,
        severity_score=0.35,
        location_precision="city",
        location_confidence=location_confidence,
        location_reason="gazetteer:city_state",
    )


def test_local_geocoder_resolves_city_state_and_rejects_ambiguous_city():
    from app.services.geocoding import LocalGeocoder

    geocoder = LocalGeocoder()

    philadelphia = geocoder.resolve(text="Protest reported in Philadelphia, PA")
    assert philadelphia is not None
    assert philadelphia.city == "Philadelphia"
    assert philadelphia.state == "PA"
    assert philadelphia.precision == "city"
    assert philadelphia.confidence >= 0.8
    assert "city_state" in philadelphia.reason

    ambiguous = geocoder.resolve(text="Protest reported in Springfield")
    assert ambiguous is None


def test_low_location_confidence_blocks_map_signal_and_auto_promotion():
    engine = _engine()
    db = _session(engine)
    social = _lead(db, source_type="bluesky", record_id="social-low-geo", location_confidence=0.4)
    news = _lead(db, source_type="eventregistry", record_id="news-low-geo", trust_tier="news", location_confidence=0.4)

    assert eligible_map_signals(db) == []
    assert apply_observation_automation(db, social) is None
    assert apply_observation_automation(db, news) is None
    assert db.query(Event).count() == 0
    assert social.exception_category == "bad_location"
    db.close()
    Base.metadata.drop_all(bind=engine)


def test_sources_status_api_reports_feed_health_and_exception_counts():
    engine = _engine()
    db = _session(engine)
    _lead(db, record_id="bad-location", location_confidence=0.3)
    db.add(
        IngestRun(
            started_at=datetime(2026, 5, 7, 12, 0, 0),
            finished_at=datetime(2026, 5, 7, 12, 0, 5),
            status="success",
            ingest_source="bluesky",
            records_fetched=10,
            evidence_inserted=4,
            observations_inserted=3,
            records_rejected=6,
            reject_counts_json='{"classified_out":4,"bad_location":2}',
        )
    )
    db.commit()

    client = _client(engine)
    try:
        response = client.get("/api/v1/sources/status")
        assert response.status_code == 200
        body = response.json()
        bluesky = next(source for source in body["sources"] if source["source_name"] == "bluesky")
        assert bluesky["records_fetched"] == 10
        assert bluesky["records_rejected"] == 6
        assert body["exception_counts"]["bad_location"] == 1
    finally:
        app.dependency_overrides.clear()
        db.close()
        Base.metadata.drop_all(bind=engine)


def test_observation_api_filters_by_exception_category():
    engine = _engine()
    db = _session(engine)
    bad = _lead(db, record_id="bad", location_confidence=0.3)
    good = _lead(db, record_id="good", location_confidence=0.9)
    good.exception_category = "social_only"
    db.commit()

    client = _client(engine)
    try:
        response = client.get("/api/v1/observations/?status=lead&exception_category=bad_location")
        assert response.status_code == 200
        assert [item["id"] for item in response.json()] == [bad.id]
    finally:
        app.dependency_overrides.clear()
        db.close()
        Base.metadata.drop_all(bind=engine)


def test_bluesky_query_pack_runs_multiple_curated_queries():
    from app.services.ingestion.bluesky_source import BlueskySource

    response = MagicMock()
    response.raise_for_status.return_value = None
    response.json.return_value = {
        "posts": [
            {
                "uri": "at://did:plc:test/app.bsky.feed.post/abc",
                "indexedAt": "2026-05-07T12:00:00Z",
                "author": {"handle": "example.bsky.social"},
                "record": {
                    "text": "Hundreds of protesters march through downtown Philadelphia tonight",
                    "createdAt": "2026-05-07T11:59:00Z",
                },
            }
        ]
    }

    with (
        patch("app.services.ingestion.bluesky_source.httpx.get", return_value=response) as get,
        patch("app.config.settings.bluesky_query_pack", "protest,downtown demonstration"),
    ):
        candidates = BlueskySource().fetch()

    assert get.call_count == 2
    assert len(candidates) == 1
    assert candidates[0].source_record_id == "at://did:plc:test/app.bsky.feed.post/abc"


def test_social_sources_use_curated_default_query_packs():
    from app.services.ingestion.bluesky_source import _queries as bluesky_queries
    from app.services.ingestion.mastodon_source import _queries as mastodon_queries

    with (
        patch("app.config.settings.bluesky_query_pack", ""),
        patch("app.config.settings.mastodon_query_pack", ""),
    ):
        assert len(bluesky_queries()) > 1
        assert len(mastodon_queries()) > 1


def test_local_news_source_fetches_allowlisted_feed_and_article():
    from app.services.ingestion.local_news_source import LocalNewsSource

    feed = """<?xml version="1.0"?>
    <rss version="2.0"><channel>
      <item>
        <guid>story-1</guid>
        <title>Protest march closes downtown Philadelphia streets</title>
        <link>https://local.test/story-1</link>
        <description>Demonstrators gathered downtown in Philadelphia, PA.</description>
        <pubDate>Thu, 07 May 2026 12:00:00 GMT</pubDate>
      </item>
    </channel></rss>
    """
    article = "<html><body><article>Hundreds of protesters gathered in downtown Philadelphia, PA.</article></body></html>"
    feed_response = MagicMock(text=feed)
    feed_response.raise_for_status.return_value = None
    article_response = MagicMock(text=article)
    article_response.raise_for_status.return_value = None

    def fake_get(url, **_kwargs):
        return article_response if "story-1" in url else feed_response

    with (
        patch("app.config.settings.local_news_enabled", True),
        patch("app.config.settings.local_news_feed_urls", "https://local.test/rss.xml"),
        patch("app.config.settings.local_news_allowed_domains", "local.test"),
        patch("app.services.ingestion.local_news_source.httpx.get", side_effect=fake_get),
        patch("app.services.ingestion.local_news_source.robotparser.RobotFileParser.can_fetch", return_value=True),
    ):
        candidates = LocalNewsSource().fetch()

    assert len(candidates) == 1
    assert candidates[0].source_type == "local_news"
    assert candidates[0].status == "lead"
    assert candidates[0].candidate_event_type == "protest"
    assert "Hundreds of protesters" in candidates[0].excerpt


def test_local_news_requires_allowlist_when_enabled():
    from app.services.ingestion.local_news_source import LocalNewsSource

    with (
        patch("app.config.settings.local_news_enabled", True),
        patch("app.config.settings.local_news_feed_urls", "https://local.test/rss.xml"),
        patch("app.config.settings.local_news_allowed_domains", ""),
        patch("app.services.ingestion.local_news_source.httpx.get") as get,
    ):
        source = LocalNewsSource()
        candidates = source.fetch()

    assert candidates == []
    assert source.stats["reject_counts"]["allowlist_required"] == 1
    get.assert_not_called()


def test_observation_source_ingestion_persists_run_stats_for_rejections(db_engine):
    import app.jobs.seed as seed_module

    Session = sessionmaker(bind=db_engine)
    candidate = ObservationCandidate(
        source_type="bluesky",
        source_record_id="accepted",
        source_url=None,
        source_name="Bluesky",
        source_title="Protest in Philadelphia",
        excerpt="Protest in Philadelphia, PA",
        published_at=datetime(2026, 5, 7, 12, 0, 0),
        trust_tier="weak",
        raw_payload={},
        status="lead",
        title="Protest in Philadelphia",
        candidate_event_type="protest",
        latitude=39.9526,
        longitude=-75.1652,
        city="Philadelphia",
        state="PA",
        observed_at=datetime(2026, 5, 7, 12, 0, 0),
        confidence_score=0.5,
        severity_score=0.3,
        location_precision="city",
        location_confidence=0.8,
        location_reason="gazetteer:city_state",
    )

    class FakeSource:
        stats = {"fetched": 2, "rejected": 1, "reject_counts": {"classified_out": 1}}

        def fetch(self):
            return [candidate]

    with (
        patch("app.jobs.seed.SessionLocal", side_effect=lambda: Session()),
        patch.dict(seed_module.OBSERVATION_SOURCE_MAP, {"fake": ("fake", lambda: FakeSource())}, clear=False),
        patch("app.jobs.seed.compute_hotspots"),
    ):
        seed_module.run_observation_source_ingestion("fake")

    db = Session()
    run = db.query(IngestRun).filter(IngestRun.ingest_source == "fake").one()
    assert run.records_fetched == 2
    assert run.records_rejected == 1
    assert run.evidence_inserted == 1
    assert run.observations_inserted == 1
    assert run.reject_counts_json == '{"classified_out":1}'
    db.close()


def test_bad_location_manual_link_is_zero_weight_provenance_only():
    engine = _engine()
    db = _session(engine)
    event = Event(
        source_id="confirmed-1",
        source_name="gdelt",
        event_type="protest",
        title="Confirmed Philadelphia protest",
        summary="Confirmed protest in Philadelphia.",
        city="Philadelphia",
        state="PA",
        country="US",
        latitude=39.9526,
        longitude=-75.1652,
        occurred_at=datetime(2026, 5, 7, 12, 0, 0),
        confidence_score=0.7,
        severity_score=0.4,
        source_count=1,
        is_active=True,
        location_precision="city",
    )
    db.add(event)
    db.commit()
    lead = _lead(db, source_type="eventregistry", record_id="bad-link", trust_tier="news", location_confidence=0.3)

    link_observation_to_event(db, lead.id, event.id)
    db.commit()

    linked = db.query(EventSource).filter(EventSource.event_id == event.id).one()
    assert linked.source_trust_weight == 0.0
    assert event.source_count == 1
    assert event.confidence_score == 0.7
    assert lead.status == "linked"
    db.close()
    Base.metadata.drop_all(bind=engine)


def test_sources_status_lists_enabled_sources_before_first_run():
    engine = _engine()
    client = _client(engine)

    with patch("app.config.settings.bluesky_enabled", True):
        try:
            response = client.get("/api/v1/sources/status")
            assert response.status_code == 200
            names = [source["source_name"] for source in response.json()["sources"]]
            assert "bluesky" in names
        finally:
            app.dependency_overrides.clear()
            Base.metadata.drop_all(bind=engine)
