#!/usr/bin/env python3
import json
import os
import sys
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
from app.models import IngestRun  # noqa: E402


def _json(value, fallback):
    if not value:
        return fallback
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return fallback
    return parsed if isinstance(parsed, type(fallback)) else fallback


def main():
    _migrate()
    db = SessionLocal()
    try:
        source_names = [
            row[0]
            for row in db.query(IngestRun.ingest_source)
            .filter(IngestRun.ingest_source.isnot(None))
            .distinct()
            .all()
        ]
        report = []
        for source_name in sorted(source_names):
            run = (
                db.query(IngestRun)
                .filter(IngestRun.ingest_source == source_name)
                .order_by(IngestRun.started_at.desc())
                .first()
            )
            if not run:
                continue
            counts = _json(run.reject_counts_json, {})
            report.append({
                "source_name": source_name,
                "status": run.status,
                "last_run_at": run.started_at.isoformat() if run.started_at else None,
                "records_fetched": run.records_fetched,
                "observations_inserted": run.observations_inserted,
                "records_rejected": run.records_rejected,
                "reject_counts": counts,
                "specificity_counts": {
                    key.removeprefix("specificity:"): value
                    for key, value in counts.items()
                    if key.startswith("specificity:")
                },
                "quality_tier_counts": {
                    key.removeprefix("quality:"): value
                    for key, value in counts.items()
                    if key.startswith("quality:")
                },
                "records_enriched": counts.get("records_enriched", 0),
                "records_gated_low_specificity": counts.get("records_gated_low_specificity", 0),
                "records_detector_only": counts.get("records_detector_only", 0),
                "events_hotspot_eligible": counts.get("events_hotspot_eligible", 0),
                "sample_records": _json(run.sample_records_json, []),
                "source_breakdown": _json(run.source_breakdown_json, []),
            })
        print(json.dumps({"sources": report}, indent=2, sort_keys=True))
    finally:
        db.close()


if __name__ == "__main__":
    main()
