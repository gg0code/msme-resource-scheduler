# tests/services/test_detect_day_2.py
# Branch: v5-whatsapp
#
# FILE PURPOSE
# Unit tests for detect_day_2 (catalog/tenancy.py, spec
# B.5.day_2_first_observation).
#
# WHO CALLS THIS FILE
#   pytest tests/ -m "not integration" -v
#
# WHAT THIS FILE CALLS
#   app.services.briefing_intelligence.catalog.tenancy.detect_day_2
#   tests/services/conftest.py builders (make_tenant, make_employee,
#                                          make_machine)
#
# DESIGN NOTES
#   Verifies single-shot semantics (only fires on day 2), industry-
#   label substitution via templates.industry_labels (printing →
#   presses, fabrication → operators), and full placeholder
#   resolution (no leftover {employees_label} in output).

from datetime import date, timedelta

from app.services.briefing_intelligence.catalog.tenancy import (
    DAY_2_SIGNAL_ID,
    DAY_2_TARGET_AGE_DAYS,
    detect_day_2,
)

from tests.services.conftest import make_employee, make_machine, make_tenant


TODAY = date(2026, 5, 4)


class TestDetectDay2:

    def test_returns_none_off_marker(self, db):
        tenant = make_tenant(db, age_days=5)
        db.commit()
        assert detect_day_2(tenant.id, TODAY, db) is None

    def test_fires_on_day_2_with_employee_and_machine_counts(self, db):
        tenant = make_tenant(
            db, age_days=DAY_2_TARGET_AGE_DAYS, industry_type="printing",
        )
        make_employee(db, tenant=tenant, full_name="Suresh")
        make_employee(db, tenant=tenant, full_name="Anil")
        make_machine(db, tenant=tenant, name="Press-1")
        db.commit()

        result = detect_day_2(tenant.id, TODAY, db)
        assert result is not None
        assert result.signal_id == DAY_2_SIGNAL_ID
        assert result.tier == 1
        assert result.confidence == "high"
        # Industry vocabulary substituted (printing → presses)
        assert "presses" in result.message_hi_en
        assert "employees" in result.message_hi_en
        assert "2" in result.message_hi_en  # 2 employees
        assert "1" in result.message_hi_en  # 1 press
        # No unresolved placeholders
        assert "{" not in result.message_hi_en

    def test_uses_fabrication_vocabulary(self, db):
        tenant = make_tenant(
            db, age_days=DAY_2_TARGET_AGE_DAYS,
            industry_type="fabrication",
        )
        make_employee(db, tenant=tenant, full_name="Worker")
        db.commit()
        result = detect_day_2(tenant.id, TODAY, db)
        assert result is not None
        assert "operators" in result.message_hi_en

    def test_returns_none_for_day_1(self, db):
        tenant = make_tenant(db, age_days=1)
        db.commit()
        assert detect_day_2(tenant.id, TODAY, db) is None

    def test_returns_none_for_day_3(self, db):
        tenant = make_tenant(db, age_days=3)
        db.commit()
        assert detect_day_2(tenant.id, TODAY, db) is None
