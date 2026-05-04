# tests/services/test_detect_revenue_at_risk.py
# Branch: v5-whatsapp
#
# FILE PURPOSE
# Unit tests for detect_revenue_at_risk (catalog/customer.py, spec
# B.4.revenue_at_risk).
#
# WHO CALLS THIS FILE
#   pytest tests/ -m "not integration" -v
#
# WHAT THIS FILE CALLS
#   app.services.briefing_intelligence.catalog.customer.detect_revenue_at_risk
#   tests/services/conftest.py builders (make_tenant, make_job)
#
# DESIGN NOTES
#   Covers the Rs.50,000 threshold, the same-data suppression rule
#   vs detect_delayed_jobs (only fires when len(delayed) > 3), terminal-
#   status skip, and tolerance for null order_value.

from datetime import date, timedelta

from app.services.briefing_intelligence.catalog.customer import (
    REVENUE_SIGNAL_ID,
    REVENUE_THRESHOLD_INR,
    detect_revenue_at_risk,
)

from tests.services.conftest import make_job, make_tenant


TODAY = date(2026, 5, 4)


def _delayed(db, tenant, name, *, value, status="in_progress"):
    """Insert one Job whose end_date is one day in the past (delayed).

    Called by:    every test in this file.
    Calls into:   make_job (tests/services/conftest.py).
    Side effects: stages a Job row via the test session.
    """
    return make_job(
        db, tenant=tenant, name=name,
        start_date=TODAY - timedelta(days=10),
        end_date=TODAY - timedelta(days=1),
        status=status,
        order_value=value,
    )


class TestDetectRevenueAtRisk:

    def test_returns_none_when_no_delayed_jobs(self, db):
        tenant = make_tenant(db)
        make_job(
            db, tenant=tenant, name="Future",
            start_date=TODAY, end_date=TODAY + timedelta(days=2),
            status="in_progress", order_value=100_000.0,
        )
        db.commit()
        assert detect_revenue_at_risk(tenant.id, TODAY, db) is None

    def test_returns_none_below_threshold(self, db):
        tenant = make_tenant(db)
        # Need >3 delayed jobs to bypass same-data suppression.
        for i in range(4):
            _delayed(db, tenant, f"J{i}", value=1_000.0)
        db.commit()
        assert detect_revenue_at_risk(tenant.id, TODAY, db) is None

    def test_fires_when_threshold_crossed_and_more_than_3_jobs(self, db):
        tenant = make_tenant(db)
        for i in range(4):
            _delayed(db, tenant, f"J{i}", value=20_000.0)
        db.commit()
        result = detect_revenue_at_risk(tenant.id, TODAY, db)
        assert result is not None
        assert result.signal_id == REVENUE_SIGNAL_ID
        assert result.tier == 2
        assert "Rs." in result.message_hi_en
        assert result.severity_score >= REVENUE_THRESHOLD_INR

    def test_self_suppresses_when_delayed_jobs_count_is_small(self, db):
        # Spec: when <=3 delayed jobs the delayed_jobs_count signal
        # surfaces them by name; revenue_at_risk must back off.
        tenant = make_tenant(db)
        _delayed(db, tenant, "BigA", value=100_000.0)
        _delayed(db, tenant, "BigB", value=100_000.0)
        db.commit()
        assert detect_revenue_at_risk(tenant.id, TODAY, db) is None

    def test_skips_terminal_status_jobs(self, db):
        tenant = make_tenant(db)
        for i in range(4):
            _delayed(
                db, tenant, f"Done{i}", value=100_000.0, status="Completed",
            )
        db.commit()
        assert detect_revenue_at_risk(tenant.id, TODAY, db) is None

    def test_handles_null_order_value(self, db):
        tenant = make_tenant(db)
        for i in range(4):
            _delayed(db, tenant, f"NoVal{i}", value=None)
        db.commit()
        # All NULL order_value → total = 0 → below threshold → None
        assert detect_revenue_at_risk(tenant.id, TODAY, db) is None
