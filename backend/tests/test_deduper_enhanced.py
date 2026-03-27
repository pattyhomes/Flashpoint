"""
Tests for the enhanced deduplication utilities:
  - is_syndicated_copy() — six-rule syndicated detection
  - find_matching_event() — cross-source similarity matching
"""

from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest

from app.services.ingestion.deduper import (
    find_matching_event,
    is_syndicated_copy,
)


# ---------------------------------------------------------------------------
# EventSource factory
# ---------------------------------------------------------------------------

def make_source(
    source_name: str = "Test Outlet",
    source_url: str | None = None,
    source_title: str | None = None,
    source_published_at: datetime | None = None,
    metadata_json: str | None = None,
) -> MagicMock:
    src = MagicMock()
    src.source_name = source_name
    src.source_url = source_url
    src.source_title = source_title
    src.source_published_at = source_published_at
    src.metadata_json = metadata_json
    return src


_BASE_TIME = datetime(2025, 3, 15, 12, 0, 0)
_TITLE = "Protesters march outside state capitol building"


# ---------------------------------------------------------------------------
# is_syndicated_copy — Rule 1: same outlet
# ---------------------------------------------------------------------------

class TestSyndicatedSameOutlet:
    def test_same_outlet_is_syndicated(self):
        src = make_source(source_name="AP News")
        assert is_syndicated_copy(
            outlet_name="AP News",
            article_url=None,
            article_title=_TITLE,
            article_published_at=_BASE_TIME,
            article_er_event_uri=None,
            existing_sources=[src],
        ) is True

    def test_same_outlet_case_insensitive(self):
        src = make_source(source_name="Reuters")
        assert is_syndicated_copy(
            outlet_name="REUTERS",
            article_url=None,
            article_title=_TITLE,
            article_published_at=_BASE_TIME,
            article_er_event_uri=None,
            existing_sources=[src],
        ) is True

    def test_different_outlet_not_syndicated_by_name_alone(self):
        src = make_source(source_name="The Seattle Times")
        result = is_syndicated_copy(
            outlet_name="The Portland Tribune",
            article_url=None,
            article_title="Completely different story about a sporting event",
            article_published_at=_BASE_TIME,
            article_er_event_uri=None,
            existing_sources=[src],
        )
        assert result is False


# ---------------------------------------------------------------------------
# is_syndicated_copy — Rule 2: wire family
# ---------------------------------------------------------------------------

class TestSyndicatedWireFamily:
    def test_ap_variant_names_same_family(self):
        # "Associated Press" and "AP News" should be in the same family
        src = make_source(source_name="Associated Press")
        assert is_syndicated_copy(
            outlet_name="AP News",
            article_url=None,
            article_title=_TITLE,
            article_published_at=_BASE_TIME,
            article_er_event_uri=None,
            existing_sources=[src],
        ) is True

    def test_reuters_variants_same_family(self):
        src = make_source(source_name="Reuters")
        assert is_syndicated_copy(
            outlet_name="Reuters UK",
            article_url=None,
            article_title=_TITLE,
            article_published_at=_BASE_TIME,
            article_er_event_uri=None,
            existing_sources=[src],
        ) is True

    def test_different_wire_families_not_syndicated(self):
        # AP vs Reuters — different families; no other rule fires
        src = make_source(
            source_name="Associated Press",
            source_title="An entirely unrelated article about city budget",
            source_published_at=_BASE_TIME - timedelta(hours=5),
        )
        result = is_syndicated_copy(
            outlet_name="Reuters",
            article_url=None,
            article_title="Protesters rallied outside the building",
            article_published_at=_BASE_TIME,
            article_er_event_uri=None,
            existing_sources=[src],
        )
        assert result is False


# ---------------------------------------------------------------------------
# is_syndicated_copy — Rule 3: high title similarity
# ---------------------------------------------------------------------------

class TestSyndicatedTitleSimilarity:
    def test_near_identical_title_is_syndicated(self):
        existing_title = "Protesters march outside the state capitol building today"
        new_title      = "Protesters march outside state capitol building"
        src = make_source(source_name="Some Outlet", source_title=existing_title)
        assert is_syndicated_copy(
            outlet_name="Other Outlet",
            article_url=None,
            article_title=new_title,
            article_published_at=None,
            article_er_event_uri=None,
            existing_sources=[src],
        ) is True

    def test_different_title_not_syndicated_by_similarity(self):
        src = make_source(
            source_name="Some Outlet",
            source_title="City council approves new transit plan",
        )
        result = is_syndicated_copy(
            outlet_name="Other Outlet",
            article_url=None,
            article_title="Protesters march outside the capitol demanding change",
            article_published_at=None,
            article_er_event_uri=None,
            existing_sources=[src],
        )
        assert result is False


# ---------------------------------------------------------------------------
# is_syndicated_copy — Rule 4: wire domain URL match
# ---------------------------------------------------------------------------

class TestSyndicatedUrlDomain:
    def test_apnews_domain_match_is_syndicated(self):
        src = make_source(
            source_name="Some Site",
            source_url="https://apnews.com/article/protest-seattle-12345",
        )
        assert is_syndicated_copy(
            outlet_name="Another Site",
            article_url="https://apnews.com/article/protest-seattle-67890",
            article_title="Different protesters event",
            article_published_at=None,
            article_er_event_uri=None,
            existing_sources=[src],
        ) is True

    def test_non_wire_domain_not_syndicated_by_rule4(self):
        src = make_source(
            source_name="Seattle Times",
            source_url="https://seattletimes.com/article/123",
        )
        result = is_syndicated_copy(
            outlet_name="Oregon Live",
            article_url="https://oregonlive.com/article/456",
            article_title="Entirely separate event in another city",
            article_published_at=None,
            article_er_event_uri=None,
            existing_sources=[src],
        )
        assert result is False


# ---------------------------------------------------------------------------
# is_syndicated_copy — Rule 5: timestamp proximity + moderate title similarity
# ---------------------------------------------------------------------------

class TestSyndicatedTimestampProximity:
    def test_rapid_rewrite_is_syndicated(self):
        # Published 15 minutes apart, titles share >0.70 Jaccard
        t1 = _BASE_TIME
        t2 = _BASE_TIME + timedelta(minutes=15)
        src = make_source(
            source_name="Outlet A",
            source_title="Police deployed tear gas on protesters near city hall",
            source_published_at=t1,
        )
        assert is_syndicated_copy(
            outlet_name="Outlet B",
            article_url=None,
            article_title="Police deploy tear gas on protesters near city hall",
            article_published_at=t2,
            article_er_event_uri=None,
            existing_sources=[src],
        ) is True

    def test_timestamp_close_but_titles_different_not_syndicated(self):
        t1 = _BASE_TIME
        t2 = _BASE_TIME + timedelta(minutes=10)
        src = make_source(
            source_name="Outlet A",
            source_title="City council votes on housing ordinance",
            source_published_at=t1,
        )
        result = is_syndicated_copy(
            outlet_name="Outlet B",
            article_url=None,
            article_title="Protesters demand climate action at downtown rally",
            article_published_at=t2,
            article_er_event_uri=None,
            existing_sources=[src],
        )
        assert result is False


# ---------------------------------------------------------------------------
# is_syndicated_copy — Rule 6: same ER eventUri + same outlet family
# ---------------------------------------------------------------------------

class TestSyndicatedErEventUri:
    def test_same_event_uri_and_family_is_syndicated(self):
        src = make_source(
            source_name="AP News",
            metadata_json='{"er_event_uri": "eng-12345"}',
        )
        assert is_syndicated_copy(
            outlet_name="Associated Press",
            article_url=None,
            article_title=_TITLE,
            article_published_at=None,
            article_er_event_uri="eng-12345",
            existing_sources=[src],
        ) is True

    def test_same_event_uri_different_family_not_syndicated_by_rule6(self):
        # Same ER eventUri but different wire families — rule 6 does not fire alone
        src = make_source(
            source_name="AP News",
            source_title="Somewhat different title for same event",
            source_published_at=_BASE_TIME - timedelta(hours=3),
            metadata_json='{"er_event_uri": "eng-12345"}',
        )
        result = is_syndicated_copy(
            outlet_name="Reuters",        # different wire family
            article_url=None,
            article_title="Slightly different title that doesn't match well",
            article_published_at=_BASE_TIME,
            article_er_event_uri="eng-12345",
            existing_sources=[src],
        )
        # Rule 6 requires SAME family — AP ≠ Reuters; others shouldn't fire either
        assert result is False


# ---------------------------------------------------------------------------
# is_syndicated_copy — genuine independent article
# ---------------------------------------------------------------------------

class TestGenuinelyIndependent:
    def test_independent_article_returns_false(self):
        src = make_source(
            source_name="Seattle Times",
            source_url="https://seattletimes.com/news/123",
            source_title="Protesters demand affordable housing outside city hall",
            source_published_at=_BASE_TIME - timedelta(hours=8),
        )
        result = is_syndicated_copy(
            outlet_name="Portland Tribune",
            article_url="https://portlandtribune.com/news/456",
            article_title="Activists block bridge to protest pipeline expansion",
            article_published_at=_BASE_TIME,
            article_er_event_uri="eng-99999",
            existing_sources=[src],
        )
        assert result is False

    def test_empty_existing_sources_returns_false(self):
        assert is_syndicated_copy(
            outlet_name="AP News",
            article_url=None,
            article_title=_TITLE,
            article_published_at=_BASE_TIME,
            article_er_event_uri=None,
            existing_sources=[],
        ) is False


# ---------------------------------------------------------------------------
# find_matching_event — cross-source similarity
# ---------------------------------------------------------------------------

def make_event(
    id: int = 1,
    title: str = _TITLE,
    lat: float = 47.6,
    lon: float = -122.3,
    occurred_at: datetime = _BASE_TIME,
    event_type: str = "protest",
    is_active: bool = True,
) -> MagicMock:
    ev = MagicMock()
    ev.id = id
    ev.title = title
    ev.latitude = lat
    ev.longitude = lon
    ev.occurred_at = occurred_at
    ev.event_type = event_type
    ev.is_active = is_active
    return ev


class TestFindMatchingEvent:
    def _mock_db(self, events: list) -> MagicMock:
        """Return a mock DB session whose .query().filter().all() yields events."""
        db = MagicMock()
        db.query.return_value.filter.return_value.all.return_value = events
        return db

    def test_matches_nearby_recent_similar_title(self):
        ev = make_event(
            title="Protesters march outside state capitol building",
            lat=47.6097, lon=-122.3331,
            occurred_at=_BASE_TIME,
        )
        db = self._mock_db([ev])
        result = find_matching_event(
            title="Protesters march outside the capitol building",
            lat=47.6097,
            lon=-122.3331,
            occurred_at=_BASE_TIME + timedelta(hours=1),
            event_type="protest",
            db=db,
        )
        assert result is ev

    def test_returns_none_for_distant_event(self):
        ev = make_event(
            title=_TITLE,
            lat=34.0522,  # Los Angeles
            lon=-118.2437,
            occurred_at=_BASE_TIME,
        )
        db = self._mock_db([ev])
        result = find_matching_event(
            title=_TITLE,
            lat=47.6097,   # Seattle — ~1100 miles away
            lon=-122.3331,
            occurred_at=_BASE_TIME,
            event_type="protest",
            db=db,
        )
        assert result is None

    def test_returns_none_for_unrelated_title(self):
        ev = make_event(
            title="City budget hearing draws large crowd of residents",
            lat=47.6097, lon=-122.3331,
            occurred_at=_BASE_TIME,
        )
        db = self._mock_db([ev])
        result = find_matching_event(
            title="Protesters clash with police outside state capitol",
            lat=47.6097,
            lon=-122.3331,
            occurred_at=_BASE_TIME + timedelta(hours=2),
            event_type="police_clash",
            db=db,
        )
        assert result is None

    def test_returns_none_when_no_candidates(self):
        db = self._mock_db([])
        result = find_matching_event(
            title=_TITLE,
            lat=47.6097,
            lon=-122.3331,
            occurred_at=_BASE_TIME,
            event_type="protest",
            db=db,
        )
        assert result is None

    def test_returns_best_scoring_match(self):
        close = make_event(
            id=1,
            title="Protesters march outside state capitol",
            lat=47.6097, lon=-122.3331,
            occurred_at=_BASE_TIME + timedelta(hours=1),
        )
        far_older = make_event(
            id=2,
            title="Protesters marched near state capitol last weekend",
            lat=47.6100, lon=-122.3340,
            occurred_at=_BASE_TIME - timedelta(hours=40),
        )
        db = self._mock_db([close, far_older])
        result = find_matching_event(
            title="Protesters march outside state capitol building",
            lat=47.6097,
            lon=-122.3331,
            occurred_at=_BASE_TIME + timedelta(hours=2),
            event_type="protest",
            db=db,
        )
        # Both pass gates; the closer/more-recent one should win
        assert result is close
