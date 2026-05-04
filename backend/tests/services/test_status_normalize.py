# tests/services/test_status_normalize.py
# Branch: v5-whatsapp
#
# FILE PURPOSE
# Unit tests for app/services/status_normalize.py — case-insensitive
# membership shared by every v6.3.11 evaluator.
#
# WHO CALLS THIS FILE
#   pytest tests/ -m "not integration" -v
#
# WHAT THIS FILE CALLS
#   app.services.status_normalize.status_in
#
# DESIGN NOTES
#   No DB or fixtures required — status_in is a pure string helper, so
#   each test calls it directly and asserts on the boolean result.

from app.services.status_normalize import status_in


class TestStatusIn:

    def test_exact_match(self):
        assert status_in("completed", {"completed", "cancelled"}) is True

    def test_titlecase_input_matches_lowercase_candidate(self):
        assert status_in("Completed", {"completed", "cancelled"}) is True

    def test_lowercase_input_matches_titlecase_candidate(self):
        assert status_in("operational", {"Operational"}) is True

    def test_whitespace_trimmed(self):
        assert status_in("  in_progress  ", {"in_progress"}) is True

    def test_none_returns_false(self):
        assert status_in(None, {"completed"}) is False

    def test_empty_string_returns_false(self):
        assert status_in("", {"completed"}) is False

    def test_non_string_returns_false(self):
        assert status_in(123, {"completed"}) is False  # type: ignore[arg-type]

    def test_non_member_returns_false(self):
        assert status_in("Pending", {"completed"}) is False

    def test_candidate_casing_normalised_too(self):
        # Caller passed mixed-case candidates; needle still matches.
        assert status_in("active", {"Active", "Inactive"}) is True
