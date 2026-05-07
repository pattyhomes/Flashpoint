from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.models import Event, Hotspot, IngestRun, Observation
from app.schemas import SystemStatusResponse
from app.services.intelligence import eligible_map_signals
from app.utils.time import to_utc, utcnow, utcnow_naive

router = APIRouter(prefix="/system", tags=["system"])


@router.get("/status", response_model=SystemStatusResponse)
def system_status(db: Session = Depends(get_db)):
    last_ingested = db.query(func.max(Event.ingested_at)).scalar()
    last_computed = db.query(func.max(Hotspot.last_computed_at)).scalar()
    event_count   = db.query(func.count(Event.id)).filter(Event.is_active == True).scalar() or 0
    hotspot_count = db.query(func.count(Hotspot.id)).scalar() or 0
    lead_count = db.query(func.count(Observation.id)).filter(Observation.status == "lead").scalar() or 0
    mapped_signal_count = len(eligible_map_signals(db))
    exception_counts = {
        category: count
        for category, count in (
            db.query(Observation.exception_category, func.count(Observation.id))
            .filter(Observation.exception_category.isnot(None), Observation.status == "lead")
            .group_by(Observation.exception_category)
            .all()
        )
    }
    source_count = (
        db.query(func.count(func.distinct(IngestRun.ingest_source)))
        .filter(IngestRun.ingest_source.isnot(None))
        .scalar()
        or 0
    )
    unhealthy_source_count = _unhealthy_source_count(db)

    # Most recent run of any status — filtered to the configured source
    last_run = (
        db.query(IngestRun)
        .filter(IngestRun.ingest_source == settings.ingest_source)
        .order_by(IngestRun.started_at.desc())
        .first()
    )

    # Most recent successful run — use finished_at as the authoritative success timestamp
    last_success = (
        db.query(IngestRun)
        .filter(
            IngestRun.ingest_source == settings.ingest_source,
            IngestRun.status == "success",
        )
        .order_by(IngestRun.finished_at.desc())
        .first()
    )

    last_success_at = last_success.finished_at if last_success else None

    # is_stale: based on run-path freshness (last_success_at), not compute freshness
    stale_threshold = settings.ingestion_interval_seconds * 2
    is_stale = (
        last_success_at is None
        or (utcnow() - to_utc(last_success_at)).total_seconds() > stale_threshold
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
        lead_count=lead_count,
        exception_count=lead_count,
        mapped_signal_count=mapped_signal_count,
        source_count=source_count,
        unhealthy_source_count=unhealthy_source_count,
        exception_counts=exception_counts,
        generated_at=utcnow_naive(),
        db_path=settings.database_url,
    )


def _unhealthy_source_count(db: Session) -> int:
    source_names = [
        row[0]
        for row in db.query(IngestRun.ingest_source).filter(IngestRun.ingest_source.isnot(None)).distinct().all()
    ]
    unhealthy = 0
    for source_name in source_names:
        last_run = (
            db.query(IngestRun)
            .filter(IngestRun.ingest_source == source_name)
            .order_by(IngestRun.started_at.desc())
            .first()
        )
        last_success = (
            db.query(IngestRun)
            .filter(IngestRun.ingest_source == source_name, IngestRun.status == "success")
            .order_by(IngestRun.finished_at.desc())
            .first()
        )
        if last_run and last_run.status == "failed":
            unhealthy += 1
        elif last_success is None:
            unhealthy += 1
        elif (utcnow() - to_utc(last_success.finished_at)).total_seconds() > _source_interval(source_name) * 2:
            unhealthy += 1
    return unhealthy


def _source_interval(source_name: str) -> int:
    return {
        "eventregistry": settings.event_registry_interval_seconds,
        "nws": settings.nws_alerts_interval_seconds,
        "bluesky": settings.bluesky_interval_seconds,
        "mastodon": settings.mastodon_interval_seconds,
        "local_news": settings.local_news_interval_seconds,
        "acled": settings.acled_interval_seconds,
    }.get(source_name, settings.ingestion_interval_seconds)
