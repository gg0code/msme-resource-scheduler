# tests/test_message_formatters.py
# Branch: v5-whatsapp
# Iteration: v6.3.18 (WhatsApp message styling pass)
#
# FILE PURPOSE
# Unit tests for the four pure formatters added in v6.3.18:
#   format_jobs_list, format_employee_status, format_relative_date,
#   format_machine_status. Plus the legacy markdown post-processor that
#   was folded from whatsapp_formatter.py into message_formatters.py.
#
# WHO CALLS THIS FILE
# - pytest tests/ -m "not integration" (the v6.3.18 verification gate).
#
# WHAT THIS FILE CALLS
# - app/services/message_formatters.py — the module under test.
#
# AC IDs covered (per CLAUDE.md naming convention):
#   23-AC2  format_relative_date uses Asia/Kolkata day boundaries.
# Tests not tied to a specific numbered AC carry no AC prefix; they
# guard structural behaviour discovered while implementing the formatters.

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Optional
from zoneinfo import ZoneInfo

import pytest

from app.services.message_formatters import (
    format_employee_status,
    format_for_whatsapp,
    format_jobs_list,
    format_machine_status,
    format_relative_date,
)


# ---------------------------------------------------------------------------
# Fixtures (simple dataclasses matching the structural protocols)
# ---------------------------------------------------------------------------

@dataclass
class JobFix:
    name: Optional[str]
    end_date: Optional[date] = None


@dataclass
class EmpFix:
    full_name: str
    is_present: bool
    primary_skill: Optional[str] = None
    is_contractor: bool = False


@dataclass
class MachineFix:
    name: str
    status: str
    current_job: Optional[str] = None


IST = ZoneInfo("Asia/Kolkata")


# ===========================================================================
# format_jobs_list
# ===========================================================================

class TestFormatJobsList:
    """Truncation, due-date suffix, name fallbacks."""

    def test_empty_list_returns_empty_string(self) -> None:
        assert format_jobs_list([]) == ""

    def test_renders_each_job_as_dash_prefix_line(self) -> None:
        out = format_jobs_list([JobFix(name="Bhatia cards"), JobFix(name="Modi flyers")])
        assert out == "- Bhatia cards\n- Modi flyers"

    def test_due_date_suffix_when_end_date_present(self) -> None:
        out = format_jobs_list([JobFix(name="Bhatia cards", end_date=date(2026, 5, 12))])
        assert out == "- Bhatia cards (due: 2026-05-12)"

    def test_truncation_at_max_items_appends_more_tail(self) -> None:
        jobs = [JobFix(name=f"Job {i}") for i in range(7)]
        out = format_jobs_list(jobs, max_items=5)
        lines = out.split("\n")
        assert len(lines) == 6
        assert lines[-1] == "+2 more"
        assert lines[0] == "- Job 0"
        assert lines[4] == "- Job 4"

    def test_no_truncation_when_below_max(self) -> None:
        jobs = [JobFix(name=f"Job {i}") for i in range(3)]
        out = format_jobs_list(jobs, max_items=5)
        assert "+0 more" not in out
        assert "more" not in out

    def test_blank_or_none_name_falls_back_to_untitled(self) -> None:
        out = format_jobs_list([JobFix(name=None), JobFix(name="   ")])
        # Neither blank nor None should produce "- " or "-  "; both
        # should produce a stable fallback.
        for line in out.split("\n"):
            assert line.startswith("- "), f"line shape broken: {line!r}"
            assert "Untitled" in line


# ===========================================================================
# format_employee_status
# ===========================================================================

class TestFormatEmployeeStatus:
    """Presence flag, skill rendering, contractor tag."""

    def test_present_with_skill(self) -> None:
        out = format_employee_status(
            EmpFix(full_name="Ravi Kumar", is_present=True, primary_skill="Cutting")
        )
        assert out == "Ravi Kumar — present, Cutting"

    def test_absent_no_skill(self) -> None:
        out = format_employee_status(
            EmpFix(full_name="Sita Devi", is_present=False, primary_skill=None)
        )
        assert out == "Sita Devi — absent"

    def test_contractor_tag_appended(self) -> None:
        out = format_employee_status(
            EmpFix(full_name="Anil", is_present=True, primary_skill="Welding", is_contractor=True)
        )
        assert out == "Anil — present, Welding (contractor)"

    def test_blank_name_falls_back(self) -> None:
        out = format_employee_status(EmpFix(full_name="", is_present=True))
        assert out.startswith("Unnamed")


# ===========================================================================
# format_machine_status
# ===========================================================================

class TestFormatMachineStatus:
    def test_with_current_job(self) -> None:
        out = format_machine_status(
            MachineFix(name="Heidelberg 1", status="Operational", current_job="Bhatia cards")
        )
        assert out == "Heidelberg 1 — Operational, running Bhatia cards"

    def test_without_current_job(self) -> None:
        out = format_machine_status(
            MachineFix(name="Cutter 3", status="Maintenance", current_job=None)
        )
        assert out == "Cutter 3 — Maintenance"

    def test_blank_status_renders_unknown(self) -> None:
        out = format_machine_status(MachineFix(name="Press 2", status=""))
        assert out == "Press 2 — Unknown"


# ===========================================================================
# format_relative_date — AC 23-AC2 (Asia/Kolkata day boundaries)
# ===========================================================================

class TestFormatRelativeDate:
    """AC 23-AC2: use IST calendar-day deltas, not 24-hour deltas."""

    def test_23_ac2_today(self) -> None:
        now_ = datetime(2026, 5, 8, 9, 0, tzinfo=IST)
        assert format_relative_date(now_, now=now_) == "today"

    def test_23_ac2_tomorrow(self) -> None:
        now_ = datetime(2026, 5, 8, 9, 0, tzinfo=IST)
        target = datetime(2026, 5, 9, 9, 0, tzinfo=IST)
        assert format_relative_date(target, now=now_) == "tomorrow"

    def test_23_ac2_yesterday(self) -> None:
        now_ = datetime(2026, 5, 8, 9, 0, tzinfo=IST)
        target = datetime(2026, 5, 7, 9, 0, tzinfo=IST)
        assert format_relative_date(target, now=now_) == "yesterday"

    def test_23_ac2_in_n_days(self) -> None:
        now_ = datetime(2026, 5, 8, 9, 0, tzinfo=IST)
        target = datetime(2026, 5, 11, 9, 0, tzinfo=IST)
        assert format_relative_date(target, now=now_) == "in 3 days"

    def test_23_ac2_n_days_ago(self) -> None:
        now_ = datetime(2026, 5, 8, 9, 0, tzinfo=IST)
        target = datetime(2026, 5, 3, 9, 0, tzinfo=IST)
        assert format_relative_date(target, now=now_) == "5 days ago"

    def test_23_ac2_ist_day_boundary_not_24h_delta(self) -> None:
        """23:30 IST vs 00:30 IST next day = 1 hour later, but a different IST
        calendar day -> "tomorrow", not "today". This is the assertion
        the 24-hour-delta naive implementation gets wrong."""
        late_today = datetime(2026, 5, 8, 23, 30, tzinfo=IST)
        early_tomorrow = datetime(2026, 5, 9, 0, 30, tzinfo=IST)
        assert format_relative_date(early_tomorrow, now=late_today) == "tomorrow"

    def test_23_ac2_utc_input_converts_through_ist(self) -> None:
        """A UTC timestamp passed in is converted to IST first (IST = UTC+5:30).
        2026-05-08 23:00 UTC = 2026-05-09 04:30 IST = "tomorrow" relative
        to 2026-05-08 09:00 IST anchor."""
        utc = ZoneInfo("UTC")
        target = datetime(2026, 5, 8, 23, 0, tzinfo=utc)
        anchor = datetime(2026, 5, 8, 9, 0, tzinfo=IST)
        assert format_relative_date(target, now=anchor) == "tomorrow"

    def test_naive_datetimes_treated_as_ist(self) -> None:
        """Documented behaviour: naive datetimes are interpreted as IST
        local time (project default per SRS §17.3)."""
        target = datetime(2026, 5, 9, 10, 0)  # naive
        anchor = datetime(2026, 5, 8, 10, 0)  # naive
        assert format_relative_date(target, now=anchor) == "tomorrow"


# ===========================================================================
# format_for_whatsapp — folded legacy surface (regression coverage)
# ===========================================================================

class TestFormatForWhatsapp:
    """Sanity that the v5.0 markdown post-processor still works after the
    v6.3.18 fold from whatsapp_formatter.py into message_formatters.py."""

    def test_strips_bold_markers(self) -> None:
        assert format_for_whatsapp("**hello** world") == "hello world"

    def test_converts_dash_bullets_to_bullet_glyphs(self) -> None:
        out = format_for_whatsapp("- one\n- two")
        assert "• one" in out
        assert "• two" in out

    def test_empty_input_returns_safe_fallback(self) -> None:
        out = format_for_whatsapp("")
        assert out  # non-empty
        assert "try" in out.lower() or "kuch" in out.lower()

    def test_hindi_passthrough_no_mangling(self) -> None:
        """AC 11 voice/tone: Hindi-script input must round-trip without
        unicode mangling. format_for_whatsapp only strips markdown; it
        must leave Devanagari bytes alone."""
        hindi = "नमस्ते — आज का काम तैयार है।"
        out = format_for_whatsapp(hindi)
        assert hindi == out
