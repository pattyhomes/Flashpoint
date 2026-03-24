from datetime import datetime

from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.models import Event, Hotspot
from app.schemas import SystemStatusResponse

router = APIRouter(prefix="/system", tags=["system"])


@router.get("/status", response_model=SystemStatusResponse)
def system_status(db: Session = Depends(get_db)):
    last_ingested = db.query(func.max(Event.ingested_at)).scalar()
    last_computed = db.query(func.max(Hotspot.last_computed_at)).scalar()
    event_count   = db.query(func.count(Event.id)).filter(Event.is_active == True).scalar() or 0
    hotspot_count = db.query(func.count(Hotspot.id)).scalar() or 0

    stale_threshold = settings.ingestion_interval_seconds * 2
    is_stale = (
        last_computed is None
        or (datetime.utcnow() - last_computed).total_seconds() > stale_threshold
    )

    return SystemStatusResponse(
        last_ingested_at=last_ingested,
        last_computed_at=last_computed,
        event_count=event_count,
        hotspot_count=hotspot_count,
        is_stale=is_stale,
        generated_at=datetime.utcnow(),
        db_path=settings.database_url,
    )
