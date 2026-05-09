from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Event, EventSource
from app.schemas import EventDetailOut, EventPage
from app.services.event_display import serialize_event

router = APIRouter(prefix="/events", tags=["events"])


@router.get("/", response_model=EventPage)
def list_events(
    limit: int = Query(500, le=1000),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    base = db.query(Event).filter(Event.is_active == True)
    total = base.count()
    items = base.order_by(Event.occurred_at.desc()).offset(offset).limit(limit).all()
    event_ids = [event.id for event in items]
    sources_by_event: dict[int, list[EventSource]] = {event_id: [] for event_id in event_ids}
    if event_ids:
        sources = db.query(EventSource).filter(EventSource.event_id.in_(event_ids)).all()
        for source in sources:
            sources_by_event.setdefault(source.event_id, []).append(source)
    return {
        "items": [serialize_event(event, sources_by_event.get(event.id, [])) for event in items],
        "total": total,
        "limit": limit,
        "offset": offset,
        "has_more": (offset + len(items)) < total,
    }


@router.get("/{event_id}", response_model=EventDetailOut)
def get_event(event_id: int, db: Session = Depends(get_db)):
    event = db.query(Event).filter(Event.id == event_id).first()
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    sources = (
        db.query(EventSource)
        .filter(EventSource.event_id == event_id)
        .order_by(EventSource.source_published_at.desc())
        .all()
    )
    base = serialize_event(event, sources)
    return {**base, "sources": sources}
