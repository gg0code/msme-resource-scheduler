# app/services/status_normalize.py
# Branch: v5-whatsapp
#
# FILE PURPOSE
# Case-insensitive status comparison helper for the v6.3.11 pattern
# briefing evaluators. Centralises the "lowercase + trim then test set
# membership" idiom so evaluators do not enumerate variants
# ('completed' / 'Completed' / ...) per query.
#
# Spec ref: v6_3_11_signals_spec.md Section C "Status field reality
# check" — Q6 chose Option (b) application-level comparison.
#
# WHO CALLS THIS FILE
# - app/services/briefing_intelligence/catalog/attendance.py
# - app/services/briefing_intelligence/catalog/customer.py
# - app/services/briefing_intelligence/catalog/health.py
# - app/services/briefing_intelligence/catalog/job.py
# - app/services/briefing_intelligence/catalog/machine.py
# - app/services/briefing_intelligence/catalog/tenancy.py
# - tests/test_status_normalize.py
#
# WHAT THIS FILE CALLS
# - typing.Iterable — type hint only
#
# DESIGN NOTES
# - status_in() is the only public surface. It is intentionally tiny
#   so callers cannot drift into bespoke comparisons.
# - None / non-string statuses return False. The contract is "match
#   when value is in candidates" — None matches nothing.
# - Candidate strings are normalised at call time, NOT cached, so a
#   caller that passes a frozenset with mixed casing still works.
# - The evaluator pattern is `if status_in(machine.status, IDLE_OK):`
#   — never `machine.status.lower() in ...` (rejects None) and never
#   `machine.status in TUPLE_OF_VARIANTS` (the bug Section C
#   documents).

from typing import Iterable, Optional


def status_in(value: Optional[str], candidates: Iterable[str]) -> bool:
    """Case-insensitive membership test against a set of canonical
    status strings.

    Called by:    every v6.3.11 signal evaluator that filters on
                  status fields (attendance, machine, customer, health,
                  job, tenancy catalogs).
    Calls into:   nothing — pure string ops.
    Side effects: none.

    Args:
        value:      A status column value. May be None, mixed case,
                    surrounded by whitespace.
        candidates: Iterable of canonical status strings the caller
                    treats as a positive match. Casing of candidates
                    is also normalised so callers can pass either
                    'completed' or 'Completed' freely.

    Returns:
        True iff `value` (after lowercasing + stripping) equals any
        candidate (after the same normalisation). False when value
        is None / not a string / empty.
    """
    if not isinstance(value, str):
        return False
    needle = value.strip().lower()
    if not needle:
        return False
    return needle in {c.strip().lower() for c in candidates}
