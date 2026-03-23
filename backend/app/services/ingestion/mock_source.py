import random
from datetime import datetime, timedelta

from app.schemas import EventCreate
from app.services.ingestion.base import BaseSource

# Representative sample events spread across the U.S.
_MOCK_EVENTS = [
    {"title": "Labor protest downtown", "event_type": "protest", "severity": 2,
     "lat": 40.7128, "lon": -74.0060, "city": "New York, NY"},
    {"title": "Highway blockade reported", "event_type": "disruption", "severity": 3,
     "lat": 34.0522, "lon": -118.2437, "city": "Los Angeles, CA"},
    {"title": "Armed standoff in progress", "event_type": "violence", "severity": 5,
     "lat": 41.8781, "lon": -87.6298, "city": "Chicago, IL"},
    {"title": "Demonstration near capitol", "event_type": "protest", "severity": 1,
     "lat": 38.9072, "lon": -77.0369, "city": "Washington, DC"},
    {"title": "Civil unrest reported", "event_type": "unrest", "severity": 4,
     "lat": 29.7604, "lon": -95.3698, "city": "Houston, TX"},
    {"title": "Public disturbance at transit hub", "event_type": "disruption", "severity": 2,
     "lat": 33.7490, "lon": -84.3880, "city": "Atlanta, GA"},
    {"title": "Protest march blocking street", "event_type": "protest", "severity": 3,
     "lat": 47.6062, "lon": -122.3321, "city": "Seattle, WA"},
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
            slug = item["city"].lower().replace(", ", "-").replace(" ", "-")
            events.append(EventCreate(
                title=item["title"],
                event_type=item["event_type"],
                severity=item["severity"],
                latitude=round(lat, 6),
                longitude=round(lon, 6),
                location_name=item["city"],
                source=self.source_name,
                source_id=f"mock-{slug}-{int(occurred.timestamp())}",
                confidence=round(random.uniform(0.7, 1.0), 2),
                occurred_at=occurred,
            ))
        return events
