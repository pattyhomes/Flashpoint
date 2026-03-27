"""
Deduplication utilities for Flashpoint ingestion.

Provides three layers of duplicate detection:

1. is_duplicate(source_id, db)
   Exact source_id match. Fast. Used for all sources.

2. find_matching_event(...)
   Cross-source similarity matching. Finds an existing Event that likely
   describes the same real-world incident as a new article, using location
   proximity, time proximity, and title similarity.

3. is_syndicated_copy(article, existing_sources)
   Detects syndicated/near-duplicate copies within the event_sources table.
   Prevents fake corroboration from wire service republication.
"""

import re
from datetime import datetime, timedelta
import math
from urllib.parse import urlparse

from sqlalchemy.orm import Session

from app.models import Event, EventSource


# ---------------------------------------------------------------------------
# Stop words (shared with classifier)
# ---------------------------------------------------------------------------

_STOP_WORDS = frozenset({
    "a", "an", "the", "and", "or", "but", "in", "on", "at", "to", "for",
    "of", "with", "by", "from", "up", "is", "are", "was", "were", "be",
    "been", "has", "have", "had", "do", "does", "did", "will", "would",
    "could", "should", "may", "might", "as", "that", "this", "it", "its",
    "after", "during", "over", "into", "about", "than", "more", "not",
    "no", "new", "says", "said", "amid", "following",
})


def _tokens(text: str) -> frozenset[str]:
    words = re.findall(r"[a-z]+", text.lower())
    return frozenset(w for w in words if w not in _STOP_WORDS and len(w) > 2)


def _jaccard(a: frozenset[str], b: frozenset[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def _haversine_miles(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    R = 3958.8
    lat1, lat2 = math.radians(lat1), math.radians(lat2)
    dlat = lat2 - lat1
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))


# ---------------------------------------------------------------------------
# Wire service family sets — outlets that republish the same wire copy
# ---------------------------------------------------------------------------

# Keys are canonical family names; values are lowercased outlet name substrings.
# A match on ANY substring → same family.
_WIRE_FAMILIES: dict[str, frozenset[str]] = {
    "ap": frozenset({"associated press", "ap news", "apnews", "ap ", "the ap", "/ap/"}),
    "reuters": frozenset({"reuters"}),
    "upi": frozenset({"upi", "united press international"}),
    "afp": frozenset({"agence france", "afp"}),
    "cnn wire": frozenset({"cnn wire", "cnn.com wire"}),
    "nbc news wire": frozenset({"nbc news wire"}),
}

# Canonical domains for wire services — a source URL on one of these domains
# is a reliable wire signal
_WIRE_DOMAINS = frozenset({
    "apnews.com", "reuters.com", "upi.com",
})

# Type compatibility groups — events in the same group may refer to the same incident
_COMPATIBLE_TYPES: dict[str, frozenset[str]] = {
    "protest":                      frozenset({"protest", "police_clash", "crowd_disruption",
                                               "protest_related_road_shutdown", "unrest"}),
    "police_clash":                 frozenset({"police_clash", "protest", "riot", "unrest"}),
    "riot":                         frozenset({"riot", "vandalism_tied_to_unrest", "police_clash",
                                               "crowd_disruption", "unrest"}),
    "vandalism_tied_to_unrest":     frozenset({"vandalism_tied_to_unrest", "riot", "unrest"}),
    "crowd_disruption":             frozenset({"crowd_disruption", "protest", "riot", "unrest"}),
    "protest_related_road_shutdown": frozenset({"protest_related_road_shutdown", "protest", "unrest"}),
    "political_violence":           frozenset({"political_violence", "violence"}),
    "unrest":                       frozenset({"unrest", "protest", "riot", "crowd_disruption",
                                               "vandalism_tied_to_unrest", "police_clash"}),
    "violence":                     frozenset({"violence", "political_violence", "riot"}),
    "disruption":                   frozenset({"disruption", "crowd_disruption", "unrest"}),
    "other":                        frozenset({"other"}),
}


def _types_compatible(t1: str, t2: str) -> bool:
    """Return True if two event types can plausibly refer to the same incident."""
    compat = _COMPATIBLE_TYPES.get(t1, frozenset({t1}))
    return t2 in compat


def _outlet_family(outlet: str) -> str | None:
    """Return the wire family key if the outlet belongs to one, else None."""
    lower = outlet.lower()
    for family, substrings in _WIRE_FAMILIES.items():
        for sub in substrings:
            if sub in lower:
                return family
    return None


def _url_domain(url: str | None) -> str | None:
    if not url:
        return None
    try:
        return urlparse(url).netloc.lower().removeprefix("www.")
    except Exception:
        return None


# ---------------------------------------------------------------------------
# 1. Exact source_id dedup
# ---------------------------------------------------------------------------

def is_duplicate(source_id: str, db: Session) -> bool:
    """Return True if an event with this source_id already exists in the database."""
    if not source_id:
        return False
    return db.query(Event).filter(Event.source_id == source_id).first() is not None


# ---------------------------------------------------------------------------
# 2. Cross-source similarity matching
# ---------------------------------------------------------------------------

def find_matching_event(
    title: str,
    lat: float,
    lon: float,
    occurred_at: datetime,
    event_type: str,
    db: Session,
    time_window_hours: int = 48,
    distance_miles: float = 50.0,
    title_similarity_threshold: float = 0.4,
) -> Event | None:
    """
    Find an existing active Event that likely describes the same real-world incident.

    Matching criteria (all must pass):
      - Location within distance_miles of the candidate event
      - occurred_at within time_window_hours of the candidate event
      - Title Jaccard similarity above title_similarity_threshold (adjusted by type compatibility)
      - Compatible event type (or high enough title similarity to overcome type mismatch)

    Returns the best-scoring match, or None if no match is found.
    """
    window_start = occurred_at - timedelta(hours=time_window_hours)
    window_end   = occurred_at + timedelta(hours=time_window_hours)

    candidates = (
        db.query(Event)
        .filter(
            Event.is_active == True,
            Event.occurred_at >= window_start,
            Event.occurred_at <= window_end,
        )
        .all()
    )

    title_tok = _tokens(title)
    best_event: Event | None = None
    best_score = 0.0

    for candidate in candidates:
        # Distance gate
        try:
            dist = _haversine_miles(lat, lon, candidate.latitude, candidate.longitude)
        except Exception:
            continue
        if dist > distance_miles:
            continue

        # Title similarity
        cand_tok = _tokens(candidate.title)
        sim = _jaccard(title_tok, cand_tok)

        # Effective threshold: lower for compatible types, higher for incompatible
        compatible = _types_compatible(event_type, candidate.event_type or "")
        effective_threshold = title_similarity_threshold if compatible else title_similarity_threshold + 0.2

        if sim < effective_threshold:
            continue

        # Composite score: title similarity + recency bonus + proximity bonus
        time_diff_h = abs((occurred_at - candidate.occurred_at).total_seconds()) / 3600
        recency = max(0.0, 1.0 - time_diff_h / time_window_hours)
        proximity = max(0.0, 1.0 - dist / distance_miles)
        score = 0.5 * sim + 0.3 * recency + 0.2 * proximity

        if score > best_score:
            best_score = score
            best_event = candidate

    return best_event


# ---------------------------------------------------------------------------
# 3. Syndicated copy detection
# ---------------------------------------------------------------------------

def is_syndicated_copy(
    outlet_name: str | None,
    article_url: str | None,
    article_title: str | None,
    article_published_at: datetime | None,
    article_er_event_uri: str | None,
    existing_sources: list[EventSource],
) -> bool:
    """
    Return True if this article is a syndicated/near-duplicate copy of an already-recorded source.

    Detection rules (any single rule → syndicated):
      1. Same outlet name (exact, case-insensitive)
      2. Same wire service family (AP, Reuters, UPI, AFP …)
      3. Title Jaccard similarity > 0.85 against any existing source's title
      4. Same canonical URL domain (e.g., apnews.com) — both articles come from same wire domain
      5. Publish timestamp within 30 min of an existing source AND title similarity > 0.70
      6. Same ER eventUri AND same outlet wire family (strong signal of grouped wire copies)

    A syndicated copy is stored with source_trust_weight=0.0 — it does not count
    as independent corroboration and does not uplift the event's confidence.
    """
    if not existing_sources:
        return False

    outlet_lower = (outlet_name or "").lower()
    new_domain = _url_domain(article_url)
    new_title_tok = _tokens(article_title or "")
    new_family = _outlet_family(outlet_lower) if outlet_lower else None

    for src in existing_sources:
        # Rule 1: exact outlet match
        if outlet_lower and outlet_lower == (src.source_name or "").lower():
            return True

        # Rule 2: same wire family
        existing_family = _outlet_family((src.source_name or "").lower())
        if new_family and existing_family and new_family == existing_family:
            return True

        # Rule 3: high title similarity
        if article_title and src.source_title:
            sim = _jaccard(new_title_tok, _tokens(src.source_title))
            if sim > 0.85:
                return True

        # Rule 4: same canonical URL domain (wire service domain)
        existing_domain = _url_domain(src.source_url)
        if new_domain and existing_domain:
            if new_domain == existing_domain and new_domain in _WIRE_DOMAINS:
                return True

        # Rule 5: timestamp proximity + moderate title similarity
        if article_published_at and src.source_published_at:
            minutes_diff = abs(
                (article_published_at - src.source_published_at).total_seconds()
            ) / 60
            if minutes_diff <= 30 and article_title and src.source_title:
                sim = _jaccard(new_title_tok, _tokens(src.source_title))
                if sim > 0.70:
                    return True

        # Rule 6: same ER eventUri + same outlet family
        if article_er_event_uri:
            try:
                meta = __import__("json").loads(src.metadata_json or "{}")
                existing_event_uri = meta.get("er_event_uri")
            except Exception:
                existing_event_uri = None
            if (
                existing_event_uri
                and existing_event_uri == article_er_event_uri
                and new_family
                and existing_family
                and new_family == existing_family
            ):
                return True

    return False
