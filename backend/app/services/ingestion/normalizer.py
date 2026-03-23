from app.schemas import EventCreate


def normalize(raw: dict) -> EventCreate | None:
    """
    Convert a raw dict from an external source into an EventCreate.
    Returns None if the data is missing required fields.

    Each real data source will need its own normalization logic here
    or in a source-specific subclass.
    """
    # TODO: implement per-source normalization
    return None
