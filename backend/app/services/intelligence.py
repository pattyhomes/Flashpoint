import hashlib
import json
import math
import re
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from app.models import Event, EventSource, EvidenceItem, Observation
from app.services.ingestion.deduper import find_matching_event
from app.services.ai_embeddings import embed_text
from app.utils.time import utcnow_naive as utcnow

SIGNAL_CONFIDENCE_MIN = 0.45
SIGNAL_PRECISIONS = {"venue", "city"}
SIGNAL_EVENT_TYPES = {
    "protest",
    "unrest",
    "riot",
    "police_clash",
    "crowd_disruption",
    "protest_related_road_shutdown",
    "vandalism_tied_to_unrest",
    "political_violence",
    "violence",
    "disruption",
}
_SOCIAL_SOURCE_TYPES = {"bluesky", "mastodon"}
_NEWS_SOURCE_TYPES = {"eventregistry"}
_GDELT_SOURCE_TYPES = {"gdelt"}
_OFFICIAL_SOURCE_TYPES = {"official"}
_ACLED_SOURCE_TYPES = {"acled"}
_CONTEXT_SOURCE_TYPES = {"nws", "weather"}
_FAMILY_PROMOTION_RANK = {
    "acled": 5,
    "official": 4,
    "news": 3,
    "gdelt": 2,
    "social": 1,
}
_STOP_WORDS = frozenset({
    "a", "an", "the", "and", "or", "but", "in", "on", "at", "to", "for",
    "of", "with", "by", "from", "up", "is", "are", "was", "were", "be",
    "been", "has", "have", "had", "do", "does", "did", "will", "would",
    "could", "should", "may", "might", "as", "that", "this", "it", "its",
    "after", "during", "over", "into", "about", "than", "more", "not",
    "no", "new", "says", "said", "amid", "following", "reported",
})


def _json_dumps(value: dict | list | None) -> str | None:
    if value is None:
        return None
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def _hash_evidence(
    *,
    source_type: str,
    source_record_id: str | None,
    source_url: str | None,
    source_title: str | None,
    excerpt: str | None,
    raw_payload_json: str | None,
) -> str:
    material = "|".join(
        [
            source_type or "",
            source_record_id or "",
            source_url or "",
            source_title or "",
            excerpt or "",
            raw_payload_json or "",
        ]
    )
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def record_evidence(
    db: Session,
    *,
    source_type: str,
    source_record_id: str | None = None,
    source_url: str | None = None,
    source_name: str | None = None,
    source_title: str | None = None,
    excerpt: str | None = None,
    published_at: datetime | None = None,
    trust_tier: str = "weak",
    raw_payload: dict | list | None = None,
    raw_payload_json: str | None = None,
) -> EvidenceItem:
    """Persist source evidence once and return the existing row on duplicates."""
    payload_json = raw_payload_json if raw_payload_json is not None else _json_dumps(raw_payload)
    content_hash = _hash_evidence(
        source_type=source_type,
        source_record_id=source_record_id,
        source_url=source_url,
        source_title=source_title,
        excerpt=excerpt,
        raw_payload_json=payload_json,
    )

    query = db.query(EvidenceItem).filter(EvidenceItem.source_type == source_type)
    existing = None
    if source_record_id:
        existing = query.filter(EvidenceItem.source_record_id == source_record_id).first()
    if existing is None:
        existing = query.filter(EvidenceItem.content_hash == content_hash).first()
    if existing is not None:
        return existing

    item = EvidenceItem(
        source_type=source_type,
        source_record_id=source_record_id,
        source_url=source_url,
        source_name=source_name,
        source_title=source_title,
        excerpt=excerpt,
        published_at=published_at,
        content_hash=content_hash,
        trust_tier=trust_tier,
        embedding_json=embed_text(" ".join(part for part in [source_title, excerpt] if part)),
        raw_payload_json=payload_json,
    )
    db.add(item)
    db.flush()
    return item


def source_family(source_type: str | None, trust_tier: str | None = None) -> str:
    source = (source_type or "").lower()
    trust = (trust_tier or "").lower()
    if trust == "context" or source in _CONTEXT_SOURCE_TYPES:
        return "context"
    if source in _ACLED_SOURCE_TYPES or trust == "acled":
        return "acled"
    if source in _OFFICIAL_SOURCE_TYPES or trust == "official":
        return "official"
    if source in _SOCIAL_SOURCE_TYPES:
        return "social"
    if source in _GDELT_SOURCE_TYPES:
        return "gdelt"
    if source in _NEWS_SOURCE_TYPES or trust == "news":
        return "news"
    if trust == "weak":
        return "social"
    return source or "unknown"


def _observation_ready_for_event(observation: Observation) -> bool:
    return bool(
        observation.latitude is not None
        and observation.longitude is not None
        and observation.observed_at is not None
        and observation.candidate_event_type
        and observation.location_precision in SIGNAL_PRECISIONS
    )


def _signal_weight(observation: Observation, family: str) -> float:
    family_weight = {
        "acled": 1.0,
        "official": 0.95,
        "news": 0.78,
        "gdelt": 0.62,
        "social": 0.45,
    }.get(family, 0.35)
    confidence = max(0.0, min(1.0, observation.confidence_score or 0.0))
    severity = max(0.0, min(1.0, observation.severity_score or 0.0))
    return round(max(0.05, family_weight * (0.65 * confidence + 0.35 * max(severity, 0.25))), 3)


def is_map_signal_eligible(observation: Observation, evidence: EvidenceItem | None) -> bool:
    if observation.status != "lead":
        return False
    if observation.linked_event_id is not None or observation.promoted_event_id is not None:
        return False
    if observation.confidence_score < SIGNAL_CONFIDENCE_MIN:
        return False
    if observation.candidate_event_type not in SIGNAL_EVENT_TYPES:
        return False
    if not _observation_ready_for_event(observation):
        return False
    family = source_family(evidence.source_type if evidence else None, evidence.trust_tier if evidence else None)
    return family not in {"context", "unknown"}


def observation_map_signal(db: Session, observation: Observation) -> dict | None:
    evidence = db.get(EvidenceItem, observation.evidence_id)
    if not is_map_signal_eligible(observation, evidence):
        return None
    family = source_family(evidence.source_type, evidence.trust_tier)
    return {
        "observation": observation,
        "evidence": evidence,
        "source_family": family,
        "signal_weight": _signal_weight(observation, family),
    }


def eligible_map_signals(db: Session, limit: int = 500) -> list[dict]:
    observations = (
        db.query(Observation)
        .filter(
            Observation.status == "lead",
            Observation.linked_event_id.is_(None),
            Observation.promoted_event_id.is_(None),
            Observation.confidence_score >= SIGNAL_CONFIDENCE_MIN,
            Observation.latitude.isnot(None),
            Observation.longitude.isnot(None),
            Observation.location_precision.in_(SIGNAL_PRECISIONS),
            Observation.candidate_event_type.in_(SIGNAL_EVENT_TYPES),
        )
        .order_by(Observation.observed_at.desc().nullslast(), Observation.created_at.desc())
        .all()
    )
    signals = []
    for observation in observations:
        signal = observation_map_signal(db, observation)
        if signal:
            signals.append(signal)
        if len(signals) >= limit:
            break
    return signals


def record_observation(
    db: Session,
    *,
    evidence: EvidenceItem,
    status: str = "lead",
    title: str,
    summary: str | None = None,
    candidate_event_type: str | None = None,
    latitude: float | None = None,
    longitude: float | None = None,
    city: str | None = None,
    state: str | None = None,
    country: str = "US",
    observed_at: datetime | None = None,
    confidence_score: float = 0.0,
    severity_score: float = 0.0,
    location_precision: str | None = None,
) -> Observation:
    existing = (
        db.query(Observation)
        .filter(Observation.evidence_id == evidence.id)
        .first()
    )
    if existing is not None:
        return existing

    observation = Observation(
        evidence_id=evidence.id,
        status=status,
        candidate_event_type=candidate_event_type,
        title=title,
        summary=summary,
        city=city,
        state=state,
        country=country,
        latitude=latitude,
        longitude=longitude,
        location_precision=location_precision,
        observed_at=observed_at,
        confidence_score=confidence_score,
        severity_score=severity_score,
        updated_at=utcnow(),
    )
    db.add(observation)
    db.flush()
    return observation


def _require_observation(db: Session, observation_id: int) -> Observation:
    observation = db.get(Observation, observation_id)
    if observation is None:
        raise ValueError("Observation not found")
    return observation


def _require_event(db: Session, event_id: int) -> Event:
    event = db.get(Event, event_id)
    if event is None:
        raise ValueError("Event not found")
    return event


def _observation_evidence(db: Session, observation: Observation) -> EvidenceItem:
    evidence = db.get(EvidenceItem, observation.evidence_id)
    if evidence is None:
        raise ValueError("Observation evidence not found")
    return evidence


def _add_event_source_if_missing(
    db: Session,
    *,
    event: Event,
    evidence: EvidenceItem,
    observation: Observation,
) -> bool:
    existing = (
        db.query(EventSource)
        .filter(
            EventSource.event_id == event.id,
            EventSource.source_type == evidence.source_type,
            EventSource.source_record_id == evidence.source_record_id,
        )
        .first()
    )
    if existing is not None:
        return False

    family = source_family(evidence.source_type, evidence.trust_tier)
    trust_weight = 0.0 if family in {"context", "social"} else 1.0
    db.add(
        EventSource(
            event_id=event.id,
            source_type=evidence.source_type,
            source_record_id=evidence.source_record_id,
            source_name=evidence.source_name,
            source_url=evidence.source_url,
            source_title=evidence.source_title or observation.title,
            source_published_at=evidence.published_at or observation.observed_at,
            source_trust_weight=trust_weight,
            location_precision=observation.location_precision,
            metadata_json=evidence.raw_payload_json,
        )
    )
    return trust_weight > 0


def _event_source_families(db: Session, event: Event) -> set[str]:
    families = {source_family(event.source_name, None)}
    rows = (
        db.query(EventSource)
        .filter(EventSource.event_id == event.id, EventSource.source_trust_weight > 0)
        .all()
    )
    for row in rows:
        families.add(source_family(row.source_type, None))
    return {family for family in families if family not in {"context", "unknown"}}


def promote_observation(db: Session, observation_id: int) -> Event:
    observation = _require_observation(db, observation_id)
    if observation.promoted_event_id:
        return _require_event(db, observation.promoted_event_id)
    evidence = _observation_evidence(db, observation)

    if observation.latitude is None or observation.longitude is None:
        raise ValueError("Observation cannot be promoted without coordinates")
    if observation.observed_at is None:
        raise ValueError("Observation cannot be promoted without observed_at")
    if not observation.candidate_event_type:
        raise ValueError("Observation cannot be promoted without candidate_event_type")

    event = Event(
        source_id=f"obs-{observation.id}",
        title=observation.title,
        summary=observation.summary,
        event_type=observation.candidate_event_type,
        city=observation.city,
        state=observation.state,
        country=observation.country,
        latitude=observation.latitude,
        longitude=observation.longitude,
        occurred_at=observation.observed_at,
        source_url=evidence.source_url,
        source_name=evidence.source_type,
        source_count=1,
        confidence_score=observation.confidence_score,
        severity_score=observation.severity_score,
        is_active=True,
        location_precision=observation.location_precision,
        raw_payload_json=evidence.raw_payload_json,
    )
    db.add(event)
    db.flush()

    _add_event_source_if_missing(
        db,
        event=event,
        evidence=evidence,
        observation=observation,
    )
    observation.status = "promoted"
    observation.promoted_event_id = event.id
    observation.linked_event_id = event.id
    observation.updated_at = utcnow()
    db.flush()
    return event


def dismiss_observation(db: Session, observation_id: int) -> Observation:
    observation = _require_observation(db, observation_id)
    observation.status = "dismissed"
    observation.updated_at = utcnow()
    db.flush()
    return observation


def link_observation_to_event(db: Session, observation_id: int, event_id: int) -> Event:
    observation = _require_observation(db, observation_id)
    event = _require_event(db, event_id)
    evidence = _observation_evidence(db, observation)
    family = source_family(evidence.source_type, evidence.trust_tier)
    families_before = _event_source_families(db, event)

    counted = _add_event_source_if_missing(
        db,
        event=event,
        evidence=evidence,
        observation=observation,
    )
    if counted and family not in families_before:
        event.source_count = (event.source_count or 1) + 1
        event.confidence_score = round(min(1.0, (event.confidence_score or 0.0) + 0.08), 3)

    observation.status = "linked"
    observation.linked_event_id = event.id
    observation.updated_at = utcnow()
    db.flush()
    return event


def _tokens(text: str) -> frozenset[str]:
    words = re.findall(r"[a-z]+", text.lower())
    return frozenset(w for w in words if w not in _STOP_WORDS and len(w) > 2)


def _jaccard(a: frozenset[str], b: frozenset[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def _haversine_miles(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    radius = 3958.8
    lat1_r = math.radians(lat1)
    lat2_r = math.radians(lat2)
    dlat = lat2_r - lat1_r
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat / 2) ** 2 + math.cos(lat1_r) * math.cos(lat2_r) * math.sin(dlon / 2) ** 2
    return 2 * radius * math.asin(math.sqrt(a))


def _observations_match(a: Observation, b: Observation) -> bool:
    if not _observation_ready_for_event(a) or not _observation_ready_for_event(b):
        return False
    if a.id == b.id:
        return False
    if a.candidate_event_type != b.candidate_event_type:
        return False
    assert a.latitude is not None and a.longitude is not None
    assert b.latitude is not None and b.longitude is not None
    assert a.observed_at is not None and b.observed_at is not None
    if abs((a.observed_at - b.observed_at).total_seconds()) > 48 * 3600:
        return False
    if _haversine_miles(a.latitude, a.longitude, b.latitude, b.longitude) > 50:
        return False
    return _jaccard(_tokens(a.title), _tokens(b.title)) >= 0.25


def _matching_lead_observations(db: Session, observation: Observation) -> list[Observation]:
    if not _observation_ready_for_event(observation):
        return []
    assert observation.observed_at is not None
    window_start = observation.observed_at - timedelta(hours=48)
    window_end = observation.observed_at + timedelta(hours=48)
    candidates = (
        db.query(Observation)
        .filter(
            Observation.status == "lead",
            Observation.id != observation.id,
            Observation.observed_at >= window_start,
            Observation.observed_at <= window_end,
        )
        .all()
    )
    return [candidate for candidate in candidates if _observations_match(observation, candidate)]


def _automation_family(db: Session, observation: Observation) -> str:
    evidence = _observation_evidence(db, observation)
    return source_family(evidence.source_type, evidence.trust_tier)


def _promotion_candidate(db: Session, observations: list[Observation]) -> Observation:
    def rank(observation: Observation) -> tuple[int, float, float]:
        family = _automation_family(db, observation)
        return (
            _FAMILY_PROMOTION_RANK.get(family, 0),
            observation.confidence_score or 0.0,
            observation.severity_score or 0.0,
        )

    return sorted(observations, key=rank, reverse=True)[0]


def apply_observation_automation(db: Session, observation: Observation) -> Event | None:
    """Safely auto-link or auto-promote a lead when evidence rules allow it.

    The function is intentionally conservative: social/open-web observations can
    become amber map signals, but they cannot create confirmed Events unless an
    independent non-social family corroborates the same place/time/type cluster.
    """
    if observation.promoted_event_id:
        return _require_event(db, observation.promoted_event_id)
    if observation.linked_event_id:
        return _require_event(db, observation.linked_event_id)
    if observation.status != "lead":
        return None
    if not _observation_ready_for_event(observation):
        return None

    evidence = _observation_evidence(db, observation)
    family = source_family(evidence.source_type, evidence.trust_tier)
    if family in {"context", "unknown"}:
        return None

    assert observation.latitude is not None
    assert observation.longitude is not None
    assert observation.observed_at is not None
    assert observation.candidate_event_type is not None

    matched_event = find_matching_event(
        title=observation.title,
        lat=observation.latitude,
        lon=observation.longitude,
        occurred_at=observation.observed_at,
        event_type=observation.candidate_event_type,
        db=db,
    )
    if matched_event is not None:
        return link_observation_to_event(db, observation.id, matched_event.id)

    if family in {"acled", "official"}:
        return promote_observation(db, observation.id)

    matching_observations = _matching_lead_observations(db, observation)
    if not matching_observations:
        return None

    family_by_observation = {
        candidate.id: _automation_family(db, candidate)
        for candidate in [observation, *matching_observations]
    }
    independent_families = set(family_by_observation.values()) - {"context", "unknown"}
    if len(independent_families) < 2 or independent_families <= {"social"}:
        return None

    winner = _promotion_candidate(db, [observation, *matching_observations])
    event = promote_observation(db, winner.id)
    for candidate in matching_observations + [observation]:
        if candidate.id == winner.id:
            continue
        if candidate.status == "lead":
            link_observation_to_event(db, candidate.id, event.id)
    db.flush()
    return event
