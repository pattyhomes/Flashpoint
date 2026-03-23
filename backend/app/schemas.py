from datetime import datetime

from pydantic import BaseModel


# ---------------------------------------------------------------------------
# Internal — used by the ingestion pipeline, not returned to clients
# ---------------------------------------------------------------------------

class EventCreate(BaseModel):
    external_id: str | None = None
    source_id: str | None = None
    title: str
    summary: str | None = None
    event_type: str
    city: str | None = None
    state: str | None = None
    country: str = "US"
    latitude: float
    longitude: float
    occurred_at: datetime
    source_url: str | None = None
    source_name: str
    source_count: int = 1
    confidence_score: float = 1.0
    severity_score: float = 0.0
    cluster_id: int | None = None
    trend_state: str | None = None
    is_active: bool = True
    raw_payload_json: str | None = None


# ---------------------------------------------------------------------------
# API response schemas
# ---------------------------------------------------------------------------

class EventOut(BaseModel):
    id: int
    external_id: str | None
    source_id: str | None
    title: str
    summary: str | None
    event_type: str
    city: str | None
    state: str | None
    country: str
    latitude: float
    longitude: float
    occurred_at: datetime
    ingested_at: datetime
    source_url: str | None
    source_name: str
    source_count: int
    confidence_score: float
    severity_score: float
    cluster_id: int | None
    trend_state: str | None
    is_active: bool

    model_config = {"from_attributes": True}


class HotspotOut(BaseModel):
    id: int
    name: str | None
    centroid_lat: float
    centroid_lon: float
    event_count: int
    confidence_score: float
    severity_score: float
    momentum_score: float
    priority_score: float
    trend_state: str | None
    status_label: str | None
    last_computed_at: datetime | None

    model_config = {"from_attributes": True}


class HealthResponse(BaseModel):
    status: str
    service: str
    db_status: str
    timestamp: str
