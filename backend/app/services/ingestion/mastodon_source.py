import re
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


def _strip_html(value: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", value or "")).strip()


class MastodonSource:
    source_name = "mastodon"

    def fetch(self) -> list[ObservationCandidate]:
        if not settings.mastodon_access_token:
            return []
        candidates_by_record: dict[str | None, ObservationCandidate] = {}
        for query in _queries():
            for candidate in self._fetch_query(query):
                candidates_by_record.setdefault(candidate.source_record_id, candidate)
        return list(candidates_by_record.values())

    def _fetch_query(self, query: str) -> list[ObservationCandidate]:
        try:
            resp = httpx.get(
                f"{settings.mastodon_instance_url.rstrip('/')}/api/v2/search",
                params={
                    "q": query,
                    "type": "statuses",
                    "limit": settings.mastodon_max_records,
                },
                headers={"Authorization": f"Bearer {settings.mastodon_access_token}"},
                timeout=30,
            )
            resp.raise_for_status()
            data = resp.json()
        except Exception as exc:
            print(f"[mastodon] Fetch error: {exc}")
            return []

        candidates = []
        for status in data.get("statuses", []):
            text = _strip_html(status.get("content") or "")
            if not text:
                continue
            result = classify(title=text[:180], body=text, categories=[], concepts=[], min_score=0.5)
            if result is None:
                continue
            account = status.get("account") or {}
            candidates.append(
                ObservationCandidate(
                    source_type="mastodon",
                    source_record_id=status.get("id"),
                    source_url=status.get("url"),
                    source_name=account.get("acct") or "Mastodon",
                    source_title=text[:160],
                    excerpt=text,
                    published_at=_parse_dt(status.get("created_at")),
                    trust_tier="weak",
                    raw_payload=status,
                    status="lead",
                    title=text[:160],
                    summary=text,
                    candidate_event_type=result.event_type,
                    observed_at=_parse_dt(status.get("created_at")),
                    confidence_score=min(0.42, 0.18 + result.score * 0.25),
                    severity_score=0.2,
                )
            )
        return candidates


def _queries() -> list[str]:
    configured = settings.mastodon_query_pack
    queries = [part.strip() for part in configured.split(",") if part.strip()]
    return queries or list(DEFAULT_QUERY_PACK)
