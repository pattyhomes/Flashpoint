import hashlib
import json
from datetime import datetime

from sqlalchemy.orm import Session

from app.models import Event, EventSource, EvidenceItem, Observation
from app.services.ai_embeddings import embed_text
from app.utils.time import utcnow_naive as utcnow


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
        .filter(
            Observation.evidence_id == evidence.id,
            Observation.status != "dismissed",
        )
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

    trust_weight = 0.0 if evidence.trust_tier == "context" else 1.0
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

    counted = _add_event_source_if_missing(
        db,
        event=event,
        evidence=evidence,
        observation=observation,
    )
    if counted:
        event.source_count = (event.source_count or 1) + 1
        event.confidence_score = round(min(1.0, (event.confidence_score or 0.0) + 0.08), 3)

    observation.status = "linked"
    observation.linked_event_id = event.id
    observation.updated_at = utcnow()
    db.flush()
    return event
