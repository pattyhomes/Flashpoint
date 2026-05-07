from datetime import datetime

import httpx

from app.config import settings
from app.services.ingestion.base import ObservationCandidate
from app.services.ingestion.classifier import classify


DEFAULT_QUERY_PACK = (
    "protest",
    "demonstration",
    "march downtown",
    "police clash protest",
    "road blocked protest",
)


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).replace(tzinfo=None)
    except ValueError:
        return None


class BlueskySource:
    source_name = "bluesky"

    def fetch(self) -> list[ObservationCandidate]:
        candidates_by_record: dict[str | None, ObservationCandidate] = {}
        for query in _queries():
            for candidate in self._fetch_query(query):
                candidates_by_record.setdefault(candidate.source_record_id, candidate)
        return list(candidates_by_record.values())

    def _fetch_query(self, query: str) -> list[ObservationCandidate]:
        try:
            resp = httpx.get(
                "https://public.api.bsky.app/xrpc/app.bsky.feed.searchPosts",
                params={"q": query, "limit": settings.bluesky_max_records},
                timeout=30,
            )
            resp.raise_for_status()
            data = resp.json()
        except Exception as exc:
            print(f"[bluesky] Fetch error: {exc}")
            return []

        candidates = []
        for post in data.get("posts", []):
            record = post.get("record") or {}
            text = (record.get("text") or "").strip()
            if not text:
                continue
            result = classify(title=text[:180], body=text, categories=[], concepts=[], min_score=0.5)
            if result is None:
                continue
            author = post.get("author") or {}
            handle = author.get("handle")
            uri = post.get("uri")
            candidates.append(
                ObservationCandidate(
                    source_type="bluesky",
                    source_record_id=uri,
                    source_url=f"https://bsky.app/profile/{handle}/post/{uri.rsplit('/', 1)[-1]}" if uri and handle else None,
                    source_name=handle or "Bluesky",
                    source_title=text[:160],
                    excerpt=text,
                    published_at=_parse_dt(record.get("createdAt") or post.get("indexedAt")),
                    trust_tier="weak",
                    raw_payload=post,
                    status="lead",
                    title=text[:160],
                    summary=text,
                    candidate_event_type=result.event_type,
                    observed_at=_parse_dt(record.get("createdAt") or post.get("indexedAt")),
                    confidence_score=min(0.42, 0.18 + result.score * 0.25),
                    severity_score=0.2,
                )
            )
        return candidates


def _queries() -> list[str]:
    configured = settings.bluesky_query_pack
    queries = [part.strip() for part in configured.split(",") if part.strip()]
    return queries or list(DEFAULT_QUERY_PACK)
