"""
Tests for hotspot clustering algorithm and trend scoring.

Covers: cluster radius threshold, centroid stability with state-level events,
MIN_EVENTS pruning, trend zero-baseline fix, trend normal cases, momentum decay.
"""
import types
import unittest
from datetime import datetime, timedelta

from app.services.scoring.hotspot import (
    CLUSTER_RADIUS_MILES,
    MIN_EVENTS,
    _cluster_events,
    _momentum,
    _trend,
)


_NOW = datetime(2026, 3, 27, 12, 0, 0)


def _ev(
    lat: float,
    lon: float,
    city: str | None = "TestCity",
    state: str | None = "CA",
    occurred_at: datetime | None = None,
    severity_score: float = 0.5,
) -> types.SimpleNamespace:
    """Minimal fake Event with only the fields clustering/trend functions read."""
    return types.SimpleNamespace(
        latitude=lat,
        longitude=lon,
        city=city,
        state=state,
        occurred_at=occurred_at or _NOW,
        severity_score=severity_score,
        cluster_id=None,
        trend_state=None,
    )


# ---------------------------------------------------------------------------
# Cluster radius
# ---------------------------------------------------------------------------

class TestClusterRadius(unittest.TestCase):

    def test_events_within_radius_merge(self):
        # Seattle (~47.6, -122.3) to Bellevue (~47.6, -122.2) is ~5 miles — well within 75
        seattle = _ev(47.6062, -122.3321)
        bellevue = _ev(47.6101, -122.2015)
        third = _ev(47.6205, -122.3492)   # still in Seattle area
        clusters = _cluster_events([seattle, bellevue, third])
        self.assertEqual(len(clusters), 1)
        self.assertEqual(len(clusters[0]["members"]), 3)

    def test_events_beyond_radius_do_not_merge(self):
        # Seattle (47.6, -122.3) to Portland (45.5, -122.7) is ~145 miles > 75
        seattle = _ev(47.6062, -122.3321, city="Seattle", state="WA")
        seattle2 = _ev(47.5952, -122.3318, city="Seattle", state="WA")
        seattle3 = _ev(47.6205, -122.3492, city="Seattle", state="WA")
        portland = _ev(45.5231, -122.6765, city="Portland", state="OR")
        portland2 = _ev(45.5122, -122.6587, city="Portland", state="OR")
        portland3 = _ev(45.5050, -122.6700, city="Portland", state="OR")
        clusters = _cluster_events([seattle, seattle2, seattle3, portland, portland2, portland3])
        # Should form 2 separate clusters
        self.assertEqual(len(clusters), 2)
        city_sets = [
            set(e.city for e in c["members"])
            for c in clusters
        ]
        self.assertIn({"Seattle"}, city_sets)
        self.assertIn({"Portland"}, city_sets)

    def test_current_radius_constant_is_75(self):
        self.assertEqual(CLUSTER_RADIUS_MILES, 75)


# ---------------------------------------------------------------------------
# Centroid stability: state-level events do not move centroid
# ---------------------------------------------------------------------------

class TestCentroidStability(unittest.TestCase):

    def test_state_level_event_does_not_shift_centroid(self):
        # Anchor 3 city-level events at lat=47.6, lon=-122.3 (Seattle area)
        city1 = _ev(47.6062, -122.3321, city="Seattle",    state="WA")
        city2 = _ev(47.5952, -122.3318, city="Seattle",    state="WA")
        city3 = _ev(47.6205, -122.3492, city="Seattle",    state="WA")
        # State-level event at California centroid — should join but not move centroid
        state_ev = _ev(36.7700, -119.4200, city="California", state="CA")

        clusters = _cluster_events([city1, city2, city3, state_ev])
        # All 4 events join the Seattle cluster (state_ev is within 150 miles? No —
        # Seattle to California centroid is ~850 miles. State-level events that
        # can't join any cluster go to Pass 2. With only 1 such event, no fallback cluster.)
        # The Seattle cluster should have 3 members; the state event is unassigned.
        seattle_clusters = [c for c in clusters if any(e.city == "Seattle" for e in c["members"])]
        self.assertEqual(len(seattle_clusters), 1)
        seattle = seattle_clusters[0]
        # Centroid should remain near Seattle, not pulled toward California
        self.assertGreater(seattle["lat"], 47.0)

    def test_state_level_event_near_cluster_joins_without_moving_centroid(self):
        # City events in Seattle area
        city1 = _ev(47.6062, -122.3321, city="Seattle", state="WA")
        city2 = _ev(47.5952, -122.3318, city="Seattle", state="WA")
        city3 = _ev(47.6205, -122.3492, city="Seattle", state="WA")
        # "Washington" state-level event at WA centroid (~47.5, -120.5) — ~65 miles east
        wa_centroid = _ev(47.5, -120.5, city="Washington", state="WA")

        clusters = _cluster_events([city1, city2, city3, wa_centroid])
        self.assertGreaterEqual(len(clusters), 1)
        # Find cluster containing Seattle events
        seattle_clusters = [c for c in clusters if any(e.city == "Seattle" for e in c["members"])]
        self.assertEqual(len(seattle_clusters), 1)
        seattle = seattle_clusters[0]
        # Centroid should be near Seattle (lon ~-122.3), not pulled east toward -120.5
        self.assertLess(seattle["lon"], -121.5)


# ---------------------------------------------------------------------------
# MIN_EVENTS pruning
# ---------------------------------------------------------------------------

class TestMinEventsPruning(unittest.TestCase):

    def test_two_member_cluster_pruned(self):
        e1 = _ev(47.6062, -122.3321)
        e2 = _ev(47.5952, -122.3318)
        clusters = _cluster_events([e1, e2])
        self.assertEqual(len(clusters), 0)

    def test_three_member_cluster_kept(self):
        e1 = _ev(47.6062, -122.3321)
        e2 = _ev(47.5952, -122.3318)
        e3 = _ev(47.6205, -122.3492)
        clusters = _cluster_events([e1, e2, e3])
        self.assertEqual(len(clusters), 1)

    def test_min_events_constant_is_3(self):
        self.assertEqual(MIN_EVENTS, 3)


# ---------------------------------------------------------------------------
# Trend: zero-baseline bias fix
# ---------------------------------------------------------------------------

class TestTrendZeroBaseline(unittest.TestCase):

    def test_single_recent_vs_zero_earlier_is_stable(self):
        # 1 recent event, 0 earlier — should NOT trigger "escalating"
        recent_event = _ev(0, 0, occurred_at=_NOW - timedelta(hours=2))
        result = _trend([recent_event], _NOW)
        self.assertEqual(result, "stable")

    def test_two_recent_vs_zero_earlier_is_escalating(self):
        # 2 recent events, 0 earlier — enough evidence for escalating
        r1 = _ev(0, 0, occurred_at=_NOW - timedelta(hours=2))
        r2 = _ev(0, 0, occurred_at=_NOW - timedelta(hours=4))
        result = _trend([r1, r2], _NOW)
        self.assertEqual(result, "escalating")

    def test_four_recent_vs_one_earlier_is_escalating(self):
        r1 = _ev(0, 0, occurred_at=_NOW - timedelta(hours=1))
        r2 = _ev(0, 0, occurred_at=_NOW - timedelta(hours=3))
        r3 = _ev(0, 0, occurred_at=_NOW - timedelta(hours=5))
        r4 = _ev(0, 0, occurred_at=_NOW - timedelta(hours=7))
        e1 = _ev(0, 0, occurred_at=_NOW - timedelta(hours=10))
        result = _trend([r1, r2, r3, r4, e1], _NOW)
        self.assertEqual(result, "escalating")

    def test_one_recent_vs_three_earlier_is_declining(self):
        # Declining requires: e_count > r_count * 2 AND e_sev > r_sev
        r1 = _ev(0, 0, occurred_at=_NOW - timedelta(hours=2),  severity_score=0.3)
        e1 = _ev(0, 0, occurred_at=_NOW - timedelta(hours=9),  severity_score=0.7)
        e2 = _ev(0, 0, occurred_at=_NOW - timedelta(hours=14), severity_score=0.8)
        e3 = _ev(0, 0, occurred_at=_NOW - timedelta(hours=20), severity_score=0.7)
        result = _trend([r1, e1, e2, e3], _NOW)
        self.assertEqual(result, "declining")

    def test_equal_recent_and_earlier_is_stable(self):
        r1 = _ev(0, 0, occurred_at=_NOW - timedelta(hours=2), severity_score=0.5)
        r2 = _ev(0, 0, occurred_at=_NOW - timedelta(hours=5), severity_score=0.5)
        e1 = _ev(0, 0, occurred_at=_NOW - timedelta(hours=10), severity_score=0.5)
        e2 = _ev(0, 0, occurred_at=_NOW - timedelta(hours=18), severity_score=0.5)
        result = _trend([r1, r2, e1, e2], _NOW)
        self.assertEqual(result, "stable")


# ---------------------------------------------------------------------------
# Momentum: events older than 24h contribute zero
# ---------------------------------------------------------------------------

class TestMomentumDecay(unittest.TestCase):

    def test_event_older_than_24h_has_zero_momentum(self):
        old_event = _ev(0, 0, occurred_at=_NOW - timedelta(hours=25), severity_score=1.0)
        mom = _momentum([old_event], _NOW)
        self.assertEqual(mom, 0.0)

    def test_recent_event_has_positive_momentum(self):
        recent_event = _ev(0, 0, occurred_at=_NOW - timedelta(hours=2), severity_score=0.8)
        mom = _momentum([recent_event], _NOW)
        self.assertGreater(mom, 0.0)

    def test_momentum_capped_at_one(self):
        # Multiple recent high-severity events
        events = [
            _ev(0, 0, occurred_at=_NOW - timedelta(hours=i), severity_score=1.0)
            for i in range(1, 10)
        ]
        mom = _momentum(events, _NOW)
        self.assertLessEqual(mom, 1.0)


if __name__ == "__main__":
    unittest.main()
