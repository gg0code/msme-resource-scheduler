# tests/services/test_detect_day_7.py
# Branch: v5-whatsapp
#
# FILE PURPOSE
# Unit tests for detect_day_7 (catalog/tenancy.py, spec
# B.5.day_7_wow_signal — daily-marker portion only; the cross-day
# wow-gate selection is deferred to v6.3.16).
#
# WHO CALLS THIS FILE
#   pytest tests/ -m "not integration" -v
#
# WHAT THIS FILE CALLS
#   app.services.briefing_intelligence.catalog.tenancy.detect_day_7
#   tests/services/conftest.py builders (make_tenant)
#
# DESIGN NOTES
#   Single-shot semantics (day 7 only), industry-label substitution
#   for the jobs vocabulary, and placeholder resolution.

from datetime import date

from app.services.briefing_intelligence.catalog.tenancy import (
    DAY_7_SIGNAL_ID,
    DAY_7_TARGET_AGE_DAYS,
    detect_day_7,
)

from tests.services.conftest import make_tenant


TODAY = date(2026, 5, 4)


class TestDetectDay7:

    def test_returns_none_off_marker(self, db):
        tenant = make_tenant(db, age_days=5, today=TODAY)
        db.commit()
        assert detect_day_7(tenant.id, TODAY, db) is None

    def test_fires_on_day_7(self, db):
        tenant = make_tenant(
            db, age_days=DAY_7_TARGET_AGE_DAYS, industry_type="printing",
            today=TODAY,
        )
        db.commit()
        result = detect_day_7(tenant.id, TODAY, db)
        assert result is not None
        assert result.signal_id == DAY_7_SIGNAL_ID
        assert result.tier == 1
        assert "7 din" in result.message_hi_en
        # Industry-specific job-label injected
        assert "jobs" in result.message_hi_en
        assert "{" not in result.message_hi_en

    def test_fabrication_uses_orders_vocabulary(self, db):
        tenant = make_tenant(
            db, age_days=DAY_7_TARGET_AGE_DAYS,
            industry_type="fabrication",
            today=TODAY,
        )
        db.commit()
        result = detect_day_7(tenant.id, TODAY, db)
        assert result is not None
        assert "orders" in result.message_hi_en

    def test_returns_none_at_day_6(self, db):
        tenant = make_tenant(db, age_days=6, today=TODAY)
        db.commit()
        assert detect_day_7(tenant.id, TODAY, db) is None

    def test_returns_none_at_day_8(self, db):
        tenant = make_tenant(db, age_days=8, today=TODAY)
        db.commit()
        assert detect_day_7(tenant.id, TODAY, db) is None
