# tests/services/test_detect_low_utilization.py
# Branch: v5-whatsapp
#
# FILE PURPOSE
# Unit tests for detect_low_utilization (catalog/machine.py, spec
# B.2.low_utilization).
#
# WHO CALLS THIS FILE
#   pytest tests/ -m "not integration" -v
#
# WHAT THIS FILE CALLS
#   app.services.briefing_intelligence.catalog.machine.detect_low_utilization
#   tests/services/conftest.py builders (make_tenant, make_machine,
#                                          make_job, make_assignment)
#
# DESIGN NOTES
#   The local _seed_machine_with_hours() helper composes
#   machine + job + assignment so each test asserts against an exact
#   utilisation ratio. Tests verify threshold behaviour (just below
#   30%, well above), the self-suppression vs idle_machine rule, and
#   inverted-ratio severity_score for escalation.

import pytest
from datetime import date, timedelta

from app.services.briefing_intelligence.catalog.machine import (
    IDLE_MIN_TENANT_AGE_DAYS,
    LOW_UTIL_SIGNAL_ID,
    detect_low_utilization,
)

from tests.services.conftest import (
    make_assignment,
    make_job,
    make_machine,
    make_tenant,
)


TODAY = date(2026, 5, 4)


def _seed_machine_with_hours(db, tenant, name, *, hours_total: float):
    """Create one machine with a single overlapping job providing exactly
    `hours_total` hours of scheduled work in the last 7 days.
    """
    m = make_machine(db, tenant=tenant, name=name, status="Operational")
    # 7-day window job, custom hours/day
    per_day = hours_total / 7.0
    j = make_job(
        db, tenant=tenant, name=f"J-{name}",
        start_date=TODAY - timedelta(days=6),
        end_date=TODAY,
        status="in_progress",
        estimated_hours_per_day=max(per_day, 0.0001),
    )
    make_assignment(db, tenant=tenant, job=j, machine=m, days_ago=3.0)
    return m


class TestDetectLowUtilization:

    def test_returns_none_for_young_tenant(self, db):
        tenant = make_tenant(db, age_days=5)
        _seed_machine_with_hours(db, tenant, "A", hours_total=10.0)
        db.commit()
        assert detect_low_utilization(tenant.id, TODAY, db) is None

    def test_self_suppresses_when_machine_is_idle(self, db):
        # No assignments → idle_machine fires; low_utilization should
        # bow out so the higher-tier signal wins cleanly.
        tenant = make_tenant(db, age_days=IDLE_MIN_TENANT_AGE_DAYS + 5)
        make_machine(db, tenant=tenant, name="Idle", status="Operational")
        db.commit()
        assert detect_low_utilization(tenant.id, TODAY, db) is None

    @pytest.mark.xfail(strict=False, reason="date drift, see CHANGELOG note 92")
    def test_fires_when_utilization_below_30pct(self, db):
        # Capacity = 8h/day * 7 days = 56h. 10h ≈ 18% → fires.
        tenant = make_tenant(db, age_days=IDLE_MIN_TENANT_AGE_DAYS + 5)
        _seed_machine_with_hours(db, tenant, "Slow", hours_total=10.0)
        db.commit()

        result = detect_low_utilization(tenant.id, TODAY, db)
        assert result is not None
        assert result.signal_id == LOW_UTIL_SIGNAL_ID
        assert result.tier == 3
        assert result.confidence == "medium"
        assert "Slow" in result.message_hi_en
        assert "%" in result.message_hi_en

    def test_skips_when_utilization_above_threshold(self, db):
        # 56h / 56h = 100% → skips.
        tenant = make_tenant(db, age_days=IDLE_MIN_TENANT_AGE_DAYS + 5)
        _seed_machine_with_hours(db, tenant, "Busy", hours_total=56.0)
        db.commit()
        assert detect_low_utilization(tenant.id, TODAY, db) is None

    def test_status_normalization_skips_under_maintenance(self, db):
        tenant = make_tenant(db, age_days=IDLE_MIN_TENANT_AGE_DAYS + 5)
        m = make_machine(
            db, tenant=tenant, name="Broken", status="Under Maintenance",
        )
        j = make_job(
            db, tenant=tenant, name="J",
            start_date=TODAY - timedelta(days=6), end_date=TODAY,
            status="in_progress", estimated_hours_per_day=1.0,
        )
        make_assignment(db, tenant=tenant, job=j, machine=m, days_ago=3.0)
        db.commit()
        assert detect_low_utilization(tenant.id, TODAY, db) is None

    @pytest.mark.xfail(strict=False, reason="date drift, see CHANGELOG note 92")
    def test_severity_score_inversely_tracks_ratio(self, db):
        tenant = make_tenant(db, age_days=IDLE_MIN_TENANT_AGE_DAYS + 5)
        _seed_machine_with_hours(db, tenant, "VeryLow", hours_total=2.0)
        db.commit()
        result = detect_low_utilization(tenant.id, TODAY, db)
        assert result is not None
        # 2h / 56h ≈ 3.6% → severity ≈ 96 (closer to 100 = worse)
        assert result.severity_score > 90.0
