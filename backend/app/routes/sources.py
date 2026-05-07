import json
from datetime import datetime

from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.models import IngestRun, Observation
from app.schemas import SourcesStatusResponse
from app.utils.time import to_utc, utcnow, utcnow_naive

router = APIRouter(prefix="/sources", tags=["sources"])


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
        "stale": stale,
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
