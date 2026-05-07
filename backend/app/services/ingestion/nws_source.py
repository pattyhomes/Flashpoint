from datetime import datetime

import httpx

from app.config import settings
from app.services.ingestion.base import ObservationCandidate


_SEVERITY = {
    "Extreme": 0.95,
    "Severe": 0.75,
    "Moderate": 0.45,
    "Minor": 0.25,
    "Unknown": 0.15,
}


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).replace(tzinfo=None)
    except ValueError:
        return None


def _centroid(geometry: dict | None) -> tuple[float | None, float | None]:
    if not geometry:
        return None, None
    coords = geometry.get("coordinates")
    if not coords:
        return None, None
    points: list[tuple[float, float]] = []

    def collect(value):
        if (
            isinstance(value, list)
            and len(value) >= 2
            and all(isinstance(v, (int, float)) for v in value[:2])
        ):
            points.append((float(value[1]), float(value[0])))
            return
        if isinstance(value, list):
            for item in value:
                collect(item)

    collect(coords)
    if not points:
        return None, None
    return sum(p[0] for p in points) / len(points), sum(p[1] for p in points) / len(points)


class NwsAlertsSource:
    source_name = "nws"

    def fetch(self) -> list[ObservationCandidate]:
        params = {}
        if settings.nws_alerts_area:
            params["area"] = settings.nws_alerts_area
        try:
            resp = httpx.get(
                "https://api.weather.gov/alerts/active",
                params=params,
                headers={"User-Agent": "Flashpoint/0.1 local intelligence workstation"},
                timeout=30,
            )
            resp.raise_for_status()
            data = resp.json()
        except Exception as exc:
            print(f"[nws] Fetch error: {exc}")
            return []

        candidates = []
        for feature in data.get("features", []):
            props = feature.get("properties") or {}
            title = props.get("headline") or props.get("event") or "NWS alert"
            lat, lon = _centroid(feature.get("geometry"))
            candidates.append(
                ObservationCandidate(
                    source_type="nws",
                    source_record_id=props.get("id") or feature.get("id"),
                    source_url=props.get("@id") or props.get("id"),
                    source_name="National Weather Service",
                    source_title=title,
                    excerpt=props.get("description") or props.get("instruction"),
                    published_at=_parse_dt(props.get("sent")),
                    trust_tier="authoritative",
                    raw_payload=feature,
                    status="context",
                    title=title,
                    summary=props.get("description"),
                    latitude=lat,
                    longitude=lon,
                    observed_at=_parse_dt(props.get("effective")) or _parse_dt(props.get("sent")),
                    confidence_score=1.0,
                    severity_score=_SEVERITY.get(props.get("severity"), 0.15),
                    location_precision="area" if lat is not None and lon is not None else None,
                )
            )
        return candidates
