import re
from dataclasses import dataclass

from app.models import Event, EventSource


_GENERIC_TITLE_RE = re.compile(
    r"^(civil unrest|unrest|violence|protest|disruption|other)\s*(—|-|:)\s*.+$",
    re.IGNORECASE,
)
_SIGNAL_TITLE_RE = re.compile(
    r"^(civil unrest|unrest|violence|protest|disruption|other)\s+signal\s*(-|—)\s*.+$",
    re.IGNORECASE,
)
_LOW_LOCATION_PRECISIONS = {"state", "country", "area"}


@dataclass(frozen=True)
class EventDisplay:
    display_title: str
    specificity_level: str
    specificity_reason: str
    is_generic_classification: bool
    explainability_score: float

    def as_dict(self) -> dict:
        return {
            "display_title": self.display_title,
            "specificity_level": self.specificity_level,
            "specificity_reason": self.specificity_reason,
            "is_generic_classification": self.is_generic_classification,
        }


def _location(event: Event) -> str:
    return ", ".join(part for part in [event.city, event.state] if part) or event.country


def _location_label(event: Event) -> str:
    if event.city:
        return event.city
    if event.state:
        return event.state
    return event.country


def _is_gdelt(event: Event) -> bool:
    return (event.source_name or "").lower() == "gdelt"


def is_generic_title(title: str | None) -> bool:
    value = (title or "").strip()
    if not value:
        return True
    if _SIGNAL_TITLE_RE.match(value):
        return True
    if _GENERIC_TITLE_RE.match(value):
        return True
    return False


def _best_specific_source_title(event: Event, sources: list[EventSource] | None) -> str | None:
    for source in sources or []:
        title = (source.source_title or "").strip()
        if not title:
            continue
        if title == event.title:
            continue
        if is_generic_title(title):
            continue
        return title
    return None


def _location_is_broad(event: Event) -> bool:
    precision = (event.location_precision or "").lower()
    if precision in _LOW_LOCATION_PRECISIONS:
        return True
    if event.city and event.state and event.city.upper() == event.state.upper():
        return True
    return False


def display_for_event(event: Event, sources: list[EventSource] | None = None) -> EventDisplay:
    specific_source_title = _best_specific_source_title(event, sources)
    event_title_is_generic = is_generic_title(event.title)
    generic_classification = _is_gdelt(event) and event_title_is_generic
    broad_location = _location_is_broad(event)

    if specific_source_title:
        reason = "Specific source title available."
        if broad_location:
            reason = "Specific source title available, but location is broad."
        return EventDisplay(
            display_title=specific_source_title,
            specificity_level="low_location" if broad_location else "specific",
            specificity_reason=reason,
            is_generic_classification=False,
            explainability_score=0.82 if broad_location else 1.0,
        )

    if not event_title_is_generic and not generic_classification:
        reason = "Confirmed event title is specific enough for display."
        if broad_location:
            reason = "Confirmed event title is specific, but location is broad."
        return EventDisplay(
            display_title=event.title,
            specificity_level="low_location" if broad_location else "specific",
            specificity_reason=reason,
            is_generic_classification=False,
            explainability_score=0.7 if broad_location else 0.9,
        )

    if _is_gdelt(event):
        precision = "State-level" if broad_location else "GDELT"
        display_title = f"{precision} GDELT {event.event_type} classification - {_location_label(event)}"
        reason = (
            "GDELT record has only a broad unrest classification; no clean incident-level title is attached."
            if broad_location
            else "GDELT record has only a broad unrest classification; no clean incident-level title is attached."
        )
        return EventDisplay(
            display_title=display_title,
            specificity_level="low_location" if broad_location else "classified",
            specificity_reason=reason,
            is_generic_classification=True,
            explainability_score=0.25 if broad_location else 0.4,
        )

    return EventDisplay(
        display_title=event.title or f"{event.event_type} classification - {_location(event)}",
        specificity_level="source_gap",
        specificity_reason="Confirmed event lacks a clean incident-level title from its attached sources.",
        is_generic_classification=True,
        explainability_score=0.2,
    )


def serialize_event(event: Event, sources: list[EventSource] | None = None) -> dict:
    display = display_for_event(event, sources)
    from app.services.event_quality import event_quality
    quality = event_quality(event, sources)
    return {
        "id": event.id,
        "external_id": event.external_id,
        "source_id": event.source_id,
        "title": event.title,
        "summary": event.summary,
        "event_type": event.event_type,
        "city": event.city,
        "state": event.state,
        "country": event.country,
        "latitude": event.latitude,
        "longitude": event.longitude,
        "occurred_at": event.occurred_at,
        "ingested_at": event.ingested_at,
        "source_url": event.source_url,
        "source_name": event.source_name,
        "source_count": event.source_count,
        "confidence_score": event.confidence_score,
        "severity_score": event.severity_score,
        "cluster_id": event.cluster_id,
        "trend_state": event.trend_state,
        "is_active": event.is_active,
        "location_precision": event.location_precision,
        **display.as_dict(),
        **quality.as_dict(),
    }
