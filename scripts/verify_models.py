"""
Temporary verification script — confirms models and schemas load correctly.
Run from the backend/ directory: python ../scripts/verify_models.py
Delete after use.
"""
from sqlalchemy import create_engine

from app.database import Base
from app.models import Event, Hotspot
from app.schemas import EventCreate, EventOut, HotspotOut, HealthResponse

# Create tables in a throw-away in-memory database
test_engine = create_engine("sqlite:///:memory:")
Base.metadata.create_all(bind=test_engine)

table_names = sorted(Base.metadata.tables.keys())
print("Tables:", table_names)

event_cols = [c.name for c in Event.__table__.columns]
print("Event columns:", event_cols)

hotspot_cols = [c.name for c in Hotspot.__table__.columns]
print("Hotspot columns:", hotspot_cols)

print("Schemas loaded:", [EventCreate.__name__, EventOut.__name__, HotspotOut.__name__, HealthResponse.__name__])
print("OK")
