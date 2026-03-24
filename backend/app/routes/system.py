from datetime import datetime

from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.models import Event, Hotspot, IngestRun
from app.schemas import SystemStatusResponse

router = APIRouter(prefix="/system", tags=["system"])


@router.get("/status", response_model=SystemStatusResponse)
def system_status(db: Session = Depends(get_db)):
    last_ingested = db.query(func.max(Event.ingested_at)).scalar()
    last_computed = db.query(func.max(Hotspot.last_computed_at)).scalar()
    event_count   = db.query(func.count(Event.id)).filter(Event.is_active == True).scalar() or 0
    hotspot_count = db.query(func.count(Hotspot.id)).scalar() or 0

    # Most recent run of any status
    last_run = (
        db.query(IngestRun)
        .order_by(IngestRun.started_at.desc())
        .first()
    )

    # Most recent successful run — use finished_at as the authoritative success timestamp
    last_success = (
        db.query(IngestRun)
        .filter(IngestRun.status == "success")
        .order_by(IngestRun.started_at.desc())
        .first()
    )

    last_success_at = last_success.finished_at if last_success else None

    # is_stale: based on run-path freshness (last_success_at), not compute freshness
    stale_threshold = settings.ingestion_interval_seconds * 2
    is_stale = (
        last_success_at is None
        or (datetime.utcnow() - last_success_at).total_seconds() > stale_threshold
    )

    # last_error: only expose if the most recent run failed
    last_error = last_run.error_message if last_run and last_run.status == "failed" else None

    return SystemStatusResponse(
        last_ingested_at=last_ingested,
        last_computed_at=last_computed,
        event_count=event_count,
        hotspot_count=hotspot_count,
        is_stale=is_stale,
        last_run_at=last_run.started_at if last_run else None,
        last_success_at=last_success_at,
        last_run_status=last_run.status if last_run else None,
        last_error=last_error,
        generated_at=datetime.utcnow(),
        db_path=settings.database_url,
    )
