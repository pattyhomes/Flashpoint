from datetime import datetime

from app.database import SessionLocal
from app.models import Event, Hotspot
from app.services.ingestion.deduper import is_duplicate
from app.services.ingestion.mock_source import MockSource

# Hardcoded mock hotspots — realistic but not computed.
# Ordered here by priority_score descending so the intent is clear.
_MOCK_HOTSPOTS = [
    {
        "name": "Pacific Northwest Unrest",
        "centroid_lat": 47.0200,
        "centroid_lon": -122.6500,
        "event_count": 5,
        "confidence_score": 0.88,
        "severity_score": 0.85,
        "momentum_score": 0.80,
        "priority_score": 0.88,
        "trend_state": "escalating",
        "status_label": "Active Hotspot",
    },
    {
        "name": "Chicago Violence Cluster",
        "centroid_lat": 41.8781,
        "centroid_lon": -87.6298,
        "event_count": 3,
        "confidence_score": 0.86,
        "severity_score": 0.92,
        "momentum_score": 0.72,
        "priority_score": 0.82,
        "trend_state": "escalating",
        "status_label": "Active Hotspot",
    },
    {
        "name": "Texas Unrest Cluster",
        "centroid_lat": 29.6500,
        "centroid_lon": -96.5000,
        "event_count": 3,
        "confidence_score": 0.76,
        "severity_score": 0.60,
        "momentum_score": 0.55,
        "priority_score": 0.63,
        "trend_state": "stable",
        "status_label": "Elevated Activity",
    },
    {
        "name": "East Coast Political Activity",
        "centroid_lat": 39.5000,
        "centroid_lon": -76.5000,
        "event_count": 3,
        "confidence_score": 0.90,
        "severity_score": 0.38,
        "momentum_score": 0.30,
        "priority_score": 0.43,
        "trend_state": "stable",
        "status_label": "Monitored",
    },
    {
        "name": "Southern California Disruption",
        "centroid_lat": 33.9000,
        "centroid_lon": -118.2400,
        "event_count": 2,
        "confidence_score": 0.89,
        "severity_score": 0.55,
        "momentum_score": 0.35,
        "priority_score": 0.38,
        "trend_state": "declining",
        "status_label": "Monitored",
    },
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
    except Exception as e:
        db.rollback()
        print(f"[seed] Error: {e}")
    finally:
        db.close()


def reset_and_seed():
    """Wipe all events and hotspots, then reseed from scratch.
    Safe to rerun — always produces a clean, consistent dataset."""
    source = MockSource()
    events = source.fetch()
    now = datetime.utcnow()

    db = SessionLocal()
    try:
        db.query(Hotspot).delete()
        db.query(Event).delete()
        db.commit()

        for event_schema in events:
            db.add(Event(**event_schema.model_dump()))

        for data in _MOCK_HOTSPOTS:
            db.add(Hotspot(**data, last_computed_at=now))

        db.commit()
        print(f"[seed] Seeded {len(events)} events and {len(_MOCK_HOTSPOTS)} hotspots.")
    except Exception as e:
        db.rollback()
        print(f"[seed] Error: {e}")
    finally:
        db.close()
