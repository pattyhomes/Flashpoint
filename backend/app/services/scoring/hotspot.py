"""
Hotspot clustering and scoring.

Algorithm:
  1. Clear any stale cluster_id / trend_state on all active events.
  2. Load all active events.
  3. Two-pass greedy radius clustering to derive centroid candidates from event density.
  4. Delete all existing Hotspot rows; insert new ones from candidates; flush to get IDs.
  5. Compute severity, confidence, momentum, priority, and trend_state from each cluster's members.
  6. Write cluster_id and trend_state back to each assigned Event.
  7. Write all computed scores back to each Hotspot.
"""
from datetime import datetime
from collections import defaultdict
import math

from sqlalchemy.orm import Session

from app.models import Event, Hotspot

CLUSTER_RADIUS_MILES = 150   # metro-region radius — events within this distance merge
MIN_EVENTS           = 3     # minimum members to form a hotspot
MAX_HOTSPOTS         = 15    # cap to avoid UI clutter

_COUNTRY_LEVEL_LABELS = frozenset({"United States", "United States of America"})

_US_STATE_NAMES = frozenset({
    "Alabama", "Alaska", "Arizona", "Arkansas", "California", "Colorado",
    "Connecticut", "Delaware", "Florida", "Georgia", "Hawaii", "Idaho",
    "Illinois", "Indiana", "Iowa", "Kansas", "Kentucky", "Louisiana",
    "Maine", "Maryland", "Massachusetts", "Michigan", "Minnesota",
    "Mississippi", "Missouri", "Montana", "Nebraska", "Nevada",
    "New Hampshire", "New Jersey", "New Mexico", "New York",
    "North Carolina", "North Dakota", "Ohio", "Oklahoma", "Oregon",
    "Pennsylvania", "Rhode Island", "South Carolina", "South Dakota",
    "Tennessee", "Texas", "Utah", "Vermont", "Virginia", "Washington",
    "West Virginia", "Wisconsin", "Wyoming",
})

_STATE_ABBREV_TO_NAME = {
    "AL": "Alabama", "AK": "Alaska", "AZ": "Arizona", "AR": "Arkansas",
    "CA": "California", "CO": "Colorado", "CT": "Connecticut", "DE": "Delaware",
    "FL": "Florida", "GA": "Georgia", "HI": "Hawaii", "ID": "Idaho",
    "IL": "Illinois", "IN": "Indiana", "IA": "Iowa", "KS": "Kansas",
    "KY": "Kentucky", "LA": "Louisiana", "ME": "Maine", "MD": "Maryland",
    "MA": "Massachusetts", "MI": "Michigan", "MN": "Minnesota", "MS": "Mississippi",
    "MO": "Missouri", "MT": "Montana", "NE": "Nebraska", "NV": "Nevada",
    "NH": "New Hampshire", "NJ": "New Jersey", "NM": "New Mexico", "NY": "New York",
    "NC": "North Carolina", "ND": "North Dakota", "OH": "Ohio", "OK": "Oklahoma",
    "OR": "Oregon", "PA": "Pennsylvania", "RI": "Rhode Island", "SC": "South Carolina",
    "SD": "South Dakota", "TN": "Tennessee", "TX": "Texas", "UT": "Utah",
    "VT": "Vermont", "VA": "Virginia", "WA": "Washington", "WV": "West Virginia",
    "WI": "Wisconsin", "WY": "Wyoming", "DC": "Washington, D.C.",
}


def _haversine_miles(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    R = 3958.8
    lat1, lat2 = math.radians(lat1), math.radians(lat2)
    dlat = lat2 - lat1
    dlon = math.radians(lon2 - lon1)
    a = (math.sin(dlat / 2) ** 2
         + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2)
    return 2 * R * math.asin(math.sqrt(a))


def _is_country_level(event: Event) -> bool:
    return event.city is not None and event.city in _COUNTRY_LEVEL_LABELS


def _is_state_level(event: Event) -> bool:
    if event.city is None:
        return False
    if event.city in _US_STATE_NAMES:
        return True
    if event.city == event.state:
        return True
    return False


def _cluster_events(events: list[Event]) -> list[dict]:
    """
    Two-pass greedy radius clustering.

    Pass 1: Sort events by occurred_at DESC. Precise city/county events may anchor
    new clusters; state-level events only join existing clusters in pass 1.

    Pass 2: State-level events that remain unassigned are grouped by state.
    If a state group has >= MIN_EVENTS members it becomes a fallback cluster.

    Returns a list of candidate dicts: {lat, lon, members}.
    """
    sorted_events = sorted(events, key=lambda e: e.occurred_at or datetime.min, reverse=True)

    candidates: list[dict] = []   # {lat, lon, n, members}
    unassigned_state: list[Event] = []

    for event in sorted_events:
        state_level   = _is_state_level(event)
        country_level = _is_country_level(event)

        # Find nearest existing candidate
        nearest_idx, nearest_d = -1, float("inf")
        for i, c in enumerate(candidates):
            d = _haversine_miles(event.latitude, event.longitude, c["lat"], c["lon"])
            if d < nearest_d:
                nearest_d, nearest_idx = d, i

        if nearest_d <= CLUSTER_RADIUS_MILES:
            # Merge into nearest candidate via running mean (all events may join)
            c = candidates[nearest_idx]
            n = c["n"]
            c["lat"] = (c["lat"] * n + event.latitude)  / (n + 1)
            c["lon"] = (c["lon"] * n + event.longitude) / (n + 1)
            c["n"]  += 1
            c["members"].append(event)
        elif not state_level and not country_level:
            # Precise city/county event starts a new cluster
            candidates.append({
                "lat": event.latitude,
                "lon": event.longitude,
                "n": 1,
                "members": [event],
            })
        elif state_level:
            # State-level event with no nearby cluster — defer to pass 2 fallback
            unassigned_state.append(event)
        # Country-level events that can't join are dropped (remain unassigned —
        # too imprecise to anchor or fall back to a named hotspot)

    # Pass 2: state-region fallback clusters
    by_state: dict[str, list[Event]] = defaultdict(list)
    for event in unassigned_state:
        key = event.state or "unknown"
        by_state[key].append(event)

    for state_key, members in by_state.items():
        if len(members) < MIN_EVENTS:
            continue
        lat = sum(e.latitude  for e in members) / len(members)
        lon = sum(e.longitude for e in members) / len(members)
        candidates.append({"lat": lat, "lon": lon, "n": len(members), "members": members})

    # Prune under-threshold candidates
    candidates = [c for c in candidates if len(c["members"]) >= MIN_EVENTS]

    # Sort by member count descending, cap
    candidates.sort(key=lambda c: len(c["members"]), reverse=True)
    return candidates[:MAX_HOTSPOTS]


def _hotspot_name(members: list[Event]) -> str:
    # 1. City: most common city that is NOT a state/country-level label and NOT a county/parish
    cities = [e.city for e in members
              if e.city
              and e.city not in _US_STATE_NAMES
              and e.city not in _COUNTRY_LEVEL_LABELS
              and "county" not in e.city.lower()
              and "parish" not in e.city.lower()
              and e.city != e.state]
    if cities:
        best = max(set(cities), key=cities.count)
        states = [e.state for e in members if e.city == best and e.state]
        st = max(set(states), key=states.count) if states else None
        return f"{best}, {st}" if st else best

    # 2. County/Parish
    counties = [e.city for e in members
                if e.city and ("county" in e.city.lower()
                               or "parish" in e.city.lower())]
    if counties:
        best = max(set(counties), key=counties.count)
        states = [e.state for e in members if e.city == best and e.state]
        st = max(set(states), key=states.count) if states else None
        return f"{best}, {st}" if st else best

    # 3. State region (full state name to avoid abbreviation ambiguity)
    states = [e.state for e in members if e.state]
    if states:
        best_abbrev = max(set(states), key=states.count)
        full_name = _STATE_ABBREV_TO_NAME.get(best_abbrev, best_abbrev)
        return f"{full_name} region"

    # 4. Coordinate fallback
    lat = sum(e.latitude  for e in members) / len(members)
    lon = sum(e.longitude for e in members) / len(members)
    return f"Cluster ({lat:.1f}°N, {abs(lon):.1f}°W)"


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
    """Derive hotspot clusters from event density and compute all scores."""
    now = datetime.utcnow()

    # Clear stale assignments so no orphaned state persists across recomputes
    db.query(Event).filter(Event.is_active == True).update(
        {"cluster_id": None, "trend_state": None}
    )
    db.flush()

    events = db.query(Event).filter(Event.is_active == True).all()
    if not events:
        db.query(Hotspot).delete()
        db.commit()
        return

    clusters = _cluster_events(events)

    # Replace existing hotspots with dynamically derived ones
    db.query(Hotspot).delete()
    db.flush()

    hotspots = []
    for c in clusters:
        h = Hotspot(
            name=_hotspot_name(c["members"]),
            centroid_lat=c["lat"],
            centroid_lon=c["lon"],
        )
        db.add(h)
        hotspots.append((h, c["members"]))
    db.flush()  # populate auto-increment IDs

    for hotspot, members in hotspots:
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
    total_assigned = sum(len(m) for _, m in hotspots)
    print(f"[hotspot] {len(hotspots)} clusters, {total_assigned}/{len(events)} events assigned.")
