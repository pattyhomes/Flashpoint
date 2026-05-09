from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from app.models import Event, EventSource, Hotspot
from app.utils.time import utcnow_naive


def _pct(value: float | None) -> int:
    return round(max(0.0, min(1.0, value or 0.0)) * 100)


def _location(event: Event) -> str:
    return ", ".join(part for part in [event.city, event.state] if part) or event.country


def _event_label(event: Event) -> str:
    if event.source_name == "gdelt":
        return f"{event.event_type} signal - {_location(event)}"
    return event.title


def _hours_ago(value: datetime, now: datetime) -> int:
    return max(0, round((now - value).total_seconds() / 3600))


def _citation_key(citation: dict) -> tuple[str, str, str, str]:
    return (
        citation.get("source_type") or "",
        citation.get("source_name") or "",
        citation.get("url") or "",
        citation.get("title") or "",
    )


def _source_rows(db: Session, events: list[Event]) -> dict[int, list[EventSource]]:
    event_ids = [event.id for event in events]
    if not event_ids:
        return {}
    rows = (
        db.query(EventSource)
        .filter(EventSource.event_id.in_(event_ids))
        .order_by(EventSource.source_published_at.desc().nullslast(), EventSource.id.asc())
        .all()
    )
    grouped: dict[int, list[EventSource]] = {}
    for row in rows:
        grouped.setdefault(row.event_id, []).append(row)
    return grouped


def _add_citation(
    citations: list[dict],
    *,
    event_id: int,
    source_type: str,
    source_name: str | None,
    title: str | None,
    url: str | None,
    published_at: datetime | None,
    counted: bool,
    note: str,
) -> int:
    citation = {
        "id": len(citations) + 1,
        "event_id": event_id,
        "source_type": source_type,
        "source_name": source_name,
        "title": title,
        "url": url,
        "published_at": published_at,
        "counted": counted,
        "note": note,
    }
    citations.append(citation)
    return citation["id"]


def _build_citations(db: Session, events: list[Event]) -> tuple[list[dict], dict[int, list[int]]]:
    grouped = _source_rows(db, events)
    citations: list[dict] = []
    citation_ids_by_event: dict[int, list[int]] = {}

    for event in events:
        primary_id = _add_citation(
            citations,
            event_id=event.id,
            source_type=event.source_name,
            source_name=event.source_name,
            title=event.title,
            url=event.source_url,
            published_at=event.occurred_at,
            counted=True,
            note="confirmed event source",
        )
        citation_ids_by_event.setdefault(event.id, []).append(primary_id)

        for source in grouped.get(event.id, []):
            counted = (source.source_trust_weight or 0.0) > 0
            citation_id = _add_citation(
                citations,
                event_id=event.id,
                source_type=source.source_type,
                source_name=source.source_name,
                title=source.source_title or event.title,
                url=source.source_url,
                published_at=source.source_published_at,
                counted=counted,
                note="counted corroboration" if counted else "provenance only",
            )
            citation_ids_by_event.setdefault(event.id, []).append(citation_id)

    return citations, citation_ids_by_event


def build_hotspot_briefing(db: Session, hotspot: Hotspot) -> dict:
    now = utcnow_naive()
    events = (
        db.query(Event)
        .filter(Event.cluster_id == hotspot.id, Event.is_active == True)
        .order_by(Event.occurred_at.desc(), Event.severity_score.desc())
        .all()
    )
    citations, citation_ids_by_event = _build_citations(db, events)
    recent_cutoff = now - timedelta(hours=24)
    recent_events = [event for event in events if event.occurred_at >= recent_cutoff]
    top_event = max(events, key=lambda event: event.severity_score or 0.0, default=None)
    counted_citations = [citation for citation in citations if citation["counted"]]
    counted_keys = {_citation_key(citation) for citation in counted_citations}
    provenance_only_count = len(citations) - len(counted_citations)
    location_names = sorted({_location(event) for event in events if _location(event)})

    status = hotspot.status_label or "Monitored"
    trend = hotspot.trend_state or "stable"
    headline = (
        f"{status} in {hotspot.name or 'unnamed hotspot'} with "
        f"{len(events)} confirmed active event{'s' if len(events) != 1 else ''}."
    )

    if events:
        why = (
            f"This hotspot is ranked from confirmed event density, "
            f"{_pct(hotspot.severity_score)}% severity, {_pct(hotspot.momentum_score)}% momentum, "
            f"and a {trend} trend across {len(recent_events)} event"
            f"{'s' if len(recent_events) != 1 else ''} in the last 24 hours."
        )
    else:
        why = "No active confirmed events are currently assigned to this hotspot."

    key_facts = [
        {
            "label": "Confirmed events",
            "value": str(len(events)),
            "citation_ids": [citation["id"] for citation in citations[:3]],
        },
        {
            "label": "Recent activity",
            "value": f"{len(recent_events)} events in 24h",
            "citation_ids": [citation_id for event in recent_events[:3] for citation_id in citation_ids_by_event.get(event.id, [])[:1]],
        },
        {
            "label": "Counted sources",
            "value": str(len(counted_keys)),
            "citation_ids": [citation["id"] for citation in counted_citations[:4]],
        },
        {
            "label": "Primary location",
            "value": hotspot.name or (location_names[0] if location_names else "Unspecified"),
            "citation_ids": [],
        },
    ]
    if top_event:
        key_facts.insert(1, {
            "label": "Highest severity",
            "value": f"{_pct(top_event.severity_score)}% - {_event_label(top_event)}",
            "citation_ids": citation_ids_by_event.get(top_event.id, [])[:2],
        })

    timeline = [
        {
            "event_id": event.id,
            "occurred_at": event.occurred_at,
            "title": _event_label(event),
            "event_type": event.event_type,
            "location": _location(event),
            "severity_score": event.severity_score,
            "confidence_score": event.confidence_score,
            "citation_ids": citation_ids_by_event.get(event.id, [])[:3],
        }
        for event in events[:6]
    ]

    caveats = []
    if not events:
        caveats.append("Briefing has no active confirmed member events to summarize.")
    if provenance_only_count:
        caveats.append(f"{provenance_only_count} cited source record{'s' if provenance_only_count != 1 else ''} stored as provenance only and not counted as corroboration.")
    if counted_citations and len(counted_keys) <= 1:
        caveats.append("Source corroboration is limited; treat the briefing as an early operational read.")
    if hotspot.confidence_score < 0.6:
        caveats.append("Hotspot confidence is below 60%, so location and event-link assumptions should be reviewed.")

    if top_event:
        hours = _hours_ago(top_event.occurred_at, now)
        why += f" The highest-severity member is {_event_label(top_event)}, reported about {hours} hours ago."

    return {
        "hotspot_id": hotspot.id,
        "generated_at": now,
        "headline": headline,
        "why_it_matters": why,
        "key_facts": key_facts,
        "timeline": timeline,
        "citations": citations,
        "caveats": caveats,
    }
