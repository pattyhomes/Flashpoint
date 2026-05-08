import json
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app


def _engine():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    return engine


@pytest.fixture
def db_engine():
    engine = _engine()
    try:
        yield engine
    finally:
        Base.metadata.drop_all(bind=engine)
        app.dependency_overrides.clear()


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
    return TestClient(app)


def test_rss_registry_loads_enabled_regional_pilot_feeds():
    from app.services.ingestion.rss_registry import load_enabled_local_news_feeds

    feeds = load_enabled_local_news_feeds()

    names = {feed.name for feed in feeds}
    assert {"LAist", "Texas Tribune"} <= names
    assert "ABC News U.S." not in names
    assert all(feed.feed_url for feed in feeds)
    assert all(feed.allowed_domains for feed in feeds)
    assert any(feed.name == "LAist" and feed.feed_url == "https://laist.com/news.rss" for feed in feeds)
    assert any("laist.com" in feed.allowed_domains for feed in feeds)
    assert any("feeds.texastribune.org" in feed.allowed_domains for feed in feeds)


def test_rss_registry_rejects_enabled_feed_without_allowlist(tmp_path):
    from app.services.ingestion.rss_registry import load_feed_registry

    registry = tmp_path / "feeds.csv"
    registry.write_text(
        "name,feed_url,allowed_domains,region,source_family,enabled,notes\n"
        "Unsafe,https://unsafe.test/rss.xml,,Test,news,true,missing allowlist\n",
        encoding="utf-8",
    )

    try:
        load_feed_registry(registry, enabled_only=True)
    except ValueError as exc:
        assert "Unsafe" in str(exc)
        assert "allowlist" in str(exc)
    else:
        raise AssertionError("enabled feed without allowlist should fail")


def test_local_news_uses_enabled_registry_when_env_feed_list_empty():
    from app.services.ingestion.local_news_source import LocalNewsSource

    feed = """<?xml version="1.0"?>
    <rss version="2.0"><channel>
      <item>
        <guid>laist-1</guid>
        <title>Protest march reported in Los Angeles, CA</title>
        <link>https://laist.com/news/laist-1</link>
        <description>Demonstrators marched in downtown Los Angeles, CA.</description>
        <pubDate>Thu, 07 May 2026 12:00:00 GMT</pubDate>
      </item>
    </channel></rss>
    """
    feed_response = MagicMock(text=feed)
    feed_response.raise_for_status.return_value = None
    robots_response = MagicMock(text="User-agent: *\nAllow: /\n", status_code=200)
    robots_response.raise_for_status.return_value = None
    article_response = MagicMock(text="<article>Hundreds protested in Los Angeles, CA.</article>")
    article_response.raise_for_status.return_value = None

    def fake_get(url, **_kwargs):
        if url.endswith("/robots.txt"):
            return robots_response
        if "laist-1" in url:
            return article_response
        return feed_response

    with (
        patch("app.config.settings.local_news_enabled", True),
        patch("app.config.settings.local_news_feed_urls", ""),
        patch("app.config.settings.local_news_allowed_domains", ""),
        patch("app.config.settings.local_news_max_records", 5),
        patch("app.services.ingestion.rss_registry.load_enabled_local_news_feeds") as load_feeds,
        patch("app.services.ingestion.local_news_source.httpx.get", side_effect=fake_get),
    ):
        load_feeds.return_value = [
            type(
                "Feed",
                (),
                {
                    "name": "LAist",
                    "feed_url": "https://laist.com/news.rss",
                    "allowed_domains": ("laist.com",),
                },
            )()
        ]
        candidates = LocalNewsSource().fetch()

    assert len(candidates) == 1
    assert candidates[0].source_name == "LAist"
    assert candidates[0].city == "Los Angeles"
    assert candidates[0].state == "CA"


def test_local_news_follows_feed_redirect_links_to_allowlisted_article_domain():
    from app.services.ingestion.local_news_source import LocalNewsSource

    feed = """<?xml version="1.0"?>
    <rss version="2.0"><channel>
      <item>
        <guid>tt-1</guid>
        <title>Protest update after downtown gathering</title>
        <link>https://feeds.texastribune.org/link/16799/tt-1/austin-road-closure</link>
        <description>Brief update from the newsroom.</description>
        <pubDate>Thu, 07 May 2026 12:00:00 GMT</pubDate>
      </item>
    </channel></rss>
    """
    feed_response = MagicMock(text=feed)
    feed_response.raise_for_status.return_value = None
    robots_response = MagicMock(text="User-agent: *\nAllow: /\n", status_code=200)
    robots_response.raise_for_status.return_value = None
    article_response = MagicMock(
        text="<article>Protesters set up a road blockade in downtown Austin, TX.</article>",
        url="https://www.texastribune.org/2026/05/07/austin-road-closure/",
    )
    article_response.raise_for_status.return_value = None

    def fake_get(url, **kwargs):
        if url == "https://feeds.texastribune.org/feeds/main/":
            return feed_response
        if url == "https://feeds.texastribune.org/robots.txt":
            return robots_response
        if url == "https://feeds.texastribune.org/link/16799/tt-1/austin-road-closure":
            if not kwargs.get("follow_redirects"):
                raise RuntimeError("redirect was not followed")
            return article_response
        raise AssertionError(f"unexpected URL: {url}")

    with (
        patch("app.config.settings.local_news_enabled", True),
        patch("app.config.settings.local_news_feed_urls", ""),
        patch("app.config.settings.local_news_allowed_domains", ""),
        patch("app.config.settings.local_news_max_records", 5),
        patch("app.services.ingestion.rss_registry.load_enabled_local_news_feeds") as load_feeds,
        patch("app.services.ingestion.local_news_source.httpx.get", side_effect=fake_get),
    ):
        load_feeds.return_value = [
            type(
                "Feed",
                (),
                {
                    "name": "Texas Tribune",
                    "feed_url": "https://feeds.texastribune.org/feeds/main/",
                    "allowed_domains": ("feeds.texastribune.org", "www.texastribune.org"),
                },
            )()
        ]
        source = LocalNewsSource()
        candidates = source.fetch()

    assert len(candidates) == 1
    assert candidates[0].candidate_event_type == "protest"
    assert candidates[0].city == "Austin"
    assert candidates[0].state == "TX"
    assert "article_fetch_error" not in source.stats["reject_counts"]


def test_observation_source_ingestion_persists_sample_records(db_engine):
    import app.jobs.seed as seed_module
    from app.models import IngestRun

    Session = sessionmaker(bind=db_engine)

    class FakeSource:
        stats = {
            "fetched": 2,
            "rejected": 2,
            "reject_counts": {"classified_out": 2},
            "sample_records": [
                {
                    "category": "classified_out",
                    "source_name": "LAist",
                    "title": "City council approves budget",
                    "source_url": "https://laist.com/news/example",
                    "reason": "No unrest classifier signal.",
                }
            ],
        }

        def fetch(self):
            return []

    with (
        patch("app.jobs.seed.SessionLocal", side_effect=lambda: Session()),
        patch.dict(seed_module.OBSERVATION_SOURCE_MAP, {"local_news": ("local_news", FakeSource)}),
    ):
        seed_module.run_observation_source_ingestion("local_news")

    db = Session()
    run = db.query(IngestRun).filter(IngestRun.ingest_source == "local_news").one()
    samples = json.loads(run.sample_records_json)
    db.close()

    assert samples[0]["category"] == "classified_out"
    assert samples[0]["title"] == "City council approves budget"


def test_sources_status_exposes_sample_records(client, db_engine):
    from app.models import IngestRun
    from app.utils.time import utcnow_naive

    Session = sessionmaker(bind=db_engine)
    db = Session()
    db.add(IngestRun(
        started_at=utcnow_naive(),
        finished_at=utcnow_naive(),
        status="success",
        ingest_source="local_news",
        records_fetched=1,
        records_rejected=1,
        reject_counts_json=json.dumps({"classified_out": 1}),
        sample_records_json=json.dumps([
            {"category": "classified_out", "source_name": "LAist", "title": "Budget story"}
        ]),
    ))
    db.commit()
    db.close()

    response = client.get("/api/v1/sources/status")
    assert response.status_code == 200
    source = next(row for row in response.json()["sources"] if row["source_name"] == "local_news")
    assert source["sample_records"][0]["title"] == "Budget story"


def test_expanded_geocoder_resolves_alias_and_county():
    from app.services.geocoding import LocalGeocoder

    geocoder = LocalGeocoder()

    alias = geocoder.resolve(text="Large protest reported in Philly tonight")
    assert alias is not None
    assert alias.city == "Philadelphia"
    assert alias.state == "PA"
    assert alias.reason == "alias:city_state"

    county = geocoder.resolve(text="Road shutdown reported in Los Angeles County, CA")
    assert county is not None
    assert county.county == "Los Angeles"
    assert county.state == "CA"
    assert county.precision == "county"
    assert county.confidence >= 0.7


def test_stage15_eval_report_is_stable():
    from app.services.eval.stage15_eval import run_eval

    report = run_eval()

    assert report["total"] >= 30
    assert report["correct_event_type"] >= 20
    assert report["correct_exception_category"] >= 20
    assert report["false_event_creation"] == 0
    assert {"real_unrest", "bad_location", "false_positive", "social_only", "duplicate"} <= set(report["by_group"])


def test_manual_observation_ingest_helper_validates_source_names():
    script = Path(__file__).resolve().parents[2] / "scripts" / "run_observation_ingest.sh"

    assert script.exists()
    text = script.read_text(encoding="utf-8")
    assert "run_observation_source_ingestion" in text
    assert "nws|bluesky|mastodon|local_news|acled" in text
