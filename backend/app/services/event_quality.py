from dataclasses import dataclass

from app.models import Event, EventSource, Observation
from app.services.event_display import display_for_event, is_generic_title

BROAD_PRECISIONS = {"state", "country", "area"}
SPECIFIC_PRECISIONS = {"venue", "city"}


@dataclass(frozen=True)
class EventQuality:
    quality_tier: str
    eligible_for_hotspots: bool
    eligible_for_auto_promotion: bool
    quality_reason: str

    def as_dict(self) -> dict:
        return {
            "quality_tier": self.quality_tier,
            "eligible_for_hotspots": self.eligible_for_hotspots,
            "eligible_for_auto_promotion": self.eligible_for_auto_promotion,
            "quality_reason": self.quality_reason,
        }


def _source_family(source_type: str | None, trust_tier: str | None = None) -> str:
    source = (source_type or "").lower()
    trust = (trust_tier or "").lower()
    if trust == "context" or source in {"nws", "weather"}:
        return "context"
    if source == "acled" or trust == "acled":
        return "acled"
    if source == "official" or trust == "official":
        return "official"
    if source in {"bluesky", "mastodon"}:
        return "social"
    if source == "gdelt":
        return "gdelt"
    if source == "eventregistry" or trust == "news":
        return "news"
    if trust == "weak":
        return "social"
    return source or "unknown"


def _is_broad_precision(precision: str | None) -> bool:
    return (precision or "").lower() in BROAD_PRECISIONS


def _is_gdelt_event(event: Event) -> bool:
    return (event.source_name or "").lower() == "gdelt"


def _counted_non_gdelt_families(sources: list[EventSource] | None) -> set[str]:
    families = set()
    for source in sources or []:
        if (source.source_trust_weight or 0.0) <= 0:
            continue
        family = _source_family(source.source_type, None)
        if family not in {"context", "unknown", "gdelt"}:
            families.add(family)
    return families


def event_quality(event: Event, sources: list[EventSource] | None = None) -> EventQuality:
    display = display_for_event(event, sources)
    broad = _is_broad_precision(event.location_precision)
    non_gdelt_families = _counted_non_gdelt_families(sources)

    if broad and display.is_generic_classification:
        return EventQuality(
            quality_tier="broad_detector",
            eligible_for_hotspots=False,
            eligible_for_auto_promotion=False,
            quality_reason="Broad detector classification lacks incident-level source detail.",
        )

    if display.specificity_level == "specific" and not is_generic_title(event.title):
        return EventQuality(
            quality_tier="incident_specific",
            eligible_for_hotspots=True,
            eligible_for_auto_promotion=True,
            quality_reason="Confirmed event title is incident-specific with usable location.",
        )

    if display.specificity_level == "specific" and non_gdelt_families:
        if _is_gdelt_event(event) and is_generic_title(event.title):
            return EventQuality(
                quality_tier="article_backed_classification",
                eligible_for_hotspots=True,
                eligible_for_auto_promotion=True,
                quality_reason="Detector record is backed by a specific article/source title.",
            )
        return EventQuality(
            quality_tier="incident_specific",
            eligible_for_hotspots=True,
            eligible_for_auto_promotion=True,
            quality_reason="Confirmed event has a specific source title and usable location.",
        )

    if display.specificity_level == "specific" and not _is_gdelt_event(event):
        return EventQuality(
            quality_tier="incident_specific",
            eligible_for_hotspots=True,
            eligible_for_auto_promotion=True,
            quality_reason="Confirmed event title is incident-specific with usable location.",
        )

    if non_gdelt_families and not broad:
        return EventQuality(
            quality_tier="corroborated_classification",
            eligible_for_hotspots=True,
            eligible_for_auto_promotion=True,
            quality_reason="Detector classification has independent counted source corroboration.",
        )

    if _is_gdelt_event(event):
        return EventQuality(
            quality_tier="detector_only",
            eligible_for_hotspots=False,
            eligible_for_auto_promotion=False,
            quality_reason="GDELT detector record lacks a specific article title or independent corroboration.",
        )

    return EventQuality(
        quality_tier="detector_only",
        eligible_for_hotspots=False,
        eligible_for_auto_promotion=False,
        quality_reason="Record lacks enough source specificity for hotspot scoring.",
    )


def observation_quality(observation: Observation, *, source_type: str | None, trust_tier: str | None = None) -> EventQuality:
    family = _source_family(source_type, trust_tier)
    broad = _is_broad_precision(observation.location_precision)
    title_specific = not is_generic_title(observation.title)

    if broad:
        return EventQuality(
            quality_tier="broad_detector" if family == "gdelt" else "detector_only",
            eligible_for_hotspots=False,
            eligible_for_auto_promotion=False,
            quality_reason="Observation location is too broad for confirmed event promotion.",
        )
    if family in {"context", "social", "unknown"}:
        return EventQuality(
            quality_tier="detector_only",
            eligible_for_hotspots=False,
            eligible_for_auto_promotion=False,
            quality_reason="Observation source family cannot create confirmed events by itself.",
        )
    if title_specific and observation.location_precision in SPECIFIC_PRECISIONS:
        return EventQuality(
            quality_tier="incident_specific",
            eligible_for_hotspots=True,
            eligible_for_auto_promotion=True,
            quality_reason="Observation has a specific title and usable city/venue location.",
        )
    return EventQuality(
        quality_tier="detector_only",
        eligible_for_hotspots=False,
        eligible_for_auto_promotion=False,
        quality_reason="Observation lacks a specific incident title.",
    )
