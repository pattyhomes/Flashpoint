from datetime import datetime

from app.database import SessionLocal
from app.models import Event, Hotspot, IngestRun
from app.services.ingestion.deduper import is_duplicate
from app.services.ingestion.mock_source import MockSource
from app.services.scoring.hotspot import compute_hotspots


def run_mock_ingestion():
    """Insert new mock events, skipping any already in the database.
    Called by the background scheduler — does not wipe existing data.
    Persists an IngestRun record for every attempt; updates it to success or failed."""
    source = MockSource()
    events = source.fetch()

    db = SessionLocal()

    # Commit the run record before ingestion begins so it survives any failure.
    run = IngestRun(started_at=datetime.utcnow(), status="running", ingest_source="mock")
    db.add(run)
    db.commit()
    db.refresh(run)
    run_id = run.id

    try:
        inserted = 0
        for event_schema in events:
            if event_schema.source_id and is_duplicate(event_schema.source_id, db):
                continue
            db.add(Event(**event_schema.model_dump()))
            inserted += 1
        db.commit()

        run.status = "success"
        run.finished_at = datetime.utcnow()
        run.events_inserted = inserted
        db.commit()
        print(f"[seed] Inserted {inserted} new mock events.")
        compute_hotspots(db)
    except Exception as e:
        db.rollback()  # undoes uncommitted event inserts; the IngestRun commit above is unaffected
        run = db.get(IngestRun, run_id)
        run.status = "failed"
        run.finished_at = datetime.utcnow()
        run.error_message = str(e)[:1000]
        db.commit()
        print(f"[seed] Error: {e}")
    finally:
        db.close()


def run_gdelt_ingestion():
    """Fetch real events from GDELT 2.0, deduplicate, and store.
    Uses a source-aware checkpoint so GDELT and mock run histories stay separate.
    Persists an IngestRun record for every attempt; updates it to success or failed."""
    from app.services.ingestion.gdelt_source import GdeltSource

    db = SessionLocal()

    run = IngestRun(started_at=datetime.utcnow(), status="running", ingest_source="gdelt")
    db.add(run)
    db.commit()
    db.refresh(run)
    run_id = run.id

    try:
        # Source-aware checkpoint: last successful GDELT run ordered by finished_at
        last_success = (
            db.query(IngestRun)
            .filter(IngestRun.ingest_source == "gdelt", IngestRun.status == "success")
            .order_by(IngestRun.finished_at.desc())
            .first()
        )
        since = last_success.finished_at if last_success else None

        events = GdeltSource().fetch(since=since)

        inserted = 0
        for event_schema in events:
            if event_schema.source_id and is_duplicate(event_schema.source_id, db):
                continue
            db.add(Event(**event_schema.model_dump()))
            inserted += 1
        db.commit()

        run.status = "success"
        run.finished_at = datetime.utcnow()
        run.events_inserted = inserted
        db.commit()
        print(f"[gdelt] Inserted {inserted} new events.")
        compute_hotspots(db)
    except Exception as e:
        db.rollback()  # undoes uncommitted event inserts; the IngestRun commit above is unaffected
        run = db.get(IngestRun, run_id)
        run.status = "failed"
        run.finished_at = datetime.utcnow()
        run.error_message = str(e)[:1000]
        db.commit()
        print(f"[gdelt] Error: {e}")
    finally:
        db.close()


def reset_and_seed():
    """Wipe all events and hotspots, reseed from scratch, then compute hotspot scores.
    Safe to rerun — always produces a clean, consistent dataset."""
    source = MockSource()
    events = source.fetch()

    db = SessionLocal()
    try:
        db.query(Hotspot).delete()
        db.query(Event).delete()
        db.commit()

        for event_schema in events:
            db.add(Event(**event_schema.model_dump()))

        db.commit()
        print(f"[seed] Seeded {len(events)} events.")

        compute_hotspots(db)
    except Exception as e:
        db.rollback()
        print(f"[seed] Error: {e}")
    finally:
        db.close()
