#!/usr/bin/env python3
import argparse
import json
import os
import sys
from datetime import timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VENV_PYTHON = ROOT / ".venv" / "bin" / "python"
if VENV_PYTHON.exists() and Path(sys.executable) != VENV_PYTHON:
    os.execv(str(VENV_PYTHON), [str(VENV_PYTHON), str(Path(__file__).resolve()), *sys.argv[1:]])

BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.database import SessionLocal  # noqa: E402
from app.main import _migrate  # noqa: E402
from app.models import Event, EventSource, EvidenceItem  # noqa: E402
from app.services.article_metadata import fetch_article_metadata, is_specific_unrest_metadata  # noqa: E402
from app.services.event_quality import event_quality  # noqa: E402
from app.services.scoring.hotspot import compute_hotspots  # noqa: E402
from app.utils.time import utcnow_naive  # noqa: E402


def _sources_by_event(db, events: list[Event]) -> dict[int, list[EventSource]]:
    event_ids = [event.id for event in events]
    grouped: dict[int, list[EventSource]] = {}
    if not event_ids:
        return grouped
    for source in db.query(EventSource).filter(EventSource.event_id.in_(event_ids)).all():
        grouped.setdefault(source.event_id, []).append(source)
    return grouped


def _metadata_payload(event: Event, metadata) -> str:
    try:
        payload = json.loads(event.raw_payload_json or "{}")
    except json.JSONDecodeError:
        payload = {}
    payload["article_metadata"] = {
        "title": metadata.title,
        "excerpt": metadata.excerpt,
        "final_url": metadata.final_url,
        "reason": metadata.reason,
    }
    return json.dumps(payload, sort_keys=True, separators=(",", ":"))


def _apply_metadata(db, event: Event, metadata) -> bool:
    if not metadata.usable:
        return False
    payload_json = _metadata_payload(event, metadata)
    event.raw_payload_json = payload_json
    event.summary = metadata.excerpt or event.summary

    evidence = (
        db.query(EvidenceItem)
        .filter(EvidenceItem.source_type == "gdelt", EvidenceItem.source_record_id == event.source_id)
        .first()
    )
    if evidence is not None:
        evidence.source_title = metadata.title
        evidence.excerpt = metadata.excerpt or evidence.excerpt
        evidence.raw_payload_json = payload_json

    existing = (
        db.query(EventSource)
        .filter(
            EventSource.event_id == event.id,
            EventSource.source_type == "article",
            EventSource.source_record_id == event.source_id,
        )
        .first()
    )
    if existing is None:
        db.add(EventSource(
            event_id=event.id,
            source_type="article",
            source_record_id=event.source_id,
            source_name="GDELT source article",
            source_url=metadata.final_url or event.source_url,
            source_title=metadata.title,
            source_published_at=event.occurred_at,
            source_trust_weight=1.0,
            location_precision=event.location_precision,
            metadata_json=payload_json,
        ))
    else:
        existing.source_url = metadata.final_url or existing.source_url
        existing.source_title = metadata.title
        existing.metadata_json = payload_json
    return True


def run(*, apply: bool, limit: int, hours: int) -> dict:
    _migrate()
    db = SessionLocal()
    try:
        cutoff = utcnow_naive() - timedelta(hours=hours)
        candidates = (
            db.query(Event)
            .filter(
                Event.is_active == True,
                Event.source_name == "gdelt",
                Event.source_url.isnot(None),
                Event.occurred_at >= cutoff,
            )
            .order_by(Event.cluster_id.is_(None), Event.severity_score.desc(), Event.occurred_at.desc())
            .limit(limit)
            .all()
        )
        sources_by_event = _sources_by_event(db, candidates)
        detector_only = [
            event
            for event in candidates
            if event_quality(event, sources_by_event.get(event.id, [])).quality_tier in {"detector_only", "broad_detector"}
        ]
        enriched = 0
        fetchable = 0
        sample = []
        for event in detector_only:
            if event.source_url:
                fetchable += 1
            metadata = fetch_article_metadata(event.source_url)
            article_specific = is_specific_unrest_metadata(metadata)
            if article_specific:
                enriched += 1
                if apply:
                    _apply_metadata(db, event, metadata)
            if len(sample) < 8:
                sample.append({
                    "event_id": event.id,
                    "source_url": event.source_url,
                    "metadata_title": metadata.title,
                    "usable": article_specific,
                    "reason": metadata.reason,
                })
        if apply:
            db.commit()
            compute_hotspots(db)
        else:
            db.rollback()
        return {
            "mode": "apply" if apply else "dry-run",
            "candidates_found": len(candidates),
            "detector_only_candidates": len(detector_only),
            "article_urls_available": fetchable,
            "likely_enrichable_records": enriched,
            "sample": sample,
        }
    finally:
        db.close()


def main():
    parser = argparse.ArgumentParser(description="Backfill recent GDELT events with safe article metadata.")
    parser.add_argument("--apply", action="store_true", help="Persist enrichment and recompute hotspots.")
    parser.add_argument("--dry-run", action="store_true", help="Report candidate enrichment without persisting changes.")
    parser.add_argument("--limit", type=int, default=100)
    parser.add_argument("--hours", type=int, default=72)
    args = parser.parse_args()
    print(json.dumps(run(apply=args.apply, limit=args.limit, hours=args.hours), indent=2, default=str))


if __name__ == "__main__":
    main()
