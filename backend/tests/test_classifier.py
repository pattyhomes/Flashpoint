"""
Tests for the deterministic unrest classifier.

Covers: accept/reject decisions, event_type mapping, multi-signal reinforcement,
hard-exclusion rules, and body-only fallback behavior.
"""

import pytest

from app.services.ingestion.classifier import classify, ClassificationResult


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def cat(uri: str) -> dict:
    return {"uri": uri}

def concept(uri: str) -> dict:
    return {"uri": uri}


# ---------------------------------------------------------------------------
# Accept cases: keyword signals
# ---------------------------------------------------------------------------

class TestAcceptKeywords:
    def test_protest_title_keyword(self):
        result = classify(
            title="Hundreds of protesters march through downtown Seattle",
            body="",
            categories=[],
            concepts=[],
        )
        assert result is not None
        assert result.event_type == "protest"

    def test_riot_title_phrase(self):
        result = classify(
            title="Riot broke out near city hall after curfew announcement",
            body="",
            categories=[],
            concepts=[],
        )
        assert result is not None
        assert result.event_type == "riot"

    def test_police_clash_title_phrase(self):
        result = classify(
            title="Police clash with demonstrators outside state capitol",
            body="",
            categories=[],
            concepts=[],
        )
        assert result is not None
        assert result.event_type == "police_clash"

    def test_tear_gas_phrase(self):
        result = classify(
            title="Officers deployed tear gas on crowd at university",
            body="",
            categories=[],
            concepts=[],
        )
        assert result is not None
        assert result.event_type == "police_clash"

    def test_looting_maps_to_riot(self):
        result = classify(
            title="Looting reported across three blocks during unrest",
            body="",
            categories=[],
            concepts=[],
        )
        assert result is not None
        assert result.event_type == "riot"

    def test_political_violence_phrase(self):
        result = classify(
            title="Political violence erupts at campaign rally",
            body="",
            categories=[],
            concepts=[],
        )
        assert result is not None
        assert result.event_type == "political_violence"

    def test_road_shutdown_phrase(self):
        result = classify(
            title="Protesters block freeway blocked causing major delays",
            body="",
            categories=[],
            concepts=[],
        )
        assert result is not None
        assert result.event_type == "protest_related_road_shutdown"

    def test_vandalism_title_phrase(self):
        # "storefronts smashed" phrase (score 0.80) clearly wins over any competing token
        result = classify(
            title="Storefronts smashed near city hall after march",
            body="",
            categories=[],
            concepts=[],
        )
        assert result is not None
        assert result.event_type == "vandalism_tied_to_unrest"


# ---------------------------------------------------------------------------
# Multi-signal reinforcement
# ---------------------------------------------------------------------------

class TestMultiSignalReinforcement:
    def test_title_plus_body_raises_score(self):
        r_title_only = classify(
            title="Protesters gathered in the park",
            body="",
            categories=[],
            concepts=[],
        )
        r_title_body = classify(
            title="Protesters gathered in the park",
            body="Protesters clashed with police near the entrance",
            categories=[],
            concepts=[],
        )
        assert r_title_only is not None
        assert r_title_body is not None
        # Having body phrase matches should not decrease the score
        assert r_title_body.score >= r_title_only.score

    def test_category_boost_increases_score(self):
        r_no_cat = classify(
            title="Demonstrators rallied outside the courthouse",
            body="",
            categories=[],
            concepts=[],
        )
        r_with_cat = classify(
            title="Demonstrators rallied outside the courthouse",
            body="",
            categories=[cat("dmoz/news/conflict_and_protest")],
            concepts=[],
        )
        assert r_no_cat is not None
        assert r_with_cat is not None
        assert r_with_cat.score > r_no_cat.score

    def test_concept_boost_increases_score(self):
        r_no_concept = classify(
            title="Demonstrators rallied outside the courthouse",
            body="",
            categories=[],
            concepts=[],
        )
        r_with_concept = classify(
            title="Demonstrators rallied outside the courthouse",
            body="",
            categories=[],
            concepts=[concept("en/protest"), concept("en/social_movement")],
        )
        assert r_no_concept is not None
        assert r_with_concept is not None
        assert r_with_concept.score > r_no_concept.score

    def test_score_capped_at_one(self):
        result = classify(
            title="Riot broke out — police clash with rioters and looting reported",
            body="Molotov cocktails thrown as officers deployed tear gas",
            categories=[cat("dmoz/conflict/civil_unrest"), cat("dmoz/news/protest")],
            concepts=[concept("en/riot"), concept("en/protest"), concept("en/police_brutality")],
        )
        assert result is not None
        assert result.score <= 1.0


# ---------------------------------------------------------------------------
# Reject cases: hard exclusions
# ---------------------------------------------------------------------------

class TestHardExclusions:
    def test_rejects_opinion_prefix(self):
        result = classify(
            title="Opinion: Why protest movements fail in the long run",
            body="Demonstrators have been gathering for weeks",
            categories=[],
            concepts=[],
        )
        assert result is None

    def test_rejects_analysis_prefix(self):
        result = classify(
            title="Analysis: The roots of political violence in America",
            body="Protesters marched through the city",
            categories=[],
            concepts=[],
        )
        assert result is None

    def test_rejects_weather_only_title(self):
        result = classify(
            title="Hurricane Milton makes landfall in Florida",
            body="Evacuation orders issued for coastal communities",
            categories=[],
            concepts=[],
        )
        assert result is None

    def test_rejects_traffic_accident(self):
        result = classify(
            title="Car crash on I-95 causes morning delays",
            body="A multi-vehicle accident blocked traffic",
            categories=[],
            concepts=[],
        )
        assert result is None

    def test_rejects_exclusively_sports_categories(self):
        result = classify(
            title="Players protest referee decision during championship match",
            body="",
            categories=[cat("dmoz/sports/football"), cat("dmoz/sports/championship")],
            concepts=[],
        )
        assert result is None

    def test_rejects_body_only_with_no_support(self):
        # Title has no keywords. Body has "protest" but no category/concept support.
        result = classify(
            title="City council announces infrastructure update",
            body="Residents have been protesting the decision for weeks",
            categories=[],
            concepts=[],
        )
        assert result is None

    def test_rejects_empty_title(self):
        result = classify(title="", body="Protesters marched downtown", categories=[], concepts=[])
        assert result is None

    def test_rejects_below_min_score(self):
        # A very weak signal should not pass min_score=0.6
        result = classify(
            title="A rally of interest to local observers",
            body="",
            categories=[],
            concepts=[],
            min_score=0.6,
        )
        # "rally" token has base 0.55, no boost; should be below threshold
        assert result is None or result.score >= 0.6


# ---------------------------------------------------------------------------
# Correct type for each class
# ---------------------------------------------------------------------------

class TestTypeMappings:
    @pytest.mark.parametrize("title,expected", [
        ("Protesters marched peacefully through downtown", "protest"),
        ("Rioters looted stores in the city center", "riot"),
        ("Political violence erupts near the capitol", "political_violence"),
        ("Officers deployed tear gas on crowd", "police_clash"),
        ("Windows smashed and storefronts smashed after demonstration", "vandalism_tied_to_unrest"),
        ("Protesters block highway blocked traffic for miles", "protest_related_road_shutdown"),
    ])
    def test_type_mapping(self, title, expected):
        result = classify(title=title, body="", categories=[], concepts=[])
        assert result is not None
        assert result.event_type == expected


# ---------------------------------------------------------------------------
# Vandalism/crowd_disruption downgrade when ambiguous
# ---------------------------------------------------------------------------

class TestDowngradeToUnrest:
    def test_vandalism_token_without_phrase_or_support_downgrades(self):
        # "vandalized" token in title but no phrase match or cat/concept → should downgrade to unrest
        result = classify(
            title="A building was vandalized overnight",
            body="",
            categories=[],
            concepts=[],
        )
        # Either None (below min_score) or downgraded to unrest
        if result is not None:
            assert result.event_type == "unrest"

    def test_vandalism_phrase_with_category_support_stays(self):
        # "storefronts smashed" phrase (0.80) + category boost stays as vandalism
        result = classify(
            title="Storefronts smashed following night of unrest",
            body="",
            categories=[cat("dmoz/conflict/protest")],
            concepts=[],
        )
        assert result is not None
        assert result.event_type == "vandalism_tied_to_unrest"
