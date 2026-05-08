import json
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.jobs.seed import run_observation_source_ingestion
from app.models import IngestRun, Observation
from app.schemas import SourceRunHistoryResponse, SourceRunRequestResponse, SourcesStatusResponse
from app.utils.time import to_utc, utcnow, utcnow_naive

router = APIRouter(prefix="/sources", tags=["sources"])

RUNNABLE_OBSERVATION_SOURCES = {"nws", "bluesky", "mastodon", "local_news", "acled"}


@router.get("/status", response_model=SourcesStatusResponse)
def sources_status(db: Session = Depends(get_db)):
    sources = []
    source_names = _known_source_names(db)
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
        sources.append(_source_payload(source_name, last_run, last_success))
    return {
        "sources": sources,
        "exception_counts": _exception_counts(db),
        "generated_at": utcnow_naive(),
    }


def _known_source_names(db: Session) -> list[str]:
    configured = []
    if settings.ingest_source in {"mock", "gdelt"}:
        configured.append(settings.ingest_source)
    if settings.event_registry_enabled:
        configured.append("eventregistry")
    if settings.nws_alerts_enabled:
        configured.append("nws")
    if settings.bluesky_enabled:
        configured.append("bluesky")
    if settings.mastodon_enabled:
        configured.append("mastodon")
    if settings.local_news_enabled:
        configured.append("local_news")
    if settings.acled_enabled:
        configured.append("acled")

    known_order = ["mock", "gdelt", "eventregistry", "nws", "bluesky", "mastodon", "local_news", "acled"]
    seen = {
        row[0]
        for row in db.query(IngestRun.ingest_source).filter(IngestRun.ingest_source.isnot(None)).distinct().all()
    }
    names = set(configured) | seen
    ordered = [name for name in known_order if name in names]
    extras = sorted(name for name in names if name not in known_order)
    return ordered + extras


def _source_payload(source_name: str, last_run: IngestRun | None, last_success: IngestRun | None) -> dict:
    stale = _is_stale(source_name, last_success.finished_at if last_success else None)
    status = "idle"
    if last_run:
        status = last_run.status
    if stale and status == "success":
        status = "stale"
    return {
        "source_name": source_name,
        "status": status,
        "last_run_at": last_run.started_at if last_run else None,
        "last_success_at": last_success.finished_at if last_success else None,
        "last_error": last_run.error_message if last_run and last_run.status == "failed" else None,
        "records_fetched": last_run.records_fetched if last_run else 0,
        "evidence_inserted": last_run.evidence_inserted if last_run else 0,
        "observations_inserted": last_run.observations_inserted if last_run else 0,
        "records_rejected": last_run.records_rejected if last_run else 0,
        "reject_counts": _json_dict(last_run.reject_counts_json if last_run else None),
        "sample_records": _json_list(last_run.sample_records_json if last_run else None),
        "runnable": source_name in RUNNABLE_OBSERVATION_SOURCES,
        "stale": stale,
    }


@router.get("/runs", response_model=SourceRunHistoryResponse)
def source_runs(
    source_name: str | None = None,
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    query = db.query(IngestRun).filter(IngestRun.ingest_source.isnot(None))
    if source_name:
        query = query.filter(IngestRun.ingest_source == source_name)
    total = query.count()
    rows = query.order_by(IngestRun.started_at.desc()).limit(limit).all()
    return {
        "runs": [_run_payload(row) for row in rows],
        "total": total,
        "limit": limit,
        "source_name": source_name,
        "generated_at": utcnow_naive(),
    }


@router.post("/{source_name}/run", response_model=SourceRunRequestResponse)
def run_source_now(source_name: str):
    if source_name not in RUNNABLE_OBSERVATION_SOURCES:
        raise HTTPException(
            status_code=400,
            detail=f"Source {source_name!r} is not runnable from the operator console",
        )
    run_observation_source_ingestion(source_name)
    return {
        "source_name": source_name,
        "status": "queued",
        "message": f"{source_name} ingest completed",
    }


def _run_payload(run: IngestRun) -> dict:
    return {
        "id": run.id,
        "source_name": run.ingest_source,
        "status": run.status,
        "started_at": run.started_at,
        "finished_at": run.finished_at,
        "events_inserted": run.events_inserted,
        "records_fetched": run.records_fetched,
        "evidence_inserted": run.evidence_inserted,
        "observations_inserted": run.observations_inserted,
        "records_rejected": run.records_rejected,
        "reject_counts": _json_dict(run.reject_counts_json),
        "sample_records": _json_list(run.sample_records_json),
        "error_message": run.error_message,
    }


def _is_stale(source_name: str, last_success_at: datetime | None) -> bool:
    if last_success_at is None:
        return True
    interval = {
        "eventregistry": settings.event_registry_interval_seconds,
        "nws": settings.nws_alerts_interval_seconds,
        "bluesky": settings.bluesky_interval_seconds,
        "mastodon": settings.mastodon_interval_seconds,
        "local_news": settings.local_news_interval_seconds,
        "acled": settings.acled_interval_seconds,
    }.get(source_name, settings.ingestion_interval_seconds)
    return (utcnow() - to_utc(last_success_at)).total_seconds() > interval * 2


def _exception_counts(db: Session) -> dict[str, int]:
    rows = (
        db.query(Observation.exception_category, func.count(Observation.id))
        .filter(Observation.exception_category.isnot(None), Observation.status == "lead")
        .group_by(Observation.exception_category)
        .all()
    )
    return {category: count for category, count in rows}


def _json_dict(value: str | None) -> dict[str, int]:
    if not value:
        return {}
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return {}
    if not isinstance(parsed, dict):
        return {}
    return {str(key): int(val) for key, val in parsed.items() if isinstance(val, int)}


def _json_list(value: str | None) -> list[dict]:
    if not value:
        return []
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return []
    if not isinstance(parsed, list):
        return []
    return [item for item in parsed if isinstance(item, dict)]
