#!/usr/bin/env python3
import csv
import io
import re
import urllib.request
import zipfile
from pathlib import Path


PLACE_URL = "https://www2.census.gov/geo/docs/maps-data/data/gazetteer/2020_Gazetteer/2020_Gaz_place_national.zip"
COUNTY_URL = "https://www2.census.gov/geo/docs/maps-data/data/gazetteer/2020_Gazetteer/2020_Gaz_counties_national.zip"
OUTPUT_PATH = Path(__file__).resolve().parents[1] / "backend" / "app" / "data" / "us_locations.csv"

PLACE_SUFFIXES = (
    " city",
    " town",
    " village",
    " borough",
    " municipality",
    " CDP",
    " urban county",
    " unified government",
    " consolidated government",
    " metro government",
    " metropolitan government",
)


def main():
    rows = []
    rows.extend(_place_rows(_read_zipped_tsv(PLACE_URL)))
    rows.extend(_county_rows(_read_zipped_tsv(COUNTY_URL)))
    rows.sort(key=lambda row: (row["state"], row["kind"], row["city"] or row["county"]))
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT_PATH.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(
            fh,
            fieldnames=["kind", "city", "state", "county", "latitude", "longitude", "population"],
            lineterminator="\n",
        )
        writer.writeheader()
        writer.writerows(rows)
    print(f"Wrote {len(rows)} rows to {OUTPUT_PATH}")


def _read_zipped_tsv(url: str) -> list[dict]:
    with urllib.request.urlopen(url, timeout=60) as response:
        data = response.read()
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        txt_name = next(name for name in archive.namelist() if name.endswith(".txt"))
        with archive.open(txt_name) as fh:
            text = io.TextIOWrapper(fh, encoding="utf-8")
            return [
                {str(key).strip(): str(value).strip() for key, value in row.items()}
                for row in csv.DictReader(text, delimiter="\t")
            ]


def _place_rows(records: list[dict]) -> list[dict]:
    rows = []
    seen = set()
    for record in records:
        state = record["USPS"].strip()
        city = _clean_place_name(record["NAME"].strip())
        key = ("city", city.lower(), state)
        if not city or key in seen:
            continue
        seen.add(key)
        rows.append(
            {
                "kind": "city",
                "city": city,
                "state": state,
                "county": "",
                "latitude": _coord(record["INTPTLAT"]),
                "longitude": _coord(record["INTPTLONG"]),
                "population": "",
            }
        )
    return rows


def _county_rows(records: list[dict]) -> list[dict]:
    rows = []
    for record in records:
        rows.append(
            {
                "kind": "county",
                "city": "",
                "state": record["USPS"].strip(),
                "county": _clean_county_name(record["NAME"].strip()),
                "latitude": _coord(record["INTPTLAT"]),
                "longitude": _coord(record["INTPTLONG"]),
                "population": "",
            }
        )
    return rows


def _clean_place_name(value: str) -> str:
    for suffix in PLACE_SUFFIXES:
        if value.endswith(suffix):
            return value[: -len(suffix)].strip()
    return value


def _clean_county_name(value: str) -> str:
    return re.sub(r"\s+(County|Parish|Borough|Census Area|Municipality|city)$", "", value).strip()


def _coord(value: str) -> str:
    return f"{float(value):.6f}"


if __name__ == "__main__":
    main()
