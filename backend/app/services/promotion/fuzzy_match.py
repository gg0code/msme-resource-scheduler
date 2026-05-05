# app/services/promotion/fuzzy_match.py
# Branch: v5-whatsapp
#
# FILE PURPOSE
# String-similarity helper for the v6.3.15 candidate-promotion job.
# Decides whether an extraction_candidates.normalized_value already
# corresponds to an existing employee or machine row for the same
# tenant. A match short-circuits the insert path and writes an
# extraction.candidate_confirmed audit event instead of duplicating
# an entity.
#
# WHO CALLS THIS FILE
# - app/services/promotion/promoter.py — for every qualifying
#   candidate, promoter calls fuzzy_best_match against the candidate's
#   tenant's existing entities of the same type.
# - app/services/promotion/__init__.py — re-exports fuzzy_best_match.
# - backend/tests/services/test_promotion_fuzzy_match.py — direct
#   unit tests against the helper.
#
# WHAT THIS FILE CALLS
# - rapidfuzz.fuzz.token_set_ratio (primary scorer)
# - rapidfuzz.fuzz.ratio          (single-token fallback scorer)
#
# DESIGN NOTES (Q1, Q9)
# - Hybrid strategy chosen to balance romanisation tolerance against
#   false positives:
#     * Multi-token candidate ("Suresh Kumar") → token_set_ratio,
#       which treats the strings as bags of tokens and ignores order
#       and duplicates. Cutoff defaults to PROMOTION_FUZZY_MATCH_THRESHOLD
#       (85) per app/config.py.
#     * Single-token candidate ("Suresh") → plain ratio at the
#       higher cutoff PROMOTION_RATIO_FALLBACK_THRESHOLD (90).
#       token_set_ratio degenerates on single tokens (one-token sets
#       trivially overlap or trivially don't), so we fall back to a
#       conservative character-level metric.
# - Idempotency (Q9) for the promotion job is built ON TOP of this
#   helper: the second nightly run sees the entity inserted by the
#   first run, fuzzy_best_match returns it, the promoter writes a
#   candidate_confirmed event instead of inserting again.
#   Acceptable known edge case: if the owner renames the just-inserted
#   entity by more than the threshold tolerates within 24h (e.g.
#   "Suresh" → "S. Kumar"), the next run treats the candidate as new
#   and inserts a duplicate. Acceptable risk per Q9.
# - Empty / whitespace-only inputs return None (no crash on bad data).
# - Comparison is case-insensitive — both inputs are .lower().strip()ed
#   before scoring.
# - This module is dependency-light on purpose: only rapidfuzz, no
#   tenant/db lookups. Keeping it pure makes it trivially unit-testable
#   without database fixtures.
#
# FORWARD-COMPAT
# - v6.3.x may add an LLM-judged fallback for single-token Indian-name
#   romanisation pairs ("Suresh"/"Soorish") if the 30-day production
#   review (per Q1 operational note) shows duplicate rates above
#   acceptance threshold. The signature here would gain an optional
#   strategy="llm" override; today's hybrid stays the default.

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Optional

from rapidfuzz import fuzz

from app.config import settings


# ---------------------------------------------------------------------------
# Match strategy identifiers — written into the audit event payload so
# log-greppers can correlate which scorer produced the match.
# ---------------------------------------------------------------------------
STRATEGY_TOKEN_SET: str = "token_set_ratio"
STRATEGY_RATIO:     str = "ratio"


@dataclass(frozen=True)
class FuzzyMatch:
    """One match result.

    Used by:    fuzzy_best_match return value; promoter passes this
                directly into the candidate_confirmed event payload.
    Fields:
        candidate_value: The candidate string that was being matched
                         (post-normalisation, as stored in
                         extraction_candidates.normalized_value).
        matched_value:   The existing entity's name (post-normalisation)
                         that scored above threshold.
        matched_id:      The existing entity's primary key. Promoter
                         puts this into the audit event so the row is
                         dereferenceable later.
        score:           Score in [0, 100] from the chosen scorer.
        strategy:        One of STRATEGY_TOKEN_SET / STRATEGY_RATIO.
    """
    candidate_value: str
    matched_value:   str
    matched_id:      int
    score:           float
    strategy:        str


def _normalise(value: str) -> str:
    """Lowercase + strip — the canonical form used for scoring.

    Called by:    fuzzy_best_match.
    Calls into:   stdlib str methods.
    Returns:      Empty string for None / whitespace-only inputs.
    Side effects: none.
    """
    if not value:
        return ""
    return value.strip().lower()


def fuzzy_best_match(
    candidate_value: str,
    existing: Iterable[tuple[int, str]],
    *,
    token_set_threshold: Optional[int] = None,
    ratio_threshold:     Optional[int] = None,
) -> Optional[FuzzyMatch]:
    """Find the highest-scoring existing entity matching `candidate_value`.

    Called by:    app/services/promotion/promoter.py — once per
                  qualifying candidate during the nightly run.
    Calls into:   rapidfuzz.fuzz.token_set_ratio / fuzz.ratio.
    Side effects: none — pure function over the inputs.

    Args:
        candidate_value:     The candidate's normalized_value (already
                             lowercased by the v6.3.14 extractor; we
                             re-normalise defensively).
        existing:            Iterable of (id, name) pairs for entities
                             of the same tenant + same kind already in
                             the canonical table. Promoter passes the
                             SQLAlchemy result rows in.
        token_set_threshold: Cutoff for the multi-token primary scorer.
                             None = read from settings.
        ratio_threshold:     Cutoff for the single-token fallback.
                             None = read from settings.

    Returns:
        The best-scoring FuzzyMatch above the applicable threshold,
        or None when no existing entity scores high enough OR when
        candidate_value is empty / `existing` is empty.

    Why pick "best above threshold" rather than "first above threshold":
        Two existing entities may both score above the cutoff (e.g.
        "Suresh Kumar" and "Suresh Sharma" against candidate "Suresh"
        with token_set_ratio). Taking the highest reduces the chance
        of confirming against the wrong entity; ties go to the first
        encountered in the iteration (deterministic if the caller
        sorts by id).
    """
    cand = _normalise(candidate_value)
    if not cand:
        return None

    if token_set_threshold is None:
        token_set_threshold = settings.PROMOTION_FUZZY_MATCH_THRESHOLD
    if ratio_threshold is None:
        ratio_threshold = settings.PROMOTION_RATIO_FALLBACK_THRESHOLD

    is_single_token = len(cand.split()) == 1
    threshold = ratio_threshold if is_single_token else token_set_threshold
    strategy  = STRATEGY_RATIO if is_single_token else STRATEGY_TOKEN_SET
    scorer    = fuzz.ratio if is_single_token else fuzz.token_set_ratio

    best: Optional[FuzzyMatch] = None
    for entity_id, raw_name in existing:
        existing_norm = _normalise(raw_name)
        if not existing_norm:
            continue
        score = scorer(cand, existing_norm)
        if score < threshold:
            continue
        if best is None or score > best.score:
            best = FuzzyMatch(
                candidate_value=cand,
                matched_value=existing_norm,
                matched_id=entity_id,
                score=float(score),
                strategy=strategy,
            )
    return best
