# tests/services/test_detector_date_anchoring.py
# Branch: v5-whatsapp
#
# FILE PURPOSE
# v6.3.19.1 slice 3A verification harness — proves the detector
# pipeline is robust against wall-clock drift. Parametrises the
# frozen `now()` across a 90-day span and runs one representative
# detector at each anchor, asserting identical behaviour.
#
# The slice 3A fix added a `freeze_time(_DETECTOR_TEST_TODAY)`
# autouse fixture in tests/services/conftest.py that pins
# datetime.now() to date(2026, 5, 4) — the same TODAY constant the
# detector tests hardcode. This file overrides that autouse with a
# parametrised local freeze to prove the detector logic is anchor-
# independent: whatever date we freeze to, if the test passes its
# matching `today` argument to the detector, the assertion holds.
#
# What this guards against
# ------------------------
# CHANGELOG note 92 root cause: fixture builders use datetime.now()
# while detectors take an explicit `today` parameter. If a future
# refactor accidentally swaps the detector's `today` parameter back
# to a date.today() call (or otherwise reintroduces wall-clock
# coupling), this harness catches it at every parametrised date.
#
# WHO CALLS THIS FILE
# - pytest under the unit tier ("not integration" mark).
#
# WHAT THIS FILE CALLS
# - freezegun.freeze_time as a context manager (overrides the
#   conftest autouse on a per-test basis).
# - detect_delayed_jobs as one representative detector; the slice
#   3A conftest freeze covers every detector test, but this file
#   only exercises one to keep the matrix bounded.
# - tests/services/conftest.py builders for fixture setup.

from datetime import date, timedelta

import pytest
from freezegun import freeze_time

from app.services.briefing_intelligence.catalog.job import detect_delayed_jobs

from tests.services.conftest import make_job, make_tenant


# 13 anchor dates across a 90-day window. Includes the canonical
# TODAY (2026-05-04) and the surrounding calendar to catch any
# month / quarter boundary drift.
_NINETY_DAY_ANCHORS = [
    "2026-01-15",
    "2026-02-01",
    "2026-02-28",
    "2026-03-01",
    "2026-03-15",
    "2026-04-01",
    "2026-04-15",
    "2026-05-04",   # canonical TODAY
    "2026-05-15",
    "2026-06-01",
    "2026-06-15",
    "2026-07-01",
    "2026-07-15",
]


@pytest.mark.parametrize("frozen_today_str", _NINETY_DAY_ANCHORS)
def test_detect_delayed_jobs_anchor_invariant(db, frozen_today_str):
    """detect_delayed_jobs fires identically regardless of frozen `now()`,
    provided the test passes the matching `today` argument.

    Setup at each anchor:
      - Tenant created `today - 30 days`.
      - Job with end_date = `today - 1 day` (delayed by one day).
      - Job with end_date = `today + 1 day` (not delayed).

    Expectation: the detector returns a SignalResult with severity 1.0
    (count of delayed jobs) at every anchor. If a future regression
    couples the detector back to wall-clock now(), this assertion fails
    at every anchor whose distance from real-today exceeds the
    detector's window.
    """
    today = date.fromisoformat(frozen_today_str)

    with freeze_time(frozen_today_str):
        # Tenant set up here so its created_at is also pinned to the
        # frozen now() — matches the production invariant.
        tenant = make_tenant(db, age_days=30, today=today)

        # One overdue job, one on-time job.
        make_job(
            db, tenant=tenant, name="Overdue",
            start_date=today - timedelta(days=10),
            end_date=today - timedelta(days=1),
            status="in_progress",
        )
        make_job(
            db, tenant=tenant, name="OnTrack",
            start_date=today - timedelta(days=2),
            end_date=today + timedelta(days=1),
            status="in_progress",
        )
        db.commit()

        result = detect_delayed_jobs(tenant.id, today, db)

    assert result is not None, (
        f"Anchor {frozen_today_str}: detect_delayed_jobs returned None "
        f"despite one job overdue by one day"
    )
    assert result.severity_score == 1.0, (
        f"Anchor {frozen_today_str}: expected severity_score=1.0, got "
        f"{result.severity_score}"
    )
    assert result.signal_id == "delayed_jobs_count"


@pytest.mark.parametrize("frozen_today_str", _NINETY_DAY_ANCHORS)
def test_detect_delayed_jobs_quiet_when_no_overdue(db, frozen_today_str):
    """Detector returns None at every anchor when no overdue jobs
    exist. Locks the negative-case anchor-invariance."""
    today = date.fromisoformat(frozen_today_str)

    with freeze_time(frozen_today_str):
        tenant = make_tenant(db, age_days=30, today=today)
        make_job(
            db, tenant=tenant, name="Future",
            start_date=today + timedelta(days=1),
            end_date=today + timedelta(days=3),
            status="scheduled",
        )
        db.commit()

        result = detect_delayed_jobs(tenant.id, today, db)

    assert result is None, (
        f"Anchor {frozen_today_str}: detect_delayed_jobs fired despite "
        f"no overdue jobs (got severity={result.severity_score})"
    )
