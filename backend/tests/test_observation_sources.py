from unittest.mock import MagicMock, patch

from app.services.ai_embeddings import embed_text
from app.services.ingestion.bluesky_source import BlueskySource
from app.services.ingestion.nws_source import NwsAlertsSource


def test_nws_alerts_normalize_to_context_observations():
    response = MagicMock()
    response.json.return_value = {
        "features": [
            {
                "id": "alert-1",
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [[[-75.2, 40.0], [-75.0, 40.0], [-75.0, 40.2], [-75.2, 40.2]]],
                },
                "properties": {
                    "id": "urn:oid:alert-1",
                    "@id": "https://api.weather.gov/alerts/alert-1",
                    "headline": "Severe Thunderstorm Warning issued",
                    "description": "Storm warning text.",
                    "sent": "2026-05-07T12:00:00Z",
                    "effective": "2026-05-07T12:05:00Z",
                    "severity": "Severe",
                },
            }
        ]
    }
    response.raise_for_status.return_value = None

    with patch("app.services.ingestion.nws_source.httpx.get", return_value=response):
        candidates = NwsAlertsSource().fetch()

    assert len(candidates) == 1
    assert candidates[0].source_type == "nws"
    assert candidates[0].status == "context"
    assert candidates[0].trust_tier == "authoritative"
    assert candidates[0].confidence_score == 1.0


def test_bluesky_search_normalizes_classified_posts_to_weak_leads():
    response = MagicMock()
    response.json.return_value = {
        "posts": [
            {
                "uri": "at://did:plc:test/app.bsky.feed.post/abc",
                "indexedAt": "2026-05-07T12:00:00Z",
                "author": {"handle": "example.bsky.social"},
                "record": {
                    "text": "Hundreds of protesters march through downtown tonight",
                    "createdAt": "2026-05-07T11:59:00Z",
                },
            }
        ]
    }
    response.raise_for_status.return_value = None

    with patch("app.services.ingestion.bluesky_source.httpx.get", return_value=response):
        candidates = BlueskySource().fetch()

    assert len(candidates) == 1
    assert candidates[0].source_type == "bluesky"
    assert candidates[0].status == "lead"
    assert candidates[0].trust_tier == "weak"
    assert candidates[0].candidate_event_type == "protest"
    assert candidates[0].latitude is None


def test_ollama_embedding_failure_returns_none():
    with (
        patch("app.config.settings.ollama_embeddings_enabled", True),
        patch("app.services.ai_embeddings.httpx.post", side_effect=RuntimeError("offline")),
    ):
        assert embed_text("protest downtown") is None
