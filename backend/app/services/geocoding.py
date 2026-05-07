import csv
import re
from dataclasses import dataclass
from functools import cached_property
from pathlib import Path


_STATE_NAMES = {
    "alabama": "AL", "alaska": "AK", "arizona": "AZ", "arkansas": "AR",
    "california": "CA", "colorado": "CO", "connecticut": "CT", "delaware": "DE",
    "district of columbia": "DC", "florida": "FL", "georgia": "GA", "hawaii": "HI",
    "idaho": "ID", "illinois": "IL", "indiana": "IN", "iowa": "IA",
    "kansas": "KS", "kentucky": "KY", "louisiana": "LA", "maine": "ME",
    "maryland": "MD", "massachusetts": "MA", "michigan": "MI", "minnesota": "MN",
    "mississippi": "MS", "missouri": "MO", "montana": "MT", "nebraska": "NE",
    "nevada": "NV", "new hampshire": "NH", "new jersey": "NJ", "new mexico": "NM",
    "new york": "NY", "north carolina": "NC", "north dakota": "ND", "ohio": "OH",
    "oklahoma": "OK", "oregon": "OR", "pennsylvania": "PA", "rhode island": "RI",
    "south carolina": "SC", "south dakota": "SD", "tennessee": "TN", "texas": "TX",
    "utah": "UT", "vermont": "VT", "virginia": "VA", "washington": "WA",
    "west virginia": "WV", "wisconsin": "WI", "wyoming": "WY",
}


@dataclass(frozen=True)
class GeocodeResult:
    city: str | None
    county: str | None
    state: str | None
    country: str
    latitude: float
    longitude: float
    precision: str
    confidence: float
    reason: str


class LocalGeocoder:
    def __init__(self, gazetteer_path: Path | None = None):
        self.gazetteer_path = gazetteer_path or Path(__file__).resolve().parents[1] / "data" / "us_locations.csv"

    @cached_property
    def rows(self) -> list[dict]:
        with self.gazetteer_path.open(newline="", encoding="utf-8") as fh:
            return list(csv.DictReader(fh))

    def resolve(
        self,
        *,
        text: str | None = None,
        city: str | None = None,
        state: str | None = None,
    ) -> GeocodeResult | None:
        city = _clean(city)
        state = _normalize_state(state)
        if not city and text:
            city, state = self._extract_city_state(text)
        if not city:
            return None

        matches = [row for row in self.rows if row["city"].lower() == city.lower()]
        if state:
            matches = [row for row in matches if row["state"] == state]
        if len(matches) != 1:
            return None
        row = matches[0]
        reason = "gazetteer:city_state" if state else "gazetteer:unique_city"
        return GeocodeResult(
            city=row["city"],
            county=row["county"],
            state=row["state"],
            country="US",
            latitude=float(row["latitude"]),
            longitude=float(row["longitude"]),
            precision="city",
            confidence=0.9 if state else 0.72,
            reason=reason,
        )

    def _extract_city_state(self, text: str) -> tuple[str | None, str | None]:
        normalized = re.sub(r"\s+", " ", text)
        for row in self.rows:
            city = re.escape(row["city"])
            state = row["state"]
            state_name = next((name for name, abbr in _STATE_NAMES.items() if abbr == state), None)
            state_pattern = rf"(?:{state}|{re.escape(state_name.title()) if state_name else state})"
            if re.search(rf"\b{city}\s*,?\s+{state_pattern}\b", normalized, re.IGNORECASE):
                return row["city"], state
        for row in self.rows:
            if re.search(rf"\b{re.escape(row['city'])}\b", normalized, re.IGNORECASE):
                return row["city"], None
        return None, None


def _clean(value: str | None) -> str | None:
    if not value:
        return None
    return re.sub(r"\s+", " ", value).strip() or None


def _normalize_state(value: str | None) -> str | None:
    cleaned = _clean(value)
    if not cleaned:
        return None
    if len(cleaned) == 2:
        return cleaned.upper()
    return _STATE_NAMES.get(cleaned.lower())
