# Confidence scoring: adjusts how much we trust an event based on source reliability
# and whether multiple sources corroborate it.
# TODO: implement multi-source corroboration boost.


def adjust_confidence(event) -> float:
    """Return an adjusted confidence score (0.0–1.0) for the given event."""
    return event.confidence
