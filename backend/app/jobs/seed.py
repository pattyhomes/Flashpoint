from app.database import SessionLocal
from app.models import Event
from app.services.ingestion.deduper import is_duplicate
from app.services.ingestion.mock_source import MockSource


def run_mock_ingestion():
    """Fetch mock events and insert any that aren't already in the database."""
    source = MockSource()
    events = source.fetch()

    db = SessionLocal()
    try:
        inserted = 0
        for event_schema in events:
            if event_schema.source_id and is_duplicate(event_schema.source_id, db):
                continue
            db.add(Event(**event_schema.model_dump()))
            inserted += 1
        db.commit()
        print(f"[seed] Inserted {inserted} new mock events.")
    except Exception as e:
        db.rollback()
        print(f"[seed] Error: {e}")
    finally:
        db.close()
