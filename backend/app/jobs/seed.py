from app.database import SessionLocal
from app.models import Event, Hotspot
from app.services.ingestion.deduper import is_duplicate
from app.services.ingestion.mock_source import MockSource
from app.services.scoring.hotspot import compute_hotspots

# Cluster definitions: name + centroid only.
# Scores are computed dynamically by compute_hotspots().
_HOTSPOT_SEEDS = [
    {"name": "Pacific Northwest Unrest",       "centroid_lat": 47.0200, "centroid_lon": -122.6500},
    {"name": "Chicago Violence Cluster",        "centroid_lat": 41.8781, "centroid_lon":  -87.6298},
    {"name": "Texas Unrest Cluster",           "centroid_lat": 29.6500, "centroid_lon":  -96.5000},
    {"name": "East Coast Political Activity",  "centroid_lat": 39.5000, "centroid_lon":  -76.5000},
    {"name": "Southern California Disruption", "centroid_lat": 33.9000, "centroid_lon": -118.2400},
]


def run_mock_ingestion():
    """Insert new mock events, skipping any already in the database.
    Called by the background scheduler — does not wipe existing data."""
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
        compute_hotspots(db)
    except Exception as e:
        db.rollback()
        print(f"[seed] Error: {e}")
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

        for data in _HOTSPOT_SEEDS:
            db.add(Hotspot(**data))

        db.commit()
        print(f"[seed] Seeded {len(events)} events and {len(_HOTSPOT_SEEDS)} hotspot definitions.")

        compute_hotspots(db)
    except Exception as e:
        db.rollback()
        print(f"[seed] Error: {e}")
    finally:
        db.close()
