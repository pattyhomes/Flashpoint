from abc import ABC, abstractmethod

from app.schemas import EventCreate


class BaseSource(ABC):
    """All data sources inherit from this. Implement fetch() to return events."""

    source_name: str = "unknown"

    @abstractmethod
    def fetch(self) -> list[EventCreate]:
        """Fetch and return a list of events from this source."""
        ...
