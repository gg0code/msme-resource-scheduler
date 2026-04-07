# backend/tests/test_conflict_detection.py
# Unit tests for the _has_scheduling_conflict function used by
# dashboard.py and gantt.py.
#
# This is the unified conflict detection logic that replaced the
# availability engine approach. Tests verify it gives the same answer
# as the Jobs page for all states.

import pytest
from datetime import date
from unittest.mock import MagicMock


# Import the shared function from dashboard.py
# (gantt.py has an identical copy)
from app.routers.dashboard import _has_scheduling_conflict


def make_job(
    start: str = "2026-04-13",
    end: str = "2026-04-20",
    orig_start: str = None,
    orig_end: str = None,
) -> MagicMock:
    """Create a mock Job object with the given dates."""
    job = MagicMock()
    job.id = 1
    job.start_date = date.fromisoformat(start)
    job.end_date   = date.fromisoformat(end)
    job.original_start_date = date.fromisoformat(orig_start) if orig_start else None
    job.original_end_date   = date.fromisoformat(orig_end)   if orig_end   else None
    return job


class TestNoEntriesYet:
    def test_not_conflicted_when_no_entries(self):
        """Job with no schedule entries is not conflicted — just not yet scheduled."""
        job = make_job()
        has_conflict, reasons = _has_scheduling_conflict(job, entry_count_map={})
        assert has_conflict is False
        assert reasons == []


class TestFullyScheduled:
    def test_no_conflict_when_all_days_scheduled(self):
        """8-day job with 8 entries has no conflict."""
        job = make_job("2026-04-13", "2026-04-20")
        # 8 days (Apr 13-20 inclusive)
        has_conflict, reasons = _has_scheduling_conflict(job, {1: 8})
        assert has_conflict is False

    def test_no_conflict_uses_original_dates_for_count(self):
        """Conflict check uses original dates (user request), not rescheduled dates."""
        # Job was originally 8 days (Apr 13-20) but scheduler moved end to Apr 28
        job = make_job(
            start="2026-04-13", end="2026-04-28",
            orig_start="2026-04-13", orig_end="2026-04-20"
        )
        # 8 entries = matches original 8 days = no conflict
        has_conflict, _ = _has_scheduling_conflict(job, {1: 8})
        assert has_conflict is False

    def test_conflict_when_entries_less_than_original(self):
        """Job with 3 entries out of original 8 days IS conflicted."""
        job = make_job(
            start="2026-04-13", end="2026-04-28",
            orig_start="2026-04-13", orig_end="2026-04-20"
        )
        has_conflict, reasons = _has_scheduling_conflict(job, {1: 3})
        assert has_conflict is True
        assert len(reasons) == 1
        assert "5 of 8" in reasons[0]  # 8-3=5 missing days


class TestPartiallyScheduled:
    def test_conflict_when_missing_days(self):
        """Job with fewer entries than expected days is conflicted."""
        job = make_job("2026-04-13", "2026-04-20")  # 8 days
        has_conflict, reasons = _has_scheduling_conflict(job, {1: 5})
        assert has_conflict is True
        assert "3 of 8" in reasons[0]  # 8-5=3 missing

    def test_conflict_message_is_actionable(self):
        """Conflict reason tells user to run Auto-Schedule."""
        job = make_job("2026-04-13", "2026-04-20")
        _, reasons = _has_scheduling_conflict(job, {1: 4})
        assert "Auto-Schedule" in reasons[0] or "auto-schedule" in reasons[0].lower()


class TestEdgeCases:
    def test_single_day_job_fully_scheduled(self):
        """1-day job with 1 entry has no conflict."""
        job = make_job("2026-04-13", "2026-04-13")
        has_conflict, _ = _has_scheduling_conflict(job, {1: 1})
        assert has_conflict is False

    def test_single_day_job_not_scheduled(self):
        """1-day job with 0 entries is not conflicted (just unscheduled)."""
        job = make_job("2026-04-13", "2026-04-13")
        has_conflict, _ = _has_scheduling_conflict(job, {})
        assert has_conflict is False

    def test_job_not_in_map_not_conflicted(self):
        """Job ID not present in map (no entries) — not conflicted."""
        job = make_job("2026-04-13", "2026-04-20")
        has_conflict, _ = _has_scheduling_conflict(job, {999: 5})
        assert has_conflict is False
