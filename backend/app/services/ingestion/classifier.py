"""
Deterministic unrest classifier for Event Registry articles.

Classifies articles into Flashpoint V1-aligned event types using four signal sources:
  1. Title keywords
  2. Body keywords
  3. ER DMOZ category paths
  4. ER Wikipedia concept URIs

No LLM. No external calls. Pure function — takes article fields, returns a result.

Allowed output classes:
  protest | riot | political_violence | police_clash | vandalism_tied_to_unrest |
  crowd_disruption | protest_related_road_shutdown | unrest (fallback)

Returns None if the article is rejected by classification or hard-exclusion rules.
"""

import re
from dataclasses import dataclass

# ---------------------------------------------------------------------------
# Type definitions
# ---------------------------------------------------------------------------

@dataclass
class ClassificationResult:
    event_type: str
    score: float            # 0.0–1.0; reflects signal strength


# ---------------------------------------------------------------------------
# Keyword sets — grouped by specificity (most specific first)
# ---------------------------------------------------------------------------

# Multi-word phrases must appear in the lowercased text verbatim
_PHRASE_PATTERNS: list[tuple[str, str, float]] = [
    # (pattern, event_type, base_score)
    ("political violence",          "political_violence",          0.85),
    ("assassination attempt",       "political_violence",          0.90),
    ("shooting at protest",         "political_violence",          0.90),
    ("attacked at rally",           "political_violence",          0.85),
    ("bombing",                     "political_violence",          0.75),
    ("pipe bomb",                   "political_violence",          0.85),
    ("molotov",                     "political_violence",          0.80),
    ("police clash",                "police_clash",                0.85),
    ("clashed with police",         "police_clash",                0.85),
    ("tear gas",                    "police_clash",                0.80),
    ("pepper spray",                "police_clash",                0.75),
    ("rubber bullet",               "police_clash",                0.80),
    ("police brutality",            "police_clash",                0.80),
    ("officer injured",             "police_clash",                0.75),
    ("officers injured",            "police_clash",                0.75),
    ("highway blocked",             "protest_related_road_shutdown", 0.80),
    ("freeway blocked",             "protest_related_road_shutdown", 0.80),
    ("bridge shutdown",             "protest_related_road_shutdown", 0.75),
    ("road blockade",               "protest_related_road_shutdown", 0.75),
    ("interstate blocked",          "protest_related_road_shutdown", 0.80),
    ("property damage",             "vandalism_tied_to_unrest",    0.60),  # needs context
    ("storefronts smashed",         "vandalism_tied_to_unrest",    0.80),
    ("windows smashed",             "vandalism_tied_to_unrest",    0.75),
    ("looting",                     "riot",                        0.85),
    ("rioters",                     "riot",                        0.85),
    ("rioting",                     "riot",                        0.85),
    ("riot broke out",              "riot",                        0.90),
    ("crowd dispersed",             "crowd_disruption",            0.65),
    ("crowd dispersal",             "crowd_disruption",            0.70),
    ("mob",                         "crowd_disruption",            0.65),
    ("rally against",               "protest",                     0.70),
    ("march against",               "protest",                     0.70),
]

# Single-word tokens (matched against lowercased word set, not substring)
_TOKEN_MAP: list[tuple[str, str, float]] = [
    # (token, event_type, base_score)
    ("protest",          "protest",         0.65),
    ("protesters",       "protest",         0.65),
    ("protester",        "protest",         0.65),
    ("demonstration",    "protest",         0.65),
    ("demonstrators",    "protest",         0.65),
    ("picket",           "protest",         0.60),
    ("picketing",        "protest",         0.60),
    ("marchers",         "protest",         0.60),
    ("rally",            "protest",         0.55),
    ("rallying",         "protest",         0.55),
    ("riot",             "riot",            0.70),
    ("vandalism",        "vandalism_tied_to_unrest", 0.65),
    ("vandalized",       "vandalism_tied_to_unrest", 0.65),
    ("graffiti",         "vandalism_tied_to_unrest", 0.55),
    ("arson",            "vandalism_tied_to_unrest", 0.70),
    ("stampede",         "crowd_disruption", 0.70),
    ("baton",            "police_clash",    0.65),
    ("unrest",           "unrest",          0.55),
]

# ---------------------------------------------------------------------------
# Category and concept reinforcement
# ---------------------------------------------------------------------------

# ER DMOZ category path fragments that reinforce classification
_CONFLICT_CATEGORY_FRAGMENTS = {
    "conflict", "protest", "violence", "civil_unrest", "riot", "demonstration",
    "human_rights", "political", "social_action", "activism",
}

# ER Wikipedia concept URI fragments that reinforce classification
_CONFLICT_CONCEPT_FRAGMENTS = {
    "protest", "riot", "civil_unrest", "demonstration", "political_violence",
    "police_brutality", "social_movement", "activism",
}

# ---------------------------------------------------------------------------
# Hard exclusion patterns — reject regardless of keyword matches
# ---------------------------------------------------------------------------

# Title prefix patterns that signal opinion/analysis, not news events
_OPINION_PREFIXES = re.compile(
    r"^(opinion|analysis|editorial|column|commentary|perspective|explainer|review|"
    r"fact[\s-]check|fact check|op-ed|letter to)[\s:,–—]",
    re.IGNORECASE,
)

# Tokens that indicate weather-only articles when unrest tokens are absent or weak
_WEATHER_TOKENS = frozenset({
    "hurricane", "tornado", "earthquake", "flood", "flooding", "wildfire",
    "blizzard", "drought", "tsunami",
})

# Tokens that indicate ordinary crime (without unrest context)
_CRIME_TOKENS = frozenset({
    "dui", "drunk driving", "burglary", "robbery",
})

# Sub-strings that indicate traffic accidents (without unrest context)
_ACCIDENT_PHRASES = ("car crash", "traffic accident", "vehicle accident", "auto accident")

# Category path fragments that are exclusively non-unrest domains
_EXCLUDED_CATEGORY_DOMAINS = {
    "sports", "entertainment", "business", "technology", "finance",
    "lifestyle", "fashion", "travel", "food", "health", "science",
}

# ---------------------------------------------------------------------------
# Stop words for Jaccard similarity (shared with deduper)
# ---------------------------------------------------------------------------

_STOP_WORDS = frozenset({
    "a", "an", "the", "and", "or", "but", "in", "on", "at", "to", "for",
    "of", "with", "by", "from", "up", "is", "are", "was", "were", "be",
    "been", "has", "have", "had", "do", "does", "did", "will", "would",
    "could", "should", "may", "might", "as", "that", "this", "it", "its",
    "after", "during", "over", "into", "about", "than", "more", "not",
    "no", "new", "says", "said", "amid", "following",
})


def _tokens(text: str) -> frozenset[str]:
    """Lowercase word tokens excluding stop words."""
    words = re.findall(r"[a-z]+", text.lower())
    return frozenset(w for w in words if w not in _STOP_WORDS and len(w) > 2)


# ---------------------------------------------------------------------------
# Category / concept helpers
# ---------------------------------------------------------------------------

def _category_boost(categories: list[dict]) -> float:
    """Return score boost (0–0.2) from ER DMOZ category paths."""
    for cat in categories:
        uri = cat.get("uri", "").lower()
        for frag in _CONFLICT_CATEGORY_FRAGMENTS:
            if frag in uri:
                return 0.2
    # Check if ALL categories are excluded domains — used in exclusion test
    return 0.0


def _concept_boost(concepts: list[dict]) -> float:
    """Return score boost (0–0.3) from ER Wikipedia concept URIs."""
    boost = 0.0
    for concept in concepts:
        uri = concept.get("uri", "").lower()
        for frag in _CONFLICT_CONCEPT_FRAGMENTS:
            if frag in uri:
                boost += 0.1
                break
    return min(0.3, boost)


def _all_excluded_categories(categories: list[dict]) -> bool:
    """Return True if every category is an excluded non-unrest domain."""
    if not categories:
        return False
    for cat in categories:
        uri = cat.get("uri", "").lower()
        if not any(dom in uri for dom in _EXCLUDED_CATEGORY_DOMAINS):
            return False
    return True


# ---------------------------------------------------------------------------
# Hard exclusion check
# ---------------------------------------------------------------------------

def _is_hard_excluded(title: str, body: str, categories: list[dict]) -> bool:
    """Return True if the article must be rejected regardless of keyword signals."""
    title_lower = title.lower()
    body_lower = (body or "").lower()

    # Opinion/analysis title prefix
    if _OPINION_PREFIXES.match(title):
        return True

    # Categories are exclusively non-unrest domains
    if _all_excluded_categories(categories):
        return True

    # Weather-only: weather tokens in title with no unrest tokens
    title_tok = _tokens(title)
    if _WEATHER_TOKENS & title_tok:
        unrest_tokens = {"protest", "riot", "unrest", "violence", "clash", "demonstrat"}
        if not (unrest_tokens & title_tok):
            return True

    # Ordinary crime phrases in title (without unrest context)
    for phrase in _ACCIDENT_PHRASES:
        if phrase in title_lower and "protest" not in title_lower and "rally" not in title_lower:
            return True

    return False


# ---------------------------------------------------------------------------
# Main classifier
# ---------------------------------------------------------------------------

def classify(
    title: str,
    body: str | None,
    categories: list[dict],
    concepts: list[dict],
    min_score: float = 0.6,
) -> ClassificationResult | None:
    """
    Classify an article into a Flashpoint event type.

    Returns ClassificationResult or None if the article should be discarded.

    Signals used (in priority order):
      1. Multi-word phrase patterns (highest specificity, highest weight)
      2. Single-token keyword hits in title
      3. Single-token keyword hits in body (lower weight; require title/category/concept support)
      4. ER category boost (+0.2)
      5. ER concept boost (up to +0.3)

    Hard-exclusion rules can reject the article even if keyword signals are strong.
    """
    if not title:
        return None

    body = body or ""

    # --- Hard exclusions first ---
    if _is_hard_excluded(title, body, categories):
        return None

    title_lower = title.lower()
    body_lower = body.lower()
    title_tok = _tokens(title)
    body_tok = _tokens(body)

    # Collect candidate (event_type, score) pairs from all signals
    candidates: dict[str, float] = {}  # event_type → best score seen

    # 1. Phrase matching (title first, then body with penalty)
    for phrase, etype, base_score in _PHRASE_PATTERNS:
        if phrase in title_lower:
            score = base_score
            candidates[etype] = max(candidates.get(etype, 0.0), score)
        elif phrase in body_lower:
            score = base_score * 0.7  # body-only: 30% penalty
            candidates[etype] = max(candidates.get(etype, 0.0), score)

    # 2. Token matching in title
    for token, etype, base_score in _TOKEN_MAP:
        if token in title_tok:
            candidates[etype] = max(candidates.get(etype, 0.0), base_score)

    # 3. Token matching in body — only accepted if supported by category/concept or title signal
    if not candidates:  # only scan body when title found nothing
        cat_boost = _category_boost(categories)
        con_boost = _concept_boost(concepts)
        if cat_boost > 0 or con_boost > 0:
            for token, etype, base_score in _TOKEN_MAP:
                if token in body_tok:
                    score = base_score * 0.55  # body-only with no title hit: heavy penalty
                    candidates[etype] = max(candidates.get(etype, 0.0), score)

    if not candidates:
        return None

    # 4. Apply category and concept boosts to best candidate
    cat_boost = _category_boost(categories)
    con_boost = _concept_boost(concepts)
    total_boost = cat_boost + con_boost

    # Pick highest-scoring candidate
    best_type = max(candidates, key=lambda t: candidates[t])
    best_score = min(1.0, candidates[best_type] + total_boost)

    if best_score < min_score:
        return None

    # Vandalism and crowd_disruption require at least one reinforcing signal when body-only
    if best_type in ("vandalism_tied_to_unrest", "crowd_disruption"):
        if best_type not in {t for phrase, t, _ in _PHRASE_PATTERNS if phrase in title_lower}:
            if cat_boost == 0.0 and con_boost == 0.0:
                # Downgrade ambiguous vandalism/crowd to unrest
                best_type = "unrest"
                best_score = min(best_score, 0.6)

    return ClassificationResult(event_type=best_type, score=best_score)
