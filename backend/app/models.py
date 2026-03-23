from datetime import datetime

from sqlalchemy import DateTime, Float, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class Event(Base):
    __tablename__ = "events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    # What kind of event: protest, violence, disruption, unrest, etc.
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)

    # 1 (low) to 5 (critical)
    severity: Mapped[int] = mapped_column(Integer, default=1)

    # active | resolved | monitoring
    status: Mapped[str] = mapped_column(String(32), default="active")

    latitude: Mapped[float] = mapped_column(Float, nullable=False)
    longitude: Mapped[float] = mapped_column(Float, nullable=False)
    location_name: Mapped[str | None] = mapped_column(String(255), nullable=True)

    source: Mapped[str] = mapped_column(String(64), nullable=False)
    source_id: Mapped[str | None] = mapped_column(String(255), nullable=True, unique=True)

    # 0.0–1.0: how reliable we believe this event report to be
    confidence: Mapped[float] = mapped_column(Float, default=1.0)

    occurred_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    ingested_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
