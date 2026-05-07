from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from fastapi import Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Event, Hotspot
from app.schemas import HotspotDetailOut, HotspotOut, HotspotTrendOut

router = APIRouter(prefix="/hotspots", tags=["hotspots"])


@router.get("/", response_model=list[HotspotOut])
def list_hotspots(db: Session = Depends(get_db)):
    return db.query(Hotspot).order_by(Hotspot.priority_score.desc()).all()


def _hour_floor(value: datetime) -> datetime:
    return value.replace(minute=0, second=0, microsecond=0)


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

    end_bucket = _hour_floor(now or datetime.utcnow())
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
    # Build response from validated Pydantic objects — avoids SQLAlchemy internal state
    base = HotspotOut.model_validate(hotspot).model_dump()
    return {**base, "member_events": events}
