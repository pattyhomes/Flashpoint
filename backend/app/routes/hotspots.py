from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from fastapi import Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Event, EventSource, Hotspot
from app.schemas import HotspotBriefingOut, HotspotDetailOut, HotspotOut, HotspotTrendListOut, HotspotTrendOut
from app.services.event_display import serialize_event
from app.services.hotspot_briefing import build_hotspot_briefing

router = APIRouter(prefix="/hotspots", tags=["hotspots"])


@router.get("/", response_model=list[HotspotOut])
def list_hotspots(db: Session = Depends(get_db)):
    return db.query(Hotspot).order_by(Hotspot.priority_score.desc()).all()


def _hour_floor(value: datetime) -> datetime:
    return value.replace(minute=0, second=0, microsecond=0)


def _trend_payload(hotspot_id: int, hours: int, now: datetime, db: Session) -> dict:
    end_bucket = _hour_floor(now)
    start_bucket = end_bucket - timedelta(hours=hours - 1)
    end_exclusive = end_bucket + timedelta(hours=1)
    events = (
        db.query(Event)
        .filter(
            Event.cluster_id == hotspot_id,
            Event.is_active == True,
            Event.occurred_at >= start_bucket,
            Event.occurred_at < end_exclusive,
        )
        .all()
    )

    bucketed: dict[datetime, list[Event]] = {
        start_bucket + timedelta(hours=i): []
        for i in range(hours)
    }
    for event in events:
        bucket = _hour_floor(event.occurred_at)
        if bucket in bucketed:
            bucketed[bucket].append(event)

    buckets = []
    for bucket_start, bucket_events in bucketed.items():
        count = len(bucket_events)
        severity_sum = sum((event.severity_score or 0.0) for event in bucket_events)
        buckets.append({
            "bucket_start": bucket_start,
            "event_count": count,
            "max_severity": round(max((event.severity_score or 0.0) for event in bucket_events), 3) if bucket_events else 0.0,
            "avg_severity": round(severity_sum / count, 3) if count else 0.0,
        })

    return {"hotspot_id": hotspot_id, "hours": hours, "buckets": buckets}


@router.get("/trends", response_model=HotspotTrendListOut)
def hotspot_trends(
    ids: str = Query(..., min_length=1),
    hours: int = Query(24, ge=1, le=72),
    now: datetime | None = Query(None),
    db: Session = Depends(get_db),
):
    hotspot_ids: list[int] = []
    for raw_id in ids.split(","):
        raw_id = raw_id.strip()
        if not raw_id:
            continue
        try:
            hotspot_id = int(raw_id)
        except ValueError:
            raise HTTPException(status_code=400, detail="ids must be comma-separated integers") from None
        if hotspot_id not in hotspot_ids:
            hotspot_ids.append(hotspot_id)
    if not hotspot_ids:
        raise HTTPException(status_code=400, detail="ids must include at least one hotspot id")
    if len(hotspot_ids) > 30:
        raise HTTPException(status_code=400, detail="ids may include at most 30 hotspot ids")

    existing_ids = {
        row[0]
        for row in db.query(Hotspot.id).filter(Hotspot.id.in_(hotspot_ids)).all()
    }
    trend_now = now or datetime.utcnow()
    return {
        "trends": [
            _trend_payload(hotspot_id, hours, trend_now, db)
            for hotspot_id in hotspot_ids
            if hotspot_id in existing_ids
        ],
    }


@router.get("/{hotspot_id}/trend", response_model=HotspotTrendOut)
def hotspot_trend(
    hotspot_id: int,
    hours: int = Query(24, ge=1, le=72),
    now: datetime | None = Query(None),
    db: Session = Depends(get_db),
):
    hotspot = db.query(Hotspot).filter(Hotspot.id == hotspot_id).first()
    if not hotspot:
        raise HTTPException(status_code=404, detail="Hotspot not found")

    return _trend_payload(hotspot_id, hours, now or datetime.utcnow(), db)


@router.get("/{hotspot_id}/briefing", response_model=HotspotBriefingOut)
def hotspot_briefing(hotspot_id: int, db: Session = Depends(get_db)):
    hotspot = db.query(Hotspot).filter(Hotspot.id == hotspot_id).first()
    if not hotspot:
        raise HTTPException(status_code=404, detail="Hotspot not found")
    return build_hotspot_briefing(db, hotspot)


@router.get("/{hotspot_id}", response_model=HotspotDetailOut)
def get_hotspot(hotspot_id: int, db: Session = Depends(get_db)):
    hotspot = db.query(Hotspot).filter(Hotspot.id == hotspot_id).first()
    if not hotspot:
        raise HTTPException(status_code=404, detail="Hotspot not found")
    events = (
        db.query(Event)
        .filter(Event.cluster_id == hotspot_id, Event.is_active == True)
        .order_by(Event.severity_score.desc())
        .all()
    )
    event_ids = [event.id for event in events]
    sources_by_event: dict[int, list[EventSource]] = {event_id: [] for event_id in event_ids}
    if event_ids:
        sources = db.query(EventSource).filter(EventSource.event_id.in_(event_ids)).all()
        for source in sources:
            sources_by_event.setdefault(source.event_id, []).append(source)
    # Build response from validated Pydantic objects — avoids SQLAlchemy internal state
    base = HotspotOut.model_validate(hotspot).model_dump()
    return {**base, "member_events": [serialize_event(event, sources_by_event.get(event.id, [])) for event in events]}
