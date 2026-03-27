"""
Tests for Event Registry confidence cap and corroboration uplift logic.

The cap/uplift functions live inside eventregistry_source.py as module-level
helpers. We import them directly for unit testing.
"""

import pytest

from app.services.ingestion.eventregistry_source import (
    _apply_uncorroborated_cap,
    _initial_confidence,
)


# ---------------------------------------------------------------------------
# _initial_confidence — score → confidence before capping
# ---------------------------------------------------------------------------

class TestInitialConfidence:
    def test_venue_precision_adds_bonus(self):
        # base = 0.30 + 0.20 * score + 0.12 (venue bonus)
        conf = _initial_confidence(classification_score=0.8, precision="venue")
        expected = 0.30 + 0.20 * 0.8 + 0.12
        assert abs(conf - expected) < 1e-6

    def test_city_precision_adds_smaller_bonus(self):
        conf = _initial_confidence(classification_score=0.8, precision="city")
        expected = 0.30 + 0.20 * 0.8 + 0.08
        assert abs(conf - expected) < 1e-6

    def test_state_precision_no_bonus(self):
        conf = _initial_confidence(classification_score=0.8, precision="state")
        expected = 0.30 + 0.20 * 0.8
        assert abs(conf - expected) < 1e-6

    def test_clamped_to_1(self):
        conf = _initial_confidence(classification_score=1.0, precision="venue")
        assert conf <= 1.0

    def test_clamped_above_0(self):
        conf = _initial_confidence(classification_score=0.0, precision="state")
        assert conf >= 0.15  # minimum floor


# ---------------------------------------------------------------------------
# _apply_uncorroborated_cap — venue cap = 0.62
# ---------------------------------------------------------------------------

class TestUncorroboratedVenueCap:
    def test_venue_cap_applied_when_confidence_above(self):
        capped = _apply_uncorroborated_cap(confidence=0.80, precision="venue", max_cap=0.62)
        assert capped == pytest.approx(0.62)

    def test_venue_cap_not_applied_when_confidence_below(self):
        capped = _apply_uncorroborated_cap(confidence=0.50, precision="venue", max_cap=0.62)
        assert capped == pytest.approx(0.50)

    def test_venue_cap_boundary(self):
        capped = _apply_uncorroborated_cap(confidence=0.62, precision="venue", max_cap=0.62)
        assert capped == pytest.approx(0.62)


# ---------------------------------------------------------------------------
# _apply_uncorroborated_cap — city cap = 0.58
# ---------------------------------------------------------------------------

class TestUncorroboratedCityCap:
    def test_city_cap_applied(self):
        capped = _apply_uncorroborated_cap(confidence=0.75, precision="city", max_cap=0.58)
        assert capped == pytest.approx(0.58)

    def test_city_cap_not_applied_when_already_below(self):
        capped = _apply_uncorroborated_cap(confidence=0.45, precision="city", max_cap=0.58)
        assert capped == pytest.approx(0.45)


# ---------------------------------------------------------------------------
# _apply_uncorroborated_cap — state cap = 0.45
# ---------------------------------------------------------------------------

class TestUncorroboratedStateCap:
    def test_state_cap_applied(self):
        capped = _apply_uncorroborated_cap(confidence=0.60, precision="state", max_cap=0.45)
        assert capped == pytest.approx(0.45)

    def test_state_cap_not_applied_when_already_low(self):
        capped = _apply_uncorroborated_cap(confidence=0.30, precision="state", max_cap=0.45)
        assert capped == pytest.approx(0.30)


# ---------------------------------------------------------------------------
# max_cap parameter interaction
# ---------------------------------------------------------------------------

class TestMaxCapParameter:
    def test_tiered_cap_takes_min_with_max_cap(self):
        # venue tier would cap at 0.62, but max_cap=0.50 wins
        capped = _apply_uncorroborated_cap(confidence=0.80, precision="venue", max_cap=0.50)
        assert capped == pytest.approx(0.50)

    def test_high_max_cap_does_not_override_tier(self):
        # max_cap=0.90 but city tier is 0.58 — tier wins
        capped = _apply_uncorroborated_cap(confidence=0.80, precision="city", max_cap=0.90)
        assert capped == pytest.approx(0.58)


# ---------------------------------------------------------------------------
# Corroboration uplift (modeled in caller; verified here as arithmetic)
# ---------------------------------------------------------------------------

class TestCorroborationUplift:
    """
    Uplift is applied by the pipeline caller, not by _apply_uncorroborated_cap.
    These tests verify the expected arithmetic for the uplift pattern used in seed.py.
    """

    UPLIFT = 0.08

    def test_single_independent_source_adds_uplift(self):
        base = 0.50
        uplifted = min(1.0, base + self.UPLIFT)
        assert uplifted == pytest.approx(0.58)

    def test_three_independent_sources_cumulative(self):
        base = 0.50
        uplifted = min(1.0, base + 3 * self.UPLIFT)
        assert uplifted == pytest.approx(0.74)

    def test_uplift_capped_at_one(self):
        base = 0.95
        uplifted = min(1.0, base + self.UPLIFT)
        assert uplifted == pytest.approx(1.0)

    def test_syndicated_source_adds_zero_uplift(self):
        base = 0.50
        # syndicated sources have trust_weight=0.0; no uplift applied
        uplifted = min(1.0, base + 0 * self.UPLIFT)
        assert uplifted == pytest.approx(0.50)

    def test_cap_removed_after_genuine_corroboration(self):
        """
        Once corroborated, the uncorroborated cap no longer applies.
        Verify: city-level event that was capped at 0.58 can exceed cap after corroboration.
        """
        initial_capped = 0.58  # after applying city cap
        # 1 independent non-ER corroboration removes the cap
        corroborated = min(1.0, initial_capped + self.UPLIFT)
        assert corroborated == pytest.approx(0.66)
        # 0.66 > 0.58 (city cap) — cap is effectively bypassed
        assert corroborated > 0.58

    def test_three_syndicated_copies_still_capped(self):
        """
        3 syndicated AP rewrites should not uplift confidence — cap stays.
        """
        base_capped = 0.58  # city-level event
        # 3 syndicated, each with trust_weight=0: no uplift
        still_capped = min(1.0, base_capped + 0 * 3)
        assert still_capped == pytest.approx(0.58)
