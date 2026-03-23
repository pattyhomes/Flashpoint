from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Event, Hotspot
from app.schemas import HotspotDetailOut, HotspotOut

router = APIRouter(prefix="/hotspots", tags=["hotspots"])


@router.get("/", response_model=list[HotspotOut])
def list_hotspots(db: Session = Depends(get_db)):
    return db.query(Hotspot).order_by(Hotspot.priority_score.desc()).all()


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
