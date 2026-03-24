"""
GDELT 2.0 Event CSV ingestion source.

Fetches 15-minute event export files from the GDELT project, filters to U.S. unrest
events (CAMEO root codes 14, 17, 18), and normalises each row into an EventCreate.

GDELT 2.0 export files are tab-separated with no header row. Column positions are
documented at https://www.gdeltproject.org/data/documentation/GDELT-Event_Codebook-V2.0.pdf
"""

import csv
import io
import json
import zipfile
from datetime import datetime, timedelta

import httpx

from app.schemas import EventCreate

# ---------------------------------------------------------------------------
# GDELT 2.0 export CSV column indices (0-based, no header row, tab-delimited)
# ---------------------------------------------------------------------------
_C = {
    "GlobalEventID":        0,
    "Day":                  1,   # YYYYMMDD
    "Actor1Name":           6,
    "EventCode":           26,   # Full CAMEO code, e.g. "145"
    "EventRootCode":       28,   # 2-digit root, e.g. "14"
    "GoldsteinScale":      30,   # float; negative = destabilising
    "NumSources":          32,
    # GDELT 2.0 has 61 columns. Each Geo block is 8 fields (Type, FullName,
    # CountryCode, ADM1Code, FeatureID, Lat, Long, ObjectID). There are
    # 3 geo blocks (Actor1, Actor2, Action) at offsets 35, 43, 51.
    "ActionGeo_FullName":  52,
    "ActionGeo_CountryCode": 53,
    "ActionGeo_ADM1Code":  54,   # e.g. "USWA" → state "WA"
    "ActionGeo_Lat":       56,
    "ActionGeo_Long":      57,
    "SOURCEURL":           60,
}

# CAMEO root codes included in V1 filter
_UNREST_ROOT_CODES = {"14", "17", "18"}

# event_type mapping
_ROOT_TO_EVENT_TYPE = {
    "14": "protest",
    "17": "unrest",
    "18": "violence",
}

# Root-level label for display titles — intentionally generic to avoid overclaiming
_ROOT_TO_LABEL = {
    "14": "protest",
    "17": "civil unrest",
    "18": "violence",
}


# ---------------------------------------------------------------------------
# URL construction
# ---------------------------------------------------------------------------

def _floor_15(dt: datetime) -> datetime:
    """Floor a naive UTC datetime to the previous 15-minute boundary."""
    return dt.replace(minute=(dt.minute // 15) * 15, second=0, microsecond=0)


def _build_urls(since: datetime | None) -> list[str]:
    """
    Return GDELT 2.0 export CSV zip URLs to fetch.

    - since=None (first run): last 96 windows = 24 hours of seed data
    - since=datetime: windows from floor_15(since) to upper bound,
      capped at 96 windows (24h max)

    Upper bound = floor_15(now) - 15 min (publication buffer — latest file
    may not yet be available). Overlap between runs is safe because dedup
    uses source_id = "gdelt-{GlobalEventID}".
    """
    BASE = "http://data.gdeltproject.org/gdeltv2/"
    now = datetime.utcnow()
    upper = _floor_15(now) - timedelta(minutes=15)

    if since is None:
        lower = upper - timedelta(minutes=15 * 95)   # 96 windows inclusive
    else:
        lower = _floor_15(since)
        # Cap at 96 windows looking backward from upper
        earliest_allowed = upper - timedelta(minutes=15 * 95)
        if lower < earliest_allowed:
            lower = earliest_allowed

    urls = []
    t = lower
    while t <= upper:
        urls.append(BASE + t.strftime("%Y%m%d%H%M%S") + ".export.CSV.zip")
        t += timedelta(minutes=15)
    return urls


# ---------------------------------------------------------------------------
# HTTP fetch + parse
# ---------------------------------------------------------------------------

def _fetch_file(url: str) -> list[list[str]]:
    """Download a GDELT export zip, return list of split TSV rows."""
    response = httpx.get(url, timeout=30, follow_redirects=True)
    response.raise_for_status()
    with zipfile.ZipFile(io.BytesIO(response.content)) as zf:
        name = next(n for n in zf.namelist() if n.upper().endswith(".CSV"))
        with zf.open(name) as f:
            reader = csv.reader(io.TextIOWrapper(f, encoding="utf-8"), delimiter="\t")
            return [row for row in reader if len(row) >= 61]


# ---------------------------------------------------------------------------
# Row normalisation
# ---------------------------------------------------------------------------

def _row_to_event(row: list[str]) -> EventCreate | None:
    """
    Map a GDELT row to EventCreate. Returns None if the row should be skipped.
    Wrapped in a try/except by the caller — malformed rows are silently dropped.
    """
    # Filter: US only, relevant CAMEO root code
    if row[_C["ActionGeo_CountryCode"]] != "US":
        return None
    root_code = row[_C["EventRootCode"]].strip()
    if root_code not in _UNREST_ROOT_CODES:
        return None

    # Require valid coordinates; skip null-island (0,0)
    try:
        lat = float(row[_C["ActionGeo_Lat"]])
        lon = float(row[_C["ActionGeo_Long"]])
    except (ValueError, TypeError):
        return None
    if lat == 0.0 and lon == 0.0:
        return None

    # occurred_at: GDELT Day is YYYYMMDD; use noon UTC (no sub-day precision)
    day_str = row[_C["Day"]].strip()
    occurred_at = datetime.strptime(day_str, "%Y%m%d").replace(hour=12)

    # Location
    full_name = row[_C["ActionGeo_FullName"]].strip()
    adm1 = row[_C["ActionGeo_ADM1Code"]].strip()
    parts = [p.strip() for p in full_name.split(",")]
    city = parts[0] if parts and parts[0] else None
    state = adm1[2:] if adm1.startswith("US") and len(adm1) == 4 else None

    # Event type
    event_type = _ROOT_TO_EVENT_TYPE.get(root_code, "unrest")

    # Title — root-level template only; no CAMEO sub-code phrases, no actor attribution
    event_code = row[_C["EventCode"]].strip()
    actor = row[_C["Actor1Name"]].strip()
    label = _ROOT_TO_LABEL.get(root_code, "unrest")
    location_label = city or (full_name.split(",")[0].strip() if full_name else "unknown location")
    title = f"{label.capitalize()} — {location_label}"

    # Severity: GoldsteinScale is -10 (destabilising) to +10 (stabilising)
    # Map to 0–1 where 1 = most destabilising
    try:
        goldstein = float(row[_C["GoldsteinScale"]])
    except (ValueError, TypeError):
        goldstein = 0.0
    severity = max(0.0, min(1.0, (-goldstein + 10.0) / 20.0))

    # Confidence: scaled from NumSources (0.5 base + 0.1 per additional source)
    try:
        num_sources = int(row[_C["NumSources"]])
    except (ValueError, TypeError):
        num_sources = 1
    confidence = min(1.0, 0.5 + (num_sources - 1) * 0.1)

    source_url = row[_C["SOURCEURL"]].strip() or None
    global_event_id = row[_C["GlobalEventID"]].strip()

    return EventCreate(
        source_id=f"gdelt-{global_event_id}",
        title=title,
        event_type=event_type,
        latitude=lat,
        longitude=lon,
        city=city,
        state=state,
        country="US",
        occurred_at=occurred_at,
        source_name="gdelt",
        source_url=source_url,
        source_count=num_sources,
        confidence_score=confidence,
        severity_score=severity,
        raw_payload_json=json.dumps({
            "event_code": event_code,
            "root_code": root_code,
            "actor1": actor,
            "goldstein": goldstein,
        }),
    )


# ---------------------------------------------------------------------------
# Public interface
# ---------------------------------------------------------------------------

class GdeltSource:
    def fetch(self, since: datetime | None = None) -> list[EventCreate]:
        """
        Fetch and normalise GDELT events.

        since: last successful GDELT run's finished_at (naive UTC).
               Pass None on first run to trigger the 24-hour bootstrap window.
        """
        urls = _build_urls(since)
        print(f"[gdelt] Fetching {len(urls)} file(s) "
              f"({'first run, 24h seed' if since is None else f'since {since.isoformat()}'}).")

        events: list[EventCreate] = []
        for url in urls:
            try:
                rows = _fetch_file(url)
            except Exception as e:
                # Individual file failures are logged but do not abort the run
                print(f"[gdelt] Skipping {url.split('/')[-1]}: {e}")
                continue
            for row in rows:
                try:
                    event = _row_to_event(row)
                    if event is not None:
                        events.append(event)
                except Exception:
                    pass  # Malformed row — skip silently

        print(f"[gdelt] {len(events)} events after filtering.")
        return events
