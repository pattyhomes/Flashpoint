"""
Event Registry ingestion source.

Fetches recent English-language articles from the Event Registry API
(https://eventregistry.org) focused on U.S. unrest-related events.

Returns a list of (EventCreate, raw_article_dict) pairs. The raw article dict
is preserved so the caller can create EventSource provenance records.

Key behaviors:
  - Uses title + body + categories + concepts for deterministic classification
  - Filters by location precision (venue / city / state; country-level discarded)
  - Initial confidence is conservative (0.30–0.62 range)
  - Severity is type-based, not article-volume-based
  - Fetch failures are logged but do not raise (graceful degradation)
"""

import json
from datetime import datetime, timedelta

import httpx

from app.config import settings
from app.schemas import EventCreate
from app.services.ingestion.classifier import classify

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_ER_ARTICLE_ENDPOINT = "https://eventregistry.org/api/v1/article/getArticles"
_ER_US_LOCATION_URI  = "http://en.wikipedia.org/wiki/United_States"

# Precision ranking (lower index = more precise)
_PRECISION_ORDER = ["venue", "city", "state", "country"]

# Type-based severity — conservative, not article-volume-based
_TYPE_SEVERITY: dict[str, float] = {
    "political_violence":           0.85,
    "riot":                         0.75,
    "police_clash":                 0.70,
    "vandalism_tied_to_unrest":     0.55,
    "crowd_disruption":             0.50,
    "protest_related_road_shutdown": 0.45,
    "protest":                      0.40,
    "unrest":                       0.50,
}

# US state name → abbreviation (for location parsing)
_STATE_NAME_TO_ABBREV: dict[str, str] = {
    "Alabama": "AL", "Alaska": "AK", "Arizona": "AZ", "Arkansas": "AR",
    "California": "CA", "Colorado": "CO", "Connecticut": "CT", "Delaware": "DE",
    "Florida": "FL", "Georgia": "GA", "Hawaii": "HI", "Idaho": "ID",
    "Illinois": "IL", "Indiana": "IN", "Iowa": "IA", "Kansas": "KS",
    "Kentucky": "KY", "Louisiana": "LA", "Maine": "ME", "Maryland": "MD",
    "Massachusetts": "MA", "Michigan": "MI", "Minnesota": "MN", "Mississippi": "MS",
    "Missouri": "MO", "Montana": "MT", "Nebraska": "NE", "Nevada": "NV",
    "New Hampshire": "NH", "New Jersey": "NJ", "New Mexico": "NM", "New York": "NY",
    "North Carolina": "NC", "North Dakota": "ND", "Ohio": "OH", "Oklahoma": "OK",
    "Oregon": "OR", "Pennsylvania": "PA", "Rhode Island": "RI", "South Carolina": "SC",
    "South Dakota": "SD", "Tennessee": "TN", "Texas": "TX", "Utah": "UT",
    "Vermont": "VT", "Virginia": "VA", "Washington": "WA", "West Virginia": "WV",
    "Wisconsin": "WI", "Wyoming": "WY", "District of Columbia": "DC",
}


# ---------------------------------------------------------------------------
# Location extraction
# ---------------------------------------------------------------------------

def _extract_location(
    article: dict,
) -> tuple[float, float, str | None, str | None, str] | None:
    """
    Extract (lat, lon, city, state, precision) from an ER article's location data.

    Returns None if no usable location is found or precision is country-level.
    """
    loc = article.get("location")
    if not loc:
        return None

    lat = loc.get("lat")
    lon = loc.get("long")
    if lat is None or lon is None:
        return None

    try:
        lat = float(lat)
        lon = float(lon)
    except (TypeError, ValueError):
        return None

    # Reject null-island
    if lat == 0.0 and lon == 0.0:
        return None

    # ER location type hierarchy
    loc_type_obj = loc.get("type", {})
    loc_type = ""
    if isinstance(loc_type_obj, dict):
        loc_type = loc_type_obj.get("type", "")
    elif isinstance(loc_type_obj, str):
        loc_type = loc_type_obj

    if loc_type == "place":
        precision = "venue"
    elif loc_type == "city":
        precision = "city"
    elif loc_type in ("admin", "admin1", "admin2"):
        precision = "state"
    elif loc_type == "country":
        return None  # country-level — always discard
    else:
        precision = "city"  # conservative default

    # Extract label (e.g. "Portland, Oregon, United States")
    label_obj = loc.get("label", {})
    if isinstance(label_obj, dict):
        label = label_obj.get("eng", "") or ""
    else:
        label = str(label_obj or "")

    parts = [p.strip() for p in label.split(",")]
    city: str | None = None
    state: str | None = None

    if parts:
        # Last part is often "United States" — discard
        if len(parts) > 1 and "united states" in parts[-1].lower():
            parts = parts[:-1]

        if precision in ("venue", "city"):
            city = parts[0] if parts else None
            # Second-to-last part is often a state name
            if len(parts) >= 2:
                candidate_state = parts[-1]
                state = _STATE_NAME_TO_ABBREV.get(candidate_state) or (
                    candidate_state if len(candidate_state) == 2 else None
                )
        elif precision == "state":
            # State-level: treat the label as the state
            candidate_state = parts[0]
            state = _STATE_NAME_TO_ABBREV.get(candidate_state) or (
                candidate_state if len(candidate_state) == 2 else None
            )
            city = None  # no city-level precision

    return lat, lon, city, state, precision


# ---------------------------------------------------------------------------
# Confidence scoring
# ---------------------------------------------------------------------------

def _initial_confidence(classification_score: float, precision: str) -> float:
    """
    Compute initial confidence for a new ER event (before any corroboration).

    Conservative baseline. Precision bonus rewards better location data.
    """
    base = 0.30 + 0.20 * classification_score   # 0.30–0.50 range
    precision_bonus = {"venue": 0.12, "city": 0.08, "state": 0.0}
    confidence = base + precision_bonus.get(precision, 0.0)
    return round(max(0.15, min(1.0, confidence)), 3)


def _apply_uncorroborated_cap(confidence: float, precision: str, max_cap: float) -> float:
    """
    Apply tiered uncorroborated confidence cap.

    Caps:
      venue:  min(computed, 0.62)  — strong article-backed evidence
      city:   min(computed, 0.58)  — standard city-level
      state:  min(computed, 0.45)  — weak geographic context

    max_cap is used as a lower bound on the tier caps (operator can tighten further).
    """
    tier_cap = {"venue": 0.62, "city": 0.58, "state": 0.45}.get(precision, 0.45)
    effective_cap = min(tier_cap, max_cap)
    return round(min(confidence, effective_cap), 3)


# ---------------------------------------------------------------------------
# Precision gating
# ---------------------------------------------------------------------------

_PRECISION_RANK = {p: i for i, p in enumerate(_PRECISION_ORDER)}


def _precision_passes(precision: str, min_precision: str) -> bool:
    """Return True if precision is at least as precise as min_precision."""
    return _PRECISION_RANK.get(precision, 99) <= _PRECISION_RANK.get(min_precision, 99)


# ---------------------------------------------------------------------------
# API request builder
# ---------------------------------------------------------------------------

def _build_request(lookback_hours: int, page: int, count: int) -> dict:
    now = datetime.utcnow()
    date_start = (now - timedelta(hours=lookback_hours)).strftime("%Y-%m-%d")
    date_end = now.strftime("%Y-%m-%d")

    return {
        "apiKey": settings.event_registry_api_key,
        "action": "getArticles",
        "keyword": (
            "protest OR riot OR unrest OR \"police clash\" OR \"political violence\" "
            "OR vandalism OR \"crowd disruption\" OR demonstration OR \"tear gas\" "
            "OR looting OR \"march against\" OR \"rally against\""
        ),
        "keywordsLoc": "title,body",
        "locationUri": _ER_US_LOCATION_URI,
        "lang": "eng",
        "dateStart": date_start,
        "dateEnd": date_end,
        "articlesCount": count,
        "articlesPage": page,
        "articlesSortBy": "date",
        "articlesSortByAsc": False,
        "includeArticleLocation": True,
        "includeArticleConcepts": True,
        "includeArticleCategories": True,
        "includeArticleBody": True,
        "resultType": "articles",
    }


# ---------------------------------------------------------------------------
# Normalization
# ---------------------------------------------------------------------------

def _normalize_article(
    article: dict,
) -> tuple[EventCreate, dict] | None:
    """
    Classify and normalize one ER article.

    Returns (EventCreate, raw_article) or None if the article should be discarded.
    """
    title = (article.get("title") or "").strip()
    body  = (article.get("body") or "").strip()
    if not title:
        return None

    categories = article.get("categories") or []
    concepts   = article.get("concepts") or []

    # Classify
    result = classify(
        title=title,
        body=body,
        categories=categories,
        concepts=concepts,
        min_score=settings.event_registry_min_classification_score,
    )
    if result is None:
        return None

    # Extract location
    loc = _extract_location(article)
    if loc is None:
        return None
    lat, lon, city, state, precision = loc

    # Precision gate
    if not _precision_passes(precision, settings.event_registry_min_location_precision):
        return None

    # Timestamps
    date_str = article.get("dateTimePub") or article.get("date") or ""
    try:
        if "T" in date_str:
            occurred_at = datetime.fromisoformat(date_str.replace("Z", "+00:00")).replace(tzinfo=None)
        else:
            occurred_at = datetime.strptime(date_str[:10], "%Y-%m-%d").replace(hour=12)
    except (ValueError, TypeError):
        occurred_at = datetime.utcnow()

    # Source info
    source_obj = article.get("source") or {}
    outlet_name = (source_obj.get("title") or "").strip() or None
    source_url  = (article.get("url") or "").strip() or None

    # Scores
    confidence = _initial_confidence(result.score, precision)
    severity   = _TYPE_SEVERITY.get(result.event_type, 0.50)

    # Summary (first 500 chars of body, not the title)
    summary = body[:500].strip() or None

    er_uri = (article.get("uri") or "").strip()

    event = EventCreate(
        source_id=f"er-{er_uri}" if er_uri else None,
        title=title,
        summary=summary,
        event_type=result.event_type,
        latitude=lat,
        longitude=lon,
        city=city,
        state=state,
        country="US",
        occurred_at=occurred_at,
        source_name="eventregistry",
        source_url=source_url,
        source_count=1,
        confidence_score=confidence,
        severity_score=severity,
        location_precision=precision,
        raw_payload_json=json.dumps({
            "er_uri": er_uri,
            "er_event_uri": article.get("eventUri"),
            "classification_score": round(result.score, 3),
            "source_outlet": outlet_name or "",
            "categories": [c.get("label") for c in categories[:5]],
            "precision": precision,
        }),
    )

    return event, article


# ---------------------------------------------------------------------------
# Public interface
# ---------------------------------------------------------------------------

class EventRegistrySource:
    source_name = "eventregistry"

    def fetch(self) -> list[tuple[EventCreate, dict]]:
        """
        Fetch and classify articles from Event Registry.

        Returns a list of (EventCreate, raw_article) pairs. The raw_article
        dict is passed back to the caller so it can build EventSource records.

        Fetch or parse errors are logged and skipped — they do not abort the run.
        """
        max_records = settings.event_registry_max_records
        lookback    = settings.event_registry_lookback_hours
        page_size   = min(100, max_records)

        results: list[tuple[EventCreate, dict]] = []
        page = 1
        total_fetched = 0

        while total_fetched < max_records:
            fetch_count = min(page_size, max_records - total_fetched)
            payload = _build_request(lookback, page, fetch_count)

            try:
                resp = httpx.post(
                    _ER_ARTICLE_ENDPOINT,
                    json=payload,
                    timeout=30,
                )
                resp.raise_for_status()
                data = resp.json()
            except Exception as e:
                print(f"[eventregistry] Fetch error (page {page}): {e}")
                break

            articles_block = data.get("articles", {})
            articles = articles_block.get("results", [])
            total_results = articles_block.get("totalResults", 0)

            if not articles:
                break

            for article in articles:
                try:
                    normalized = _normalize_article(article)
                    if normalized is not None:
                        results.append(normalized)
                except Exception as e:
                    print(f"[eventregistry] Normalization error for '{article.get('uri', '?')}': {e}")

            total_fetched += len(articles)
            page += 1

            # Stop if we've exhausted all available results
            if total_fetched >= total_results:
                break

        print(
            f"[eventregistry] Fetched {total_fetched} articles, "
            f"{len(results)} passed classification/location filters."
        )
        return results
