import json
import importlib.util
from datetime import timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.models import Event, EventSource, EvidenceItem, IngestRun, Observation
from app.schemas import EventCreate
from app.services.article_metadata import ArticleMetadata, fetch_article_metadata, is_specific_unrest_metadata
from app.services.event_quality import event_quality
from app.services.scoring.hotspot import compute_hotspots
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


def _gdelt_event(**overrides):
    now = utcnow_naive()
    values = {
        "source_id": "gdelt-1",
        "title": "Violence — Tennessee",
        "event_type": "violence",
        "latitude": 35.9,
        "longitude": -86.7,
        "city": "Tennessee",
        "state": "TN",
        "country": "US",
        "occurred_at": now,
        "source_name": "gdelt",
        "source_url": "https://example.org/story",
        "source_count": 1,
        "confidence_score": 0.7,
        "severity_score": 0.9,
        "location_precision": "state",
        "raw_payload_json": "{}",
    }
    values.update(overrides)
    return EventCreate(**values)


def test_article_fetcher_blocks_private_urls_without_slug_inference():
    metadata = fetch_article_metadata("http://127.0.0.1/specific-looking-url-slug")

    assert metadata.usable is False
    assert metadata.title is None
    assert "public" in metadata.reason


def test_article_fetcher_uses_og_title_when_specific():
    response = MagicMock()
    response.content = b'<html><head><meta property="og:title" content="Protesters block downtown Nashville street"></head><body>Story text.</body></html>'
    response.headers = {"content-type": "text/html"}
    response.encoding = "utf-8"
    response.url = "https://news.example/story"
    response.raise_for_status.return_value = None

    robots = MagicMock(text="User-agent: *\nAllow: /\n", status_code=200)

    def fake_get(url, **_kwargs):
        if url.endswith("/robots.txt"):
            return robots
        return response

    with (
        patch("app.services.article_metadata.socket.getaddrinfo", return_value=[]),
        patch("app.services.article_metadata.httpx.get", side_effect=fake_get),
    ):
        metadata = fetch_article_metadata("https://news.example/story", rate_limit_seconds=0)

    assert metadata.usable is True
    assert metadata.title == "Protesters block downtown Nashville street"
    assert is_specific_unrest_metadata(metadata) is True


def test_specific_article_title_still_needs_unrest_signal():
    metadata = ArticleMetadata(
        title="Wildfire building rules trigger mix of compliance and skepticism",
        excerpt="A policy story about wildfire building rules.",
        final_url="https://example.org/wildfire",
    )

    assert metadata.usable is True
    assert is_specific_unrest_metadata(metadata) is False


def test_gdelt_state_record_becomes_observation_not_confirmed_event():
    import app.jobs.seed as seed_module

    engine = _engine()
    Session = sessionmaker(bind=engine)

    with (
        patch.object(seed_module, "SessionLocal", Session),
        patch("app.services.ingestion.gdelt_source.GdeltSource") as source_cls,
        patch("app.jobs.seed.fetch_article_metadata", return_value=ArticleMetadata(None, None, "https://example.org/story", "No title")),
    ):
        source_cls.return_value.fetch.return_value = [_gdelt_event()]
        seed_module.run_gdelt_ingestion()

    db = _session(engine)
    try:
        assert db.query(Event).count() == 0
        assert db.query(EvidenceItem).filter(EvidenceItem.source_type == "gdelt").count() == 1
        observation = db.query(Observation).one()
        assert observation.status == "lead"
        assert observation.exception_category == "broad_detector"
        run = db.query(IngestRun).one()
        counts = json.loads(run.reject_counts_json)
        assert counts["records_gated_low_specificity"] == 1
        assert counts["records_detector_only"] == 1
    finally:
        db.close()
        Base.metadata.drop_all(bind=engine)


def test_gdelt_city_record_with_specific_article_becomes_hotspot_eligible_event():
    import app.jobs.seed as seed_module

    engine = _engine()
    Session = sessionmaker(bind=engine)
    event = _gdelt_event(
        source_id="gdelt-city",
        title="Violence — Nashville",
        city="Nashville",
        location_precision="city",
        latitude=36.16,
        longitude=-86.78,
    )

    with (
        patch.object(seed_module, "SessionLocal", Session),
        patch("app.services.ingestion.gdelt_source.GdeltSource") as source_cls,
        patch("app.jobs.seed.fetch_article_metadata", return_value=ArticleMetadata("Protesters block downtown Nashville street", "Story body", "https://example.org/story")),
    ):
        source_cls.return_value.fetch.return_value = [event]
        seed_module.run_gdelt_ingestion()

    db = _session(engine)
    try:
        stored = db.query(Event).one()
        sources = db.query(EventSource).filter(EventSource.event_id == stored.id).all()
        quality = event_quality(stored, sources)
        assert quality.quality_tier == "article_backed_classification"
        assert quality.eligible_for_hotspots is True
        assert sources[0].source_title == "Protesters block downtown Nashville street"
    finally:
        db.close()
        Base.metadata.drop_all(bind=engine)


def test_hotspot_recompute_excludes_detector_only_but_keeps_article_backed():
    engine = _engine()
    db = _session(engine)
    now = utcnow_naive()
    for index in range(3):
        event = Event(
            source_id=f"generic-{index}",
            title="Violence — Tennessee",
            event_type="violence",
            city="Tennessee",
            state="TN",
            country="US",
            latitude=35.9,
            longitude=-86.7,
            occurred_at=now - timedelta(hours=index),
            source_name="gdelt",
            source_count=1,
            confidence_score=0.7,
            severity_score=0.9,
            location_precision="state",
        )
        db.add(event)
    for index in range(3):
        event = Event(
            source_id=f"specific-{index}",
            title="Violence — Nashville",
            event_type="violence",
            city="Nashville",
            state="TN",
            country="US",
            latitude=36.16,
            longitude=-86.78,
            occurred_at=now - timedelta(hours=index),
            source_name="gdelt",
            source_count=1,
            confidence_score=0.7,
            severity_score=0.9,
            location_precision="city",
        )
        db.add(event)
        db.flush()
        db.add(EventSource(
            event_id=event.id,
            source_type="article",
            source_record_id=event.source_id,
            source_name="GDELT source article",
            source_url="https://example.org/story",
            source_title=f"Protesters block downtown Nashville street {index}",
            source_trust_weight=1.0,
            location_precision="city",
        ))
    db.commit()

    try:
        compute_hotspots(db)
        hotspots = db.query(Event).filter(Event.cluster_id.isnot(None)).all()
        assert len(hotspots) == 3
        assert {event.city for event in hotspots} == {"Nashville"}
    finally:
        db.close()
        Base.metadata.drop_all(bind=engine)


def test_backfill_dry_run_reports_without_mutation():
    script_path = Path(__file__).resolve().parents[2] / "scripts" / "backfill_event_specificity.py"
    spec = importlib.util.spec_from_file_location("backfill_event_specificity", script_path)
    backfill = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(backfill)

    engine = _engine()
    Session = sessionmaker(bind=engine)
    db = _session(engine)
    event = Event(
        source_id="gdelt-backfill",
        title="Violence — Nashville",
        event_type="violence",
        city="Nashville",
        state="TN",
        country="US",
        latitude=36.16,
        longitude=-86.78,
        occurred_at=utcnow_naive(),
        source_name="gdelt",
        source_url="https://example.org/story",
        source_count=1,
        confidence_score=0.7,
        severity_score=0.9,
        location_precision="city",
    )
    db.add(event)
    db.commit()
    db.close()

    with (
        patch.object(backfill, "SessionLocal", Session),
        patch.object(backfill, "_migrate"),
        patch.object(backfill, "fetch_article_metadata", return_value=ArticleMetadata("Protesters block downtown Nashville street", "Story body", "https://example.org/story")),
    ):
        report = backfill.run(apply=False, limit=10, hours=72)

    db = _session(engine)
    try:
        assert report["likely_enrichable_records"] == 1
        assert db.query(EventSource).count() == 0
    finally:
        db.close()
        Base.metadata.drop_all(bind=engine)
