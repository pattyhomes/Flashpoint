from datetime import datetime

from pydantic import BaseModel


class EventBase(BaseModel):
    title: str
    description: str | None = None
    event_type: str
    severity: int = 1
    status: str = "active"
    latitude: float
    longitude: float
    location_name: str | None = None
    source: str
    source_id: str | None = None
    confidence: float = 1.0
    occurred_at: datetime


class EventCreate(EventBase):
    pass


class EventRead(EventBase):
    id: int
    ingested_at: datetime

    model_config = {"from_attributes": True}
