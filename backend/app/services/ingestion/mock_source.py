from datetime import datetime, timedelta

from app.schemas import EventCreate
from app.services.ingestion.base import BaseSource

# 16 realistic U.S. unrest events grouped into 5 geographic clusters.
# source_id is deterministic (no timestamp) so the scheduler's dedup works across runs.
# hours_ago sets occurred_at relative to ingest time — keeps ordering meaningful.
_MOCK_EVENTS = [
    # --- Pacific Northwest cluster ---
    {"title": "Armed clash between protesters and counter-protesters",
     "event_type": "violence", "severity_score": 0.90, "confidence_score": 0.88,
     "lat": 47.6062, "lon": -122.3321, "city": "Seattle", "state": "WA", "hours_ago": 1},
    {"title": "Freeway shutdown by demonstrators",
     "event_type": "disruption", "severity_score": 0.70, "confidence_score": 0.92,
     "lat": 47.5952, "lon": -122.3318, "city": "Seattle", "state": "WA", "hours_ago": 3},
    {"title": "March on police precinct turns confrontational",
     "event_type": "violence", "severity_score": 0.85, "confidence_score": 0.85,
     "lat": 47.6205, "lon": -122.3492, "city": "Seattle", "state": "WA", "hours_ago": 6},
    {"title": "Incendiary device thrown at federal building",
     "event_type": "violence", "severity_score": 0.95, "confidence_score": 0.80,
     "lat": 45.5231, "lon": -122.6765, "city": "Portland", "state": "OR", "hours_ago": 2},
    {"title": "Protest encampment blocking major thoroughfare",
     "event_type": "disruption", "severity_score": 0.50, "confidence_score": 0.95,
     "lat": 45.5122, "lon": -122.6587, "city": "Portland", "state": "OR", "hours_ago": 8},

    # --- Chicago cluster ---
    {"title": "Armed standoff near public housing complex",
     "event_type": "violence", "severity_score": 1.00, "confidence_score": 0.90,
     "lat": 41.8781, "lon": -87.6298, "city": "Chicago", "state": "IL", "hours_ago": 2},
    {"title": "Mass unrest following officer-involved shooting",
     "event_type": "unrest", "severity_score": 0.90, "confidence_score": 0.85,
     "lat": 41.8827, "lon": -87.6233, "city": "Chicago", "state": "IL", "hours_ago": 4},
    {"title": "Retaliatory shooting injures multiple civilians",
     "event_type": "violence", "severity_score": 0.85, "confidence_score": 0.82,
     "lat": 41.8650, "lon": -87.6412, "city": "Chicago", "state": "IL", "hours_ago": 7},

    # --- Texas cluster ---
    {"title": "Port workers' strike turns confrontational",
     "event_type": "disruption", "severity_score": 0.60, "confidence_score": 0.88,
     "lat": 29.7604, "lon": -95.3698, "city": "Houston", "state": "TX", "hours_ago": 5},
    {"title": "Protesters occupy government building lobby",
     "event_type": "protest", "severity_score": 0.50, "confidence_score": 0.91,
     "lat": 29.7537, "lon": -95.3673, "city": "Houston", "state": "TX", "hours_ago": 9},
    {"title": "Anti-immigration policy march blocks interstate",
     "event_type": "protest", "severity_score": 0.65, "confidence_score": 0.78,
     "lat": 29.4241, "lon": -98.4936, "city": "San Antonio", "state": "TX", "hours_ago": 11},

    # --- East Coast cluster ---
    {"title": "Large demonstration outside Capitol building",
     "event_type": "protest", "severity_score": 0.30, "confidence_score": 0.95,
     "lat": 38.9072, "lon": -77.0369, "city": "Washington", "state": "DC", "hours_ago": 3},
    {"title": "Labor strike and walkout at city hall",
     "event_type": "protest", "severity_score": 0.40, "confidence_score": 0.90,
     "lat": 40.7128, "lon": -74.0060, "city": "New York", "state": "NY", "hours_ago": 6},
    {"title": "Transit disruption from protest march",
     "event_type": "disruption", "severity_score": 0.45, "confidence_score": 0.87,
     "lat": 39.9526, "lon": -75.1652, "city": "Philadelphia", "state": "PA", "hours_ago": 10},

    # --- Southern California cluster ---
    {"title": "Freeway blockade halts rush-hour traffic",
     "event_type": "disruption", "severity_score": 0.60, "confidence_score": 0.93,
     "lat": 34.0522, "lon": -118.2437, "city": "Los Angeles", "state": "CA", "hours_ago": 4},
    {"title": "Port picket line turns confrontational",
     "event_type": "disruption", "severity_score": 0.50, "confidence_score": 0.85,
     "lat": 33.7515, "lon": -118.2310, "city": "Los Angeles", "state": "CA", "hours_ago": 12},
]


class MockSource(BaseSource):
    source_name = "mock"

    def fetch(self) -> list[EventCreate]:
        now = datetime.utcnow()
        events = []
        city_counters: dict[str, int] = {}

        for item in _MOCK_EVENTS:
            slug = f"{item['city'].lower().replace(' ', '-')}-{item['state'].lower()}"
            city_counters[slug] = city_counters.get(slug, 0) + 1
            source_id = f"mock-{slug}-{city_counters[slug]:02d}"

            events.append(EventCreate(
                title=item["title"],
                event_type=item["event_type"],
                severity_score=item["severity_score"],
                confidence_score=item["confidence_score"],
                latitude=item["lat"],
                longitude=item["lon"],
                city=item["city"],
                state=item["state"],
                source_name=self.source_name,
                source_id=source_id,
                occurred_at=now - timedelta(hours=item["hours_ago"]),
            ))
        return events
