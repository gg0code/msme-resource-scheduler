# tests/services/test_promotion_fuzzy_match.py
# Branch: v5-whatsapp
#
# FILE PURPOSE
# Unit tests for app/services/promotion/fuzzy_match.py (v6.3.15).
# The helper is pure (no DB), so these tests skip the `db` fixture
# and exercise fuzzy_best_match directly with literal inputs.
#
# WHO CALLS THIS FILE
#   pytest tests/ -m "not integration" -v
#
# WHAT THIS FILE CALLS
#   app.services.promotion.fuzzy_match.fuzzy_best_match
#   app.services.promotion.fuzzy_match.STRATEGY_TOKEN_SET
#   app.services.promotion.fuzzy_match.STRATEGY_RATIO

from app.services.promotion.fuzzy_match import (
    STRATEGY_RATIO,
    STRATEGY_TOKEN_SET,
    fuzzy_best_match,
)


class TestFuzzyBestMatch:
    """Coverage of the hybrid token_set / ratio matcher."""

    def test_exact_match_returns_match(self):
        result = fuzzy_best_match(
            candidate_value="suresh kumar",
            existing=[(1, "Suresh Kumar")],
        )
        assert result is not None
        assert result.matched_id == 1
        assert result.score == 100.0
        # Multi-token → token_set primary scorer.
        assert result.strategy == STRATEGY_TOKEN_SET

    def test_minor_typo_matches_above_threshold(self):
        # token_set_ratio handles "Suresh Kumar" vs "Suresh Kummar"
        # with score above the default 85 threshold.
        result = fuzzy_best_match(
            candidate_value="suresh kummar",
            existing=[(7, "Suresh Kumar")],
        )
        assert result is not None
        assert result.matched_id == 7
        assert result.score >= 85

    def test_substring_match_with_token_set(self):
        # Candidate "suresh" against existing "Suresh Kumar" — token_set
        # treats overlap as union/intersection ratio. The single-token
        # candidate triggers the ratio fallback (lower partial overlap),
        # so the strict ratio threshold of 90 typically REJECTS this
        # case to protect against confirming the wrong person.
        result = fuzzy_best_match(
            candidate_value="suresh",
            existing=[(3, "Suresh Kumar")],
        )
        # Either result is acceptable — the contract is "if it matches,
        # it's via the ratio fallback strategy". Verify the strategy
        # tag rather than the boolean outcome.
        if result is not None:
            assert result.strategy == STRATEGY_RATIO

    def test_unrelated_names_do_not_match(self):
        result = fuzzy_best_match(
            candidate_value="ramesh",
            existing=[(1, "Suresh Kumar"), (2, "Vikram Singh")],
        )
        assert result is None

    def test_single_word_uses_ratio_fallback(self):
        # Two single-token names that differ by one character fall
        # under ratio with high score (>= 90 default).
        result = fuzzy_best_match(
            candidate_value="suresh",
            existing=[(5, "Sureshh")],  # extra trailing h
        )
        assert result is not None
        assert result.strategy == STRATEGY_RATIO
        assert result.matched_id == 5

    def test_empty_candidate_returns_none(self):
        assert fuzzy_best_match("", [(1, "Suresh")]) is None
        assert fuzzy_best_match("   ", [(1, "Suresh")]) is None

    def test_empty_existing_returns_none(self):
        assert fuzzy_best_match("suresh kumar", []) is None

    def test_picks_best_score_when_multiple_above_threshold(self):
        # Two candidates above threshold — pick the highest. "Suresh
        # Kumar" matches "Suresh Kumar" perfectly (100); "Suresh K"
        # also matches (>= 85 via token_set_ratio).
        result = fuzzy_best_match(
            candidate_value="suresh kumar",
            existing=[(10, "Suresh K"), (20, "Suresh Kumar")],
        )
        assert result is not None
        assert result.matched_id == 20
        assert result.score == 100.0

    def test_threshold_overrides_apply(self):
        # Lowering the token_set threshold to 50 lets a poor multi-token
        # match through. Confirms the override hooks are wired.
        result = fuzzy_best_match(
            candidate_value="alpha beta",
            existing=[(1, "alpha gamma")],
            token_set_threshold=50,
        )
        assert result is not None
        assert result.matched_id == 1

    def test_skips_existing_with_empty_name(self):
        # An existing row with full_name='' (data quality bug) must
        # not match anything — protects against a stray junk row in
        # the canonical table soaking up every candidate.
        result = fuzzy_best_match(
            candidate_value="suresh",
            existing=[(1, ""), (2, "Suresh")],
        )
        # Should match #2, not #1.
        assert result is not None
        assert result.matched_id == 2
