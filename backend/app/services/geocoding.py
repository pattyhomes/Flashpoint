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
    def __init__(self, gazetteer_path: Path | None = None, aliases_path: Path | None = None):
        self.gazetteer_path = gazetteer_path or Path(__file__).resolve().parents[1] / "data" / "us_locations.csv"
        self.aliases_path = aliases_path or Path(__file__).resolve().parents[1] / "data" / "us_location_aliases.csv"

    @cached_property
    def rows(self) -> list[dict]:
        with self.gazetteer_path.open(newline="", encoding="utf-8") as fh:
            return list(csv.DictReader(fh))

    @cached_property
    def aliases(self) -> list[dict]:
        if not self.aliases_path.exists():
            return []
        with self.aliases_path.open(newline="", encoding="utf-8") as fh:
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
            alias = self._extract_alias(text)
            if alias is not None:
                return alias
            city, state = self._extract_city_state(text)
        if not city:
            if text:
                return self._extract_county_state(text)
            return None

        matches = [
            row for row in self.rows
            if _row_kind(row) != "county" and _row_city(row).lower() == city.lower()
        ]
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
            if _row_kind(row) == "county" or not _row_city(row):
                continue
            city = re.escape(_row_city(row))
            state = row["state"]
            state_name = next((name for name, abbr in _STATE_NAMES.items() if abbr == state), None)
            state_pattern = rf"(?:{state}|{re.escape(state_name.title()) if state_name else state})"
            if re.search(rf"\b{city}\s*,?\s+{state_pattern}\b", normalized, re.IGNORECASE):
                return _row_city(row), state
        for row in self.rows:
            if _row_kind(row) == "county" or not _row_city(row):
                continue
            if re.search(rf"\b{re.escape(_row_city(row))}\b", normalized, re.IGNORECASE):
                return _row_city(row), None
        return None, None

    def _extract_county_state(self, text: str) -> GeocodeResult | None:
        normalized = re.sub(r"\s+", " ", text)
        for row in self.rows:
            if _row_kind(row) != "county":
                continue
            county = re.escape(row["county"])
            state = row["state"]
            state_name = next((name for name, abbr in _STATE_NAMES.items() if abbr == state), None)
            state_pattern = rf"(?:{state}|{re.escape(state_name.title()) if state_name else state})"
            if re.search(rf"\b{county}\s+County\s*,?\s+{state_pattern}\b", normalized, re.IGNORECASE):
                return GeocodeResult(
                    city=None,
                    county=row["county"],
                    state=row["state"],
                    country="US",
                    latitude=float(row["latitude"]),
                    longitude=float(row["longitude"]),
                    precision="county",
                    confidence=0.76,
                    reason="gazetteer:county_state",
                )
        return None

    def _extract_alias(self, text: str) -> GeocodeResult | None:
        normalized = re.sub(r"\s+", " ", text)
        for alias in self.aliases:
            if not re.search(rf"\b{re.escape(alias['alias'])}\b", normalized, re.IGNORECASE):
                continue
            state = _normalize_state(alias.get("state"))
            city = _clean(alias.get("city"))
            county = _clean(alias.get("county"))
            if city:
                match = self.resolve(city=city, state=state)
                if match:
                    return GeocodeResult(
                        city=match.city,
                        county=county or match.county,
                        state=match.state,
                        country=match.country,
                        latitude=match.latitude,
                        longitude=match.longitude,
                        precision=match.precision,
                        confidence=0.88,
                        reason="alias:city_state",
                    )
            if county and state:
                match = self._county_match(county, state)
                if match:
                    return match
        return None

    def _county_match(self, county: str, state: str) -> GeocodeResult | None:
        matches = [
            row for row in self.rows
            if _row_kind(row) == "county" and row["county"].lower() == county.lower() and row["state"] == state
        ]
        if len(matches) != 1:
            return None
        row = matches[0]
        return GeocodeResult(
            city=None,
            county=row["county"],
            state=row["state"],
            country="US",
            latitude=float(row["latitude"]),
            longitude=float(row["longitude"]),
            precision="county",
            confidence=0.76,
            reason="alias:county_state",
        )


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


def _row_kind(row: dict) -> str:
    return (row.get("kind") or row.get("precision") or "city").lower()


def _row_city(row: dict) -> str:
    return row.get("city") or row.get("name") or ""
