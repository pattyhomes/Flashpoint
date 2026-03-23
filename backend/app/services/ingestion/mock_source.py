import random
from datetime import datetime, timedelta

from app.schemas import EventCreate
from app.services.ingestion.base import BaseSource

# Representative sample events spread across the U.S.
_MOCK_EVENTS = [
    {"title": "Labor protest downtown", "event_type": "protest", "severity_score": 0.4,
     "lat": 40.7128, "lon": -74.0060, "city": "New York", "state": "NY"},
    {"title": "Highway blockade reported", "event_type": "disruption", "severity_score": 0.6,
     "lat": 34.0522, "lon": -118.2437, "city": "Los Angeles", "state": "CA"},
    {"title": "Armed standoff in progress", "event_type": "violence", "severity_score": 1.0,
     "lat": 41.8781, "lon": -87.6298, "city": "Chicago", "state": "IL"},
    {"title": "Demonstration near capitol", "event_type": "protest", "severity_score": 0.2,
     "lat": 38.9072, "lon": -77.0369, "city": "Washington", "state": "DC"},
    {"title": "Civil unrest reported", "event_type": "unrest", "severity_score": 0.8,
     "lat": 29.7604, "lon": -95.3698, "city": "Houston", "state": "TX"},
    {"title": "Public disturbance at transit hub", "event_type": "disruption", "severity_score": 0.4,
     "lat": 33.7490, "lon": -84.3880, "city": "Atlanta", "state": "GA"},
    {"title": "Protest march blocking street", "event_type": "protest", "severity_score": 0.6,
     "lat": 47.6062, "lon": -122.3321, "city": "Seattle", "state": "WA"},
]


class MockSource(BaseSource):
    source_name = "mock"

    def fetch(self) -> list[EventCreate]:
        now = datetime.utcnow()
        events = []
        for item in _MOCK_EVENTS:
            # Add small jitter so map points don't stack exactly
            lat = item["lat"] + random.uniform(-0.05, 0.05)
            lon = item["lon"] + random.uniform(-0.05, 0.05)
            occurred = now - timedelta(minutes=random.randint(0, 180))
            slug = f"{item['city'].lower().replace(' ', '-')}-{item['state'].lower()}"
            events.append(EventCreate(
                title=item["title"],
                event_type=item["event_type"],
                severity_score=item["severity_score"],
                latitude=round(lat, 6),
                longitude=round(lon, 6),
                city=item["city"],
                state=item["state"],
                source_name=self.source_name,
                source_id=f"mock-{slug}-{int(occurred.timestamp())}",
                confidence_score=round(random.uniform(0.7, 1.0), 2),
                occurred_at=occurred,
            ))
        return events
