from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.utils.time import utcnow_naive


class Event(Base):
    __tablename__ = "events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)

    # IDs from upstream sources — used for deduplication
    external_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    source_id: Mapped[str | None] = mapped_column(String(255), nullable=True, unique=True, index=True)

    # Core content
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Classification: protest | violence | disruption | unrest | other
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)

    # Location
    city: Mapped[str | None] = mapped_column(String(128), nullable=True)
    state: Mapped[str | None] = mapped_column(String(64), nullable=True)
    country: Mapped[str] = mapped_column(String(64), nullable=False, default="US")
    latitude: Mapped[float] = mapped_column(Float, nullable=False)
    longitude: Mapped[float] = mapped_column(Float, nullable=False)

    # Timestamps
    occurred_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    ingested_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow_naive)

    # Source metadata
    source_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    source_name: Mapped[str] = mapped_column(String(64), nullable=False)
    source_count: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    # Scoring — both 0.0 to 1.0
    confidence_score: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)
    severity_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)

    # Clustering and trend state — populated by background scoring jobs
    cluster_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    trend_state: Mapped[str | None] = mapped_column(String(32), nullable=True)  # escalating | stable | declining

    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    # Location precision — venue / city / state / country; reflects how precisely the event location is known
    location_precision: Mapped[str | None] = mapped_column(String(32), nullable=True)

    # Raw ingest payload stored as JSON string — for debugging and re-processing
    raw_payload_json: Mapped[str | None] = mapped_column(Text, nullable=True)


class Hotspot(Base):
    __tablename__ = "hotspots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Geographic center of the hotspot cluster
    centroid_lat: Mapped[float] = mapped_column(Float, nullable=False)
    centroid_lon: Mapped[float] = mapped_column(Float, nullable=False)

    # Aggregated metrics — computed by scoring jobs
    event_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    confidence_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    severity_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    momentum_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    priority_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)

    trend_state: Mapped[str | None] = mapped_column(String(32), nullable=True)  # escalating | stable | declining
    status_label: Mapped[str | None] = mapped_column(String(64), nullable=True)  # e.g. "Active Hotspot", "Emerging"

    last_computed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class EventSource(Base):
    """Per-article provenance record for multi-source events.

    One Event may have many EventSource rows — one per article or raw record that
    was linked to it. Currently populated by the Event Registry adapter. GDELT/mock
    events have zero EventSource rows; their provenance lives on Event.source_name
    and Event.source_url directly.
    """
    __tablename__ = "event_sources"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    event_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)

    # Source identity
    source_type: Mapped[str] = mapped_column(String(32), nullable=False)         # "eventregistry"
    source_record_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)  # e.g. ER article uri
    source_name: Mapped[str | None] = mapped_column(String(128), nullable=True)  # outlet name
    source_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    source_title: Mapped[str | None] = mapped_column(String(512), nullable=True)
    source_published_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    # Trust weighting — 0.0 means syndicated/duplicate (stored for provenance but no corroboration credit)
    source_trust_weight: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)

    # Location precision of this specific source record
    location_precision: Mapped[str | None] = mapped_column(String(32), nullable=True)

    # Arbitrary extra metadata (JSON string)
    metadata_json: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow_naive)


class EvidenceItem(Base):
    """Raw source evidence captured before it becomes an event.

    Evidence is the provenance layer for weak leads, context alerts, and
    corroborating source records. Events remain the confirmed/synthesized layer.
    """
    __tablename__ = "evidence_items"
    __table_args__ = (
        UniqueConstraint("source_type", "source_record_id", name="uq_evidence_source_record"),
        UniqueConstraint("source_type", "content_hash", name="uq_evidence_source_hash"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)

    source_type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    source_record_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    source_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    source_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    source_title: Mapped[str | None] = mapped_column(String(512), nullable=True)
    excerpt: Mapped[str | None] = mapped_column(Text, nullable=True)

    published_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    fetched_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow_naive)

    content_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    trust_tier: Mapped[str] = mapped_column(String(32), nullable=False, default="weak")
    embedding_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    raw_payload_json: Mapped[str | None] = mapped_column(Text, nullable=True)


class Observation(Base):
    """Candidate intelligence extracted from evidence.

    Observations can be weak leads, context records, linked corroboration, or
    promoted events. Only linked/promoted observations can affect Event/Hotspot
    state.
    """
    __tablename__ = "observations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    evidence_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)

    status: Mapped[str] = mapped_column(String(32), nullable=False, default="lead", index=True)
    candidate_event_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)

    city: Mapped[str | None] = mapped_column(String(128), nullable=True)
    state: Mapped[str | None] = mapped_column(String(64), nullable=True)
    country: Mapped[str] = mapped_column(String(64), nullable=False, default="US")
    latitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    longitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    location_precision: Mapped[str | None] = mapped_column(String(32), nullable=True)
    location_confidence: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)
    location_reason: Mapped[str | None] = mapped_column(String(255), nullable=True)
    exception_category: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    exception_detail: Mapped[str | None] = mapped_column(Text, nullable=True)

    observed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    confidence_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    severity_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)

    linked_event_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    promoted_event_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow_naive)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow_naive)


class IngestRun(Base):
    __tablename__ = "ingest_runs"

    id:               Mapped[int]           = mapped_column(Integer, primary_key=True, index=True)
    started_at:       Mapped[datetime]      = mapped_column(DateTime, nullable=False)
    finished_at:      Mapped[datetime|None] = mapped_column(DateTime, nullable=True)
    status:           Mapped[str]           = mapped_column(String(16), nullable=False)  # running | success | failed
    events_inserted:  Mapped[int]           = mapped_column(Integer, nullable=False, default=0)
    error_message:    Mapped[str|None]      = mapped_column(Text, nullable=True)
    ingest_source:    Mapped[str|None]      = mapped_column(String(32), nullable=True)   # "mock" | "gdelt" | null (legacy)
    records_fetched:  Mapped[int]           = mapped_column(Integer, nullable=False, default=0)
    evidence_inserted: Mapped[int]          = mapped_column(Integer, nullable=False, default=0)
    observations_inserted: Mapped[int]      = mapped_column(Integer, nullable=False, default=0)
    records_rejected: Mapped[int]           = mapped_column(Integer, nullable=False, default=0)
    reject_counts_json: Mapped[str|None]    = mapped_column(Text, nullable=True)
    sample_records_json: Mapped[str|None]   = mapped_column(Text, nullable=True)


class LocationCache(Base):
    __tablename__ = "location_cache"
    __table_args__ = (
        UniqueConstraint("query", name="uq_location_cache_query"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    query: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    city: Mapped[str | None] = mapped_column(String(128), nullable=True)
    county: Mapped[str | None] = mapped_column(String(128), nullable=True)
    state: Mapped[str | None] = mapped_column(String(64), nullable=True)
    country: Mapped[str] = mapped_column(String(64), nullable=False, default="US")
    latitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    longitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    precision: Mapped[str | None] = mapped_column(String(32), nullable=True)
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    reason: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow_naive)


class LocationAlias(Base):
    __tablename__ = "location_aliases"
    __table_args__ = (
        UniqueConstraint("alias", "state", name="uq_location_alias_state"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    alias: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    city: Mapped[str | None] = mapped_column(String(128), nullable=True)
    county: Mapped[str | None] = mapped_column(String(128), nullable=True)
    state: Mapped[str | None] = mapped_column(String(64), nullable=True)
    latitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    longitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    precision: Mapped[str] = mapped_column(String(32), nullable=False, default="city")
