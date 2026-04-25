from datetime import datetime, timezone


def utcnow() -> datetime:
    """Return the current UTC time as a timezone-aware datetime.

    Use at API serialization boundaries (JSON output, log lines) where the
    explicit tz offset is helpful for downstream consumers.
    """
    return datetime.now(timezone.utc)


def utcnow_naive() -> datetime:
    """Return the current UTC time as a naive datetime.

    Use at the database boundary. The existing SQLite schema uses
    `DateTime` (no `timezone=True`), and existing rows were written by
    the deprecated `datetime.utcnow()` (also naive). Inserting a tz-aware
    value here would serialize with a `+00:00` suffix and break string-sort
    comparisons against the legacy rows. This helper preserves the on-disk
    representation while still routing every call through one place.
    """
    return datetime.now(timezone.utc).replace(tzinfo=None)


def to_utc(dt: datetime) -> datetime:
    """Coerce a datetime to timezone-aware UTC.

    Naive inputs are assumed to be UTC (every project naive datetime is
    UTC by convention — DB rows, in-process timestamps, ingest fallbacks).
    Tz-aware inputs are converted to UTC.
    """
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def to_iso(dt: datetime) -> str:
    """Format a datetime as an ISO 8601 string."""
    return dt.isoformat()


def to_iso_z(dt: datetime) -> str:
    """Format a datetime as ISO 8601 with a literal 'Z' UTC suffix.

    Produces e.g. '2025-04-25T12:34:56.789Z' regardless of whether the
    input was naive or tz-aware — required by the Desktop PRD §5/§26
    truthfulness contract on the /health timestamp field.
    """
    iso = to_utc(dt).isoformat()
    return iso.replace("+00:00", "Z")
