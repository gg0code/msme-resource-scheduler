# tests/services/test_detect_recurring_customer.py
# Branch: v5-whatsapp
#
# FILE PURPOSE
# Unit tests for detect_recurring_customer (catalog/customer.py, spec
# B.4.recurring_customer_callout).
#
# WHO CALLS THIS FILE
#   pytest tests/ -m "not integration" -v
#
# WHAT THIS FILE CALLS
#   app.services.briefing_intelligence.catalog.customer.detect_recurring_customer
#   tests/services/conftest.py builders (make_tenant, make_job)
#
# DESIGN NOTES
#   Covers the day-marker gate (only fires on tenant ages 7/14/21/30),
#   case-insensitive customer-name bucketing, terminal-status skip,
#   and the 30-day creation window.

from datetime import date, timedelta

from app.services.briefing_intelligence.catalog.customer import (
    RECURRING_DAY_MARKERS,
    RECURRING_SIGNAL_ID,
    detect_recurring_customer,
)

from tests.services.conftest import make_job, make_tenant


TODAY = date(2026, 5, 4)


def _job_with_customer(db, tenant, name, customer, *, status="in_progress",
                        created_days_ago=5.0):
    """Insert one Job tied to `customer` with default mid-window dates.

    Called by:    every test in this file.
    Calls into:   make_job (tests/services/conftest.py).
    Side effects: stages a Job row via the test session.
    """
    return make_job(
        db, tenant=tenant, name=name, customer=customer,
        start_date=TODAY - timedelta(days=2),
        end_date=TODAY + timedelta(days=2),
        status=status,
        created_days_ago=created_days_ago,
    )


class TestDetectRecurringCustomer:

    def test_returns_none_off_marker_days(self, db):
        # Tenant aged 3 days — not in {7, 14, 21, 30}.
        tenant = make_tenant(db, age_days=3, today=TODAY)
        for i in range(4):
            _job_with_customer(db, tenant, f"J{i}", "Cipla")
        db.commit()
        assert detect_recurring_customer(tenant.id, TODAY, db) is None

    def test_fires_on_day_7_marker(self, db):
        assert 7 in RECURRING_DAY_MARKERS
        tenant = make_tenant(db, age_days=7, today=TODAY)
        for i in range(3):
            _job_with_customer(db, tenant, f"Job-{i}", "Cipla")
        db.commit()
        result = detect_recurring_customer(tenant.id, TODAY, db)
        assert result is not None
        assert result.signal_id == RECURRING_SIGNAL_ID
        assert result.tier == 2
        assert "Cipla" in result.message_hi_en
        assert result.severity_score == 3.0

    def test_returns_none_below_min_jobs(self, db):
        tenant = make_tenant(db, age_days=7, today=TODAY)
        _job_with_customer(db, tenant, "A", "Cipla")
        _job_with_customer(db, tenant, "B", "Cipla")
        db.commit()
        assert detect_recurring_customer(tenant.id, TODAY, db) is None

    def test_normalises_customer_name_casing(self, db):
        tenant = make_tenant(db, age_days=7, today=TODAY)
        _job_with_customer(db, tenant, "A", "cipla")
        _job_with_customer(db, tenant, "B", "CIPLA")
        _job_with_customer(db, tenant, "C", "Cipla")
        db.commit()
        result = detect_recurring_customer(tenant.id, TODAY, db)
        assert result is not None
        assert result.severity_score == 3.0

    def test_skips_terminal_status_jobs(self, db):
        tenant = make_tenant(db, age_days=7, today=TODAY)
        _job_with_customer(db, tenant, "Done1", "Cipla", status="Completed")
        _job_with_customer(db, tenant, "Done2", "Cipla", status="completed")
        _job_with_customer(db, tenant, "Active", "Cipla", status="in_progress")
        db.commit()
        # Only 1 active → below threshold
        assert detect_recurring_customer(tenant.id, TODAY, db) is None

    def test_skips_jobs_outside_30d_window(self, db):
        tenant = make_tenant(db, age_days=7, today=TODAY)
        _job_with_customer(db, tenant, "Old", "Cipla", created_days_ago=40)
        _job_with_customer(db, tenant, "Recent1", "Cipla", created_days_ago=2)
        _job_with_customer(db, tenant, "Recent2", "Cipla", created_days_ago=1)
        db.commit()
        # 2 in window → below threshold
        assert detect_recurring_customer(tenant.id, TODAY, db) is None
