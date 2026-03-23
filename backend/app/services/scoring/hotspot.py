"""
Hotspot clustering and scoring.

Algorithm:
  1. Clear any stale cluster_id / trend_state on all active events.
  2. Load all active events and all hotspot centroids from DB.
  3. Assign each event to the nearest hotspot centroid within MAX_RADIUS degrees.
  4. Compute severity, confidence, momentum, priority, and trend_state from members.
  5. Write cluster_id and trend_state back to each assigned Event.
  6. Write all computed scores back to each Hotspot.
"""
from datetime import datetime
import math

from sqlalchemy.orm import Session

from app.models import Event, Hotspot

MAX_RADIUS = 3.0  # degrees lat/lon; ~220 mi at US latitudes


def _dist(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    return math.sqrt((lat1 - lat2) ** 2 + (lon1 - lon2) ** 2)


def _assign_events(
    events: list[Event], hotspots: list[Hotspot]
) -> dict[int, list[Event]]:
    clusters: dict[int, list[Event]] = {h.id: [] for h in hotspots}
    for event in events:
        nearest_id, nearest_dist = None, float("inf")
        for h in hotspots:
            d = _dist(event.latitude, event.longitude, h.centroid_lat, h.centroid_lon)
            if d < nearest_dist:
                nearest_dist, nearest_id = d, h.id
        if nearest_dist <= MAX_RADIUS and nearest_id is not None:
            clusters[nearest_id].append(event)
    return clusters


def _severity(members: list[Event]) -> float:
    if not members:
        return 0.0
    scores = [e.severity_score for e in members]
    return round(0.7 * max(scores) + 0.3 * (sum(scores) / len(scores)), 3)


def _confidence(members: list[Event]) -> float:
    if not members:
        return 0.0
    return round(sum(e.confidence_score for e in members) / len(members), 3)


def _momentum(members: list[Event], now: datetime) -> float:
    if not members:
        return 0.0
    total = sum(
        e.severity_score * max(0.0, 1.0 - (now - e.occurred_at).total_seconds() / 86400)
        for e in members
    )
    return round(min(1.0, total / len(members)), 3)


def _priority(sev: float, mom: float, count: int) -> float:
    return round(0.5 * sev + 0.3 * mom + 0.2 * min(1.0, count / 5.0), 3)


def _trend(members: list[Event], now: datetime) -> str:
    recent  = [e for e in members if (now - e.occurred_at).total_seconds() <  8 * 3600]
    earlier = [e for e in members if 8 * 3600 <= (now - e.occurred_at).total_seconds() < 24 * 3600]
    r_count, e_count = len(recent), len(earlier)
    r_sev = sum(e.severity_score for e in recent)  / r_count if r_count else 0.0
    e_sev = sum(e.severity_score for e in earlier) / e_count if e_count else 0.0
    if r_count > e_count or r_sev > e_sev + 0.15:
        return "escalating"
    if e_count > r_count * 2 and e_sev > r_sev:
        return "declining"
    return "stable"


def _status(priority: float, trend: str) -> str:
    if priority >= 0.8 and trend == "escalating":
        return "Active Hotspot"
    if priority >= 0.6:
        return "Elevated Activity"
    if trend == "escalating":
        return "Emerging"
    if trend == "declining":
        return "De-escalating"
    return "Monitored"


def compute_hotspots(db: Session) -> None:
    """Assign events to hotspot clusters and recompute all scores in-place."""
    now = datetime.utcnow()

    # Clear stale assignments so no orphaned state persists across recomputes
    db.query(Event).filter(Event.is_active == True).update(
        {"cluster_id": None, "trend_state": None}
    )
    db.flush()

    events   = db.query(Event).filter(Event.is_active == True).all()
    hotspots = db.query(Hotspot).all()
    if not hotspots:
        db.commit()
        return

    clusters = _assign_events(events, hotspots)

    for hotspot in hotspots:
        members = clusters[hotspot.id]
        trend = _trend(members, now)

        for e in members:
            e.cluster_id  = hotspot.id
            e.trend_state = trend

        sev  = _severity(members)
        conf = _confidence(members)
        mom  = _momentum(members, now)
        pri  = _priority(sev, mom, len(members))

        hotspot.event_count      = len(members)
        hotspot.severity_score   = sev
        hotspot.confidence_score = conf
        hotspot.momentum_score   = mom
        hotspot.priority_score   = pri
        hotspot.trend_state      = trend
        hotspot.status_label     = _status(pri, trend)
        hotspot.last_computed_at = now

    db.commit()
    print(f"[hotspot] Computed {len(hotspots)} hotspots from {len(events)} events.")
