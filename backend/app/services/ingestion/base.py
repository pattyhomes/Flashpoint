from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime

from app.schemas import EventCreate


@dataclass(frozen=True)
class ObservationCandidate:
    source_type: str
    source_record_id: str | None
    source_url: str | None
    source_name: str | None
    source_title: str | None
    excerpt: str | None
    published_at: datetime | None
    trust_tier: str
    raw_payload: dict | list | None
    status: str
    title: str
    summary: str | None = None
    candidate_event_type: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    city: str | None = None
    state: str | None = None
    country: str = "US"
    observed_at: datetime | None = None
    confidence_score: float = 0.0
    severity_score: float = 0.0
    location_precision: str | None = None
    location_confidence: float = 1.0
    location_reason: str | None = None
    exception_category: str | None = None
    exception_detail: str | None = None


class BaseSource(ABC):
    """All data sources inherit from this. Implement fetch() to return events."""

    source_name: str = "unknown"

    @abstractmethod
    def fetch(self) -> list[EventCreate]:
        """Fetch and return a list of events from this source."""
        ...
