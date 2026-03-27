from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Event, EventSource
from app.schemas import EventDetailOut, EventOut, EventPage

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
    return {
        "items": items,
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
    base = EventOut.model_validate(event).model_dump()
    return {**base, "sources": sources}
