from datetime import datetime, timedelta

import httpx

from app.config import settings
from app.services.ingestion.base import ObservationCandidate
from app.utils.time import utcnow_naive


_TYPE_MAP = {
    "Protests": "protest",
    "Riots": "riot",
    "Violence against civilians": "political_violence",
    "Explosions/Remote violence": "violence",
    "Battles": "violence",
    "Strategic developments": "unrest",
}


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    for fmt in ("%Y-%m-%d", "%d %B %Y"):
        try:
            return datetime.strptime(value[:32], fmt).replace(hour=12)
        except ValueError:
            continue
    return None


class AcledSource:
    source_name = "acled"

    def fetch(self) -> list[ObservationCandidate]:
        if not settings.acled_api_key:
            return []
        since = (utcnow_naive() - timedelta(days=settings.acled_lookback_days)).strftime("%Y-%m-%d")
        params = {
            "key": settings.acled_api_key,
            "limit": settings.acled_max_records,
            "event_date": since,
            "event_date_where": ">=",
            "country": "United States",
        }
        if settings.acled_email:
            params["email"] = settings.acled_email
        try:
            resp = httpx.get(settings.acled_api_url, params=params, timeout=30)
            resp.raise_for_status()
            data = resp.json()
        except Exception as exc:
            print(f"[acled] Fetch error: {exc}")
            return []

        rows = data.get("data") if isinstance(data, dict) else data
        if not isinstance(rows, list):
            return []

        candidates = []
        for row in rows:
            try:
                lat = float(row.get("latitude"))
                lon = float(row.get("longitude"))
            except (TypeError, ValueError):
                continue
            event_type = _TYPE_MAP.get(row.get("event_type"), "unrest")
            event_date = _parse_dt(row.get("event_date"))
            title = row.get("notes") or row.get("sub_event_type") or row.get("event_type") or "ACLED event"
            record_id = row.get("event_id_cnty") or row.get("event_id_no_cnty") or row.get("event_id")
            candidates.append(
                ObservationCandidate(
                    source_type="acled",
                    source_record_id=str(record_id) if record_id else None,
                    source_url=None,
                    source_name=row.get("source") or "ACLED",
                    source_title=title[:160],
                    excerpt=row.get("notes"),
                    published_at=event_date,
                    trust_tier="curated",
                    raw_payload=row,
                    status="lead",
                    title=title[:160],
                    summary=row.get("notes"),
                    candidate_event_type=event_type,
                    latitude=lat,
                    longitude=lon,
                    city=row.get("location"),
                    state=row.get("admin1"),
                    country="US",
                    observed_at=event_date,
                    confidence_score=0.72,
                    severity_score=0.55 if event_type in ("protest", "unrest") else 0.75,
                    location_precision="city",
                )
            )
        return candidates
