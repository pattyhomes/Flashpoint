from collections import Counter
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from app.models import Event, EventSource, Hotspot
from app.services.event_display import EventDisplay, display_for_event
from app.services.intelligence import source_family
from app.utils.time import utcnow_naive

CITATION_RETURN_LIMIT = 30


def _pct(value: float | None) -> int:
    return round(max(0.0, min(1.0, value or 0.0)) * 100)


def _location(event: Event) -> str:
    return ", ".join(part for part in [event.city, event.state] if part) or event.country


def _event_label(event: Event, display_by_event: dict[int, EventDisplay] | None = None) -> str:
    display = (display_by_event or {}).get(event.id)
    if display:
        return display.display_title
    return event.title


def _hours_ago(value: datetime, now: datetime) -> int:
    return max(0, round((now - value).total_seconds() / 3600))


def _avg(values: list[float]) -> float:
    if not values:
        return 0.0
    return round(sum(values) / len(values), 3)


def _change_percent(current: int, previous: int) -> float | None:
    if previous == 0:
        return None if current else 0.0
    return round(((current - previous) / previous) * 100, 1)


def _source_label(source_type: str | None) -> str:
    family = source_family(source_type, None)
    return family if family != "unknown" else (source_type or "unknown")


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


def _build_citations(events: list[Event], grouped: dict[int, list[EventSource]]) -> tuple[list[dict], dict[int, list[int]]]:
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


def _top_locations(events: list[Event], limit: int = 4) -> list[str]:
    return [location for location, _count in Counter(_location(event) for event in events).most_common(limit)]


def _dominant_event_types(events: list[Event], limit: int = 4) -> list[dict]:
    counter = Counter(event.event_type for event in events)
    return [
        {"label": event_type, "value": str(count), "citation_ids": []}
        for event_type, count in counter.most_common(limit)
    ]


def _event_ref(event: Event, citation_ids_by_event: dict[int, list[int]], display_by_event: dict[int, EventDisplay]) -> dict:
    display = display_by_event[event.id]
    return {
        "event_id": event.id,
        "occurred_at": event.occurred_at,
        "title": event.title,
        "display_title": display.display_title,
        "event_type": event.event_type,
        "location": _location(event),
        "severity_score": event.severity_score,
        "confidence_score": event.confidence_score,
        "specificity_level": display.specificity_level,
        "specificity_reason": display.specificity_reason,
        "is_generic_classification": display.is_generic_classification,
        "citation_ids": citation_ids_by_event.get(event.id, [])[:3],
    }


def _representative_events(
    events: list[Event],
    citation_ids_by_event: dict[int, list[int]],
    display_by_event: dict[int, EventDisplay],
    limit: int = 3,
) -> list[dict]:
    ranked = _representative_event_objects(events, display_by_event, limit=limit)
    return [
        _event_ref(event, citation_ids_by_event, display_by_event)
        for event in ranked[:limit]
    ]


def _window_score(events: list[Event]) -> float:
    if not events:
        return 0.0
    return round(min(1.0, sum(event.severity_score or 0.0 for event in events) / max(1, len(events))), 3)


def _trend_phrase(trend: str, current_count: int, previous_count: int) -> str:
    if trend == "escalating":
        return f"Escalating: {current_count} confirmed events in the last 24 hours versus {previous_count} in the prior 24 hours."
    if trend == "declining":
        return f"Declining: {current_count} confirmed events in the last 24 hours versus {previous_count} in the prior 24 hours."
    return f"Stable: {current_count} confirmed events in the last 24 hours versus {previous_count} in the prior 24 hours."


def _trend_with_article(trend: str) -> str:
    return f"an {trend}" if trend == "escalating" else f"a {trend}"


def _build_why_now(
    *,
    hotspot: Hotspot,
    events: list[Event],
    now: datetime,
    citation_ids_by_event: dict[int, list[int]],
    display_by_event: dict[int, EventDisplay],
) -> tuple[dict, list[Event], list[Event]]:
    current_start = now - timedelta(hours=24)
    previous_start = now - timedelta(hours=48)
    current_events = [event for event in events if event.occurred_at >= current_start]
    previous_events = [event for event in events if previous_start <= event.occurred_at < current_start]
    current_avg_sev = _avg([event.severity_score or 0.0 for event in current_events])
    previous_avg_sev = _avg([event.severity_score or 0.0 for event in previous_events])
    previous_activity = _window_score(previous_events)
    change_count = len(current_events) - len(previous_events)
    trend = hotspot.trend_state or "stable"

    drivers = [
        {
            "label": "24h volume",
            "value": f"{len(current_events)} vs {len(previous_events)}",
            "detail": "Confirmed events in the current 24-hour window compared with the prior 24-hour window.",
            "citation_ids": [citation_id for event in current_events[:3] for citation_id in citation_ids_by_event.get(event.id, [])[:1]],
        },
        {
            "label": "Severity",
            "value": f"{_pct(current_avg_sev / 1.0)}%",
            "detail": f"Average severity changed by {round(current_avg_sev - previous_avg_sev, 3):+0.3f} versus the prior window.",
            "citation_ids": [citation_id for event in _representative_event_objects(current_events, display_by_event, limit=2) for citation_id in citation_ids_by_event.get(event.id, [])[:1]],
        },
        {
            "label": "Momentum",
            "value": f"{_pct(hotspot.momentum_score)}%",
            "detail": f"Momentum changed by {round((hotspot.momentum_score or 0.0) - previous_activity, 3):+0.3f} against prior-window activity.",
            "citation_ids": [],
        },
    ]
    top_event = next(iter(_representative_event_objects(current_events or events, display_by_event, limit=1)), None)
    if top_event:
        drivers.append({
            "label": "Top driver",
            "value": _event_label(top_event, display_by_event),
            "detail": f"{_pct(top_event.severity_score)}% severity, {_location(top_event)}. {display_by_event[top_event.id].specificity_reason}",
            "citation_ids": citation_ids_by_event.get(top_event.id, [])[:2],
        })

    summary = _trend_phrase(trend, len(current_events), len(previous_events))
    if current_events:
        summary += f" Dominant current activity is {Counter(event.event_type for event in current_events).most_common(1)[0][0]}."
    else:
        summary += " No confirmed member event occurred in the current 24-hour window."

    return {
        "summary": summary,
        "current_24h_count": len(current_events),
        "previous_24h_count": len(previous_events),
        "change_count": change_count,
        "change_percent": _change_percent(len(current_events), len(previous_events)),
        "current_avg_severity": current_avg_sev,
        "previous_avg_severity": previous_avg_sev,
        "severity_change": round(current_avg_sev - previous_avg_sev, 3),
        "momentum_score": round(hotspot.momentum_score or 0.0, 3),
        "momentum_change": round((hotspot.momentum_score or 0.0) - previous_activity, 3),
        "trend_explanation": _trend_phrase(trend, len(current_events), len(previous_events)),
        "drivers": drivers,
    }, current_events, previous_events


def _representative_event_objects(
    events: list[Event],
    display_by_event: dict[int, EventDisplay],
    limit: int = 3,
) -> list[Event]:
    return sorted(
        events,
        key=lambda event: (
            display_by_event[event.id].explainability_score,
            event.severity_score or 0.0,
            event.confidence_score or 0.0,
            event.occurred_at,
        ),
        reverse=True,
    )[:limit]


def _build_timeline_groups(
    *,
    events: list[Event],
    now: datetime,
    citation_ids_by_event: dict[int, list[int]],
    display_by_event: dict[int, EventDisplay],
) -> list[dict]:
    windows = [
        ("Last 6h", now - timedelta(hours=6), now),
        ("6-24h", now - timedelta(hours=24), now - timedelta(hours=6)),
        ("Prior 24h", now - timedelta(hours=48), now - timedelta(hours=24)),
        ("Older active", None, now - timedelta(hours=48)),
    ]
    groups = []
    for label, start, end in windows:
        if start is None:
            bucket = [event for event in events if event.occurred_at < end]
        else:
            bucket = [event for event in events if start <= event.occurred_at < end]
        if not bucket:
            continue
        dominant = Counter(event.event_type for event in bucket).most_common(1)[0][0]
        reps = _representative_events(bucket, citation_ids_by_event, display_by_event, limit=3)
        citation_ids = []
        for rep in reps:
            citation_ids.extend(rep["citation_ids"])
        groups.append({
            "label": label,
            "start_at": start,
            "end_at": end,
            "event_count": len(bucket),
            "dominant_event_type": dominant,
            "locations": _top_locations(bucket, limit=3),
            "summary": f"{len(bucket)} confirmed {dominant} event{'s' if len(bucket) != 1 else ''} across {', '.join(_top_locations(bucket, limit=2))}.",
            "representative_events": reps,
            "citation_ids": citation_ids[:6],
        })
    return groups


def _build_specificity_assessment(events: list[Event], display_by_event: dict[int, EventDisplay]) -> dict:
    displays = [display_by_event[event.id] for event in events]
    incident_specific_count = sum(1 for display in displays if display.specificity_level == "specific")
    classified_count = sum(1 for display in displays if display.is_generic_classification)
    low_location_count = sum(1 for display in displays if display.specificity_level == "low_location")
    source_gap_count = sum(1 for display in displays if display.specificity_level == "source_gap")
    weak_count = classified_count + low_location_count + source_gap_count
    low_specificity = bool(events) and (incident_specific_count == 0 or weak_count / len(events) >= 0.5)
    if not events:
        summary = "No active confirmed events are assigned, so incident specificity cannot be assessed."
    elif low_specificity:
        summary = "High volume, but low incident specificity: most records are broad classifications without clean incident descriptions."
    else:
        summary = f"{incident_specific_count} incident-specific records are available for explanation."
    return {
        "summary": summary,
        "incident_specific_count": incident_specific_count,
        "classified_count": classified_count,
        "low_location_count": low_location_count,
        "source_gap_count": source_gap_count,
        "low_specificity": low_specificity,
    }


def _build_source_assessment(
    *,
    hotspot: Hotspot,
    citations: list[dict],
    citation_count_returned: int,
) -> tuple[dict, list[str]]:
    counted = [citation for citation in citations if citation["counted"]]
    provenance_only_count = len(citations) - len(counted)
    families = sorted({_source_label(citation.get("source_type")) for citation in counted})
    notes = []
    if families:
        notes.append(f"Counted corroboration spans {', '.join(families)}.")
    else:
        notes.append("No counted corroborating source family is attached to the active member events.")
    if provenance_only_count:
        notes.append(f"{provenance_only_count} provenance-only source record{'s' if provenance_only_count != 1 else ''} retained but not counted.")
    if hotspot.confidence_score < 0.6:
        notes.append("Hotspot confidence is below 60%; review event links and location quality before treating this as firm.")
    summary = (
        f"{len(families)} counted source famil{'ies' if len(families) != 1 else 'y'}, "
        f"{len(counted)} counted citation{'s' if len(counted) != 1 else ''}, "
        f"{provenance_only_count} provenance-only."
    )
    return {
        "summary": summary,
        "counted_source_families": families,
        "counted_source_count": len(families),
        "counted_citation_count": len(counted),
        "provenance_only_count": provenance_only_count,
        "citation_count_returned": citation_count_returned,
        "citation_count_total": len(citations),
        "notes": notes,
    }, notes


def _cap_citations(citations: list[dict], referenced_ids: set[int], limit: int = CITATION_RETURN_LIMIT) -> list[dict]:
    required = [citation for citation in citations if citation["id"] in referenced_ids]
    required_ids = {citation["id"] for citation in required}
    remaining = [citation for citation in citations if citation["id"] not in required_ids]
    remaining.sort(key=lambda citation: (
        not citation["counted"],
        -(citation["published_at"].timestamp() if citation.get("published_at") else 0),
        citation["id"],
    ))
    allowed_extra = max(0, limit - len(required))
    return sorted(required + remaining[:allowed_extra], key=lambda citation: citation["id"])


def _collect_referenced_ids(*values) -> set[int]:
    ids: set[int] = set()

    def visit(value):
        if isinstance(value, dict):
            for key, inner in value.items():
                if key == "citation_ids" and isinstance(inner, list):
                    ids.update(item for item in inner if isinstance(item, int))
                else:
                    visit(inner)
        elif isinstance(value, list):
            for inner in value:
                visit(inner)

    for value in values:
        visit(value)
    return ids


def build_hotspot_briefing(db: Session, hotspot: Hotspot) -> dict:
    now = utcnow_naive()
    events = (
        db.query(Event)
        .filter(Event.cluster_id == hotspot.id, Event.is_active == True)
        .order_by(Event.occurred_at.desc(), Event.severity_score.desc())
        .all()
    )
    grouped_sources = _source_rows(db, events)
    citations, citation_ids_by_event = _build_citations(events, grouped_sources)
    display_by_event = {
        event.id: display_for_event(event, grouped_sources.get(event.id, []))
        for event in events
    }
    specificity_assessment = _build_specificity_assessment(events, display_by_event)
    why_now, recent_events, previous_events = _build_why_now(
        hotspot=hotspot,
        events=events,
        now=now,
        citation_ids_by_event=citation_ids_by_event,
        display_by_event=display_by_event,
    )
    top_event = next(iter(_representative_event_objects(events, display_by_event, limit=1)), None)
    counted_citations = [citation for citation in citations if citation["counted"]]
    counted_families = {_source_label(citation.get("source_type")) for citation in counted_citations}
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
            f"and {_trend_with_article(trend)} trend across {len(recent_events)} event"
            f"{'s' if len(recent_events) != 1 else ''} in the last 24 hours."
        )
        if specificity_assessment["low_specificity"]:
            why = f"{specificity_assessment['summary']} {why}"
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
            "value": str(len(counted_families)),
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
            "label": "Representative event",
            "value": f"{_pct(top_event.severity_score)}% - {_event_label(top_event, display_by_event)}",
            "citation_ids": citation_ids_by_event.get(top_event.id, [])[:2],
        })

    timeline = [
        {
            "event_id": event.id,
            "occurred_at": event.occurred_at,
            "title": event.title,
            "display_title": _event_label(event, display_by_event),
            "event_type": event.event_type,
            "location": _location(event),
            "severity_score": event.severity_score,
            "confidence_score": event.confidence_score,
            "specificity_level": display_by_event[event.id].specificity_level,
            "specificity_reason": display_by_event[event.id].specificity_reason,
            "is_generic_classification": display_by_event[event.id].is_generic_classification,
            "citation_ids": citation_ids_by_event.get(event.id, [])[:3],
        }
        for event in events[:6]
    ]

    timeline_groups = _build_timeline_groups(
        events=events,
        now=now,
        citation_ids_by_event=citation_ids_by_event,
        display_by_event=display_by_event,
    )
    what_happened = {
        "summary": (
            f"{len(events)} confirmed active events across {', '.join(_top_locations(events, limit=3))}."
            if events else "No active confirmed events are assigned to this hotspot."
        ),
        "dominant_event_types": _dominant_event_types(events),
        "affected_locations": _top_locations(events, limit=6),
        "timeline_groups": timeline_groups,
    }

    caveats = []
    if not events:
        caveats.append("Briefing has no active confirmed member events to summarize.")
    if provenance_only_count:
        caveats.append(f"{provenance_only_count} cited source record{'s' if provenance_only_count != 1 else ''} stored as provenance only and not counted as corroboration.")
    if counted_citations and len(counted_families) <= 1:
        caveats.append("Source corroboration is limited; treat the briefing as an early operational read.")
    if hotspot.confidence_score < 0.6:
        caveats.append("Hotspot confidence is below 60%, so location and event-link assumptions should be reviewed.")
    if specificity_assessment["low_specificity"]:
        caveats.insert(0, specificity_assessment["summary"])

    if top_event:
        hours = _hours_ago(top_event.occurred_at, now)
        if display_by_event[top_event.id].is_generic_classification:
            why += f" The most explainable representative record is still a classification: {_event_label(top_event, display_by_event)}, reported about {hours} hours ago."
        else:
            why += f" The most explainable representative event is {_event_label(top_event, display_by_event)}, reported about {hours} hours ago."

    referenced_ids = _collect_referenced_ids(key_facts, timeline, why_now, what_happened)
    capped_citations = _cap_citations(citations, referenced_ids)
    source_assessment, source_notes = _build_source_assessment(
        hotspot=hotspot,
        citations=citations,
        citation_count_returned=len(capped_citations),
    )
    model_packet = {
        "version": "hotspot-briefing-v2",
        "hotspot": {
            "id": hotspot.id,
            "name": hotspot.name,
            "status": hotspot.status_label,
            "trend": trend,
            "priority_score": hotspot.priority_score,
            "severity_score": hotspot.severity_score,
            "momentum_score": hotspot.momentum_score,
            "confidence_score": hotspot.confidence_score,
        },
        "why_now": why_now,
        "what_happened": {
            "summary": what_happened["summary"],
            "timeline_groups": [
                {
                    "label": group["label"],
                    "summary": group["summary"],
                    "event_count": group["event_count"],
                    "citation_ids": group["citation_ids"],
                }
                for group in timeline_groups
            ],
        },
        "source_assessment": source_assessment,
        "specificity_assessment": specificity_assessment,
        "caveats": caveats + source_notes,
    }

    return {
        "hotspot_id": hotspot.id,
        "generated_at": now,
        "headline": headline,
        "why_it_matters": why,
        "key_facts": key_facts,
        "timeline": timeline,
        "citations": capped_citations,
        "caveats": caveats,
        "why_now": why_now,
        "what_happened": what_happened,
        "source_assessment": source_assessment,
        "specificity_assessment": specificity_assessment,
        "model_packet": model_packet,
    }
