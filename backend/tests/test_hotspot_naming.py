"""
Unit tests for hotspot naming — _hotspot_name().
Verifies precision filtering and proximity-weighted city ranking.
"""
import types
import unittest

from app.services.scoring.hotspot import _hotspot_name


def _ev(city, state, lat, lon):
    """Minimal fake Event with only the fields _hotspot_name() reads."""
    return types.SimpleNamespace(city=city, state=state, latitude=lat, longitude=lon)


class TestHotspotNaming(unittest.TestCase):

    def test_proximity_overcomes_higher_frequency_at_periphery(self):
        # Centroid at (32.0, -97.0) — near Fort Worth.
        # El Paso has 3 events but is ~556 miles from centroid.
        # Fort Worth has 2 events but is only ~55 miles from centroid.
        # Proximity discount makes Fort Worth win despite fewer events.
        members = (
            [_ev("Fort Worth", "TX", 32.75, -97.33)] * 2
            + [_ev("El Paso",   "TX", 31.76, -106.49)] * 3
        )
        name = _hotspot_name(members, centroid_lat=32.0, centroid_lon=-97.0)
        self.assertIn("Fort Worth", name)

    def test_proximity_breaks_equal_frequency_tie(self):
        # Same count; Fort Worth is much closer to centroid than El Paso.
        members = (
            [_ev("Fort Worth", "TX", 32.75, -97.33)] * 2
            + [_ev("El Paso",   "TX", 31.76, -106.49)] * 2
        )
        name = _hotspot_name(members, centroid_lat=32.0, centroid_lon=-97.0)
        self.assertIn("Fort Worth", name)

    def test_state_level_city_excluded(self):
        members = [
            _ev("California", "CA", 36.77, -119.42),
            _ev("California", "CA", 36.0,  -120.0),
        ]
        name = _hotspot_name(members, centroid_lat=36.5, centroid_lon=-119.7)
        self.assertEqual(name, "California region")

    def test_country_level_city_excluded(self):
        members = [
            _ev("United States", "TX", 39.84, -98.55),
            _ev("United States", "TX", 39.0,  -99.0),
        ]
        name = _hotspot_name(members, centroid_lat=39.5, centroid_lon=-98.8)
        self.assertNotIn("United States", name)

    def test_abbreviation_as_city_excluded(self):
        # city == state abbreviation → treated as state-level → region fallback
        members = [_ev("TX", "TX", 31.0, -100.0)] * 3
        name = _hotspot_name(members, centroid_lat=31.0, centroid_lon=-100.0)
        self.assertEqual(name, "Texas region")

    def test_county_fallback_when_no_precise_city(self):
        members = [
            _ev("Los Angeles County", "CA", 34.05, -118.24),
            _ev("Los Angeles County", "CA", 33.90, -118.10),
            _ev("California",         "CA", 36.77, -119.42),
        ]
        name = _hotspot_name(members, centroid_lat=34.0, centroid_lon=-118.2)
        self.assertIn("Los Angeles County", name)

    def test_state_region_abbreviation_expanded(self):
        # State abbrev "LA" → "Louisiana region", not ambiguous "LA region"
        members = [
            _ev("Louisiana", "LA", 30.98, -91.96),
            _ev("Louisiana", "LA", 30.5,  -90.5),
        ]
        name = _hotspot_name(members, centroid_lat=30.75, centroid_lon=-91.2)
        self.assertEqual(name, "Louisiana region")

    def test_coordinate_fallback_when_no_location(self):
        members = [_ev(None, None, 40.0, -100.0)]
        name = _hotspot_name(members, centroid_lat=40.0, centroid_lon=-100.0)
        self.assertIn("°N", name)
        self.assertIn("°W", name)

    def test_city_includes_state_suffix(self):
        members = [_ev("Chicago", "IL", 41.88, -87.63)] * 3
        name = _hotspot_name(members, centroid_lat=41.88, centroid_lon=-87.63)
        self.assertEqual(name, "Chicago, IL")


if __name__ == "__main__":
    unittest.main()
