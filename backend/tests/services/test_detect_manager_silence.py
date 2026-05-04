# tests/services/test_detect_manager_silence.py
# Branch: v5-whatsapp
#
# FILE PURPOSE
# Unit tests for detect_manager_silence (catalog/health.py, spec
# B.6.manager_silence).
#
# WHO CALLS THIS FILE
#   pytest tests/ -m "not integration" -v
#
# WHAT THIS FILE CALLS
#   app.services.briefing_intelligence.catalog.health.detect_manager_silence
#   tests/services/conftest.py builders (make_tenant, make_attendance_event)
#
# DESIGN NOTES
#   Verifies the 7-day quiet-period gate (returns None for young
#   tenants), the strictly-less-than-4-checkins threshold, and the
#   monotonic severity score (silence days = window − checkin count).

from datetime import date, datetime, timedelta, timezone

from app.services.briefing_intelligence.catalog.health import (
    MANAGER_SILENCE_MIN_TENANT_AGE_DAYS,
    MANAGER_SILENCE_SIGNAL_ID,
    detect_manager_silence,
)

from tests.services.conftest import make_attendance_event, make_tenant


TODAY = date(2026, 5, 4)


class TestDetectManagerSilence:

    def test_returns_none_for_young_tenant(self, db):
        tenant = make_tenant(db, age_days=3)
        db.commit()
        assert detect_manager_silence(tenant.id, TODAY, db) is None

    def test_fires_when_few_checkins_in_window(self, db):
        tenant = make_tenant(
            db, age_days=MANAGER_SILENCE_MIN_TENANT_AGE_DAYS + 5,
        )
        # Just 2 check-ins in the last 7 days → < 4 → fires
        for offset in (1, 2):
            make_attendance_event(
                db, tenant=tenant,
                for_date=TODAY - timedelta(days=offset),
                absent_employee_ids=[],
                created_at=datetime.now(timezone.utc) - timedelta(days=offset),
            )
        db.commit()

        result = detect_manager_silence(tenant.id, TODAY, db)
        assert result is not None
        assert result.signal_id == MANAGER_SILENCE_SIGNAL_ID
        assert result.tier == 2
        assert result.confidence == "high"
        assert "2" in result.message_hi_en
        assert result.severity_score >= 1.0

    def test_returns_none_when_enough_checkins(self, db):
        tenant = make_tenant(
            db, age_days=MANAGER_SILENCE_MIN_TENANT_AGE_DAYS + 5,
        )
        for offset in range(1, 6):  # 5 events
            make_attendance_event(
                db, tenant=tenant,
                for_date=TODAY - timedelta(days=offset),
                absent_employee_ids=[],
                created_at=datetime.now(timezone.utc) - timedelta(days=offset),
            )
        db.commit()
        assert detect_manager_silence(tenant.id, TODAY, db) is None

    def test_returns_none_for_zero_history_but_old_tenant(self, db):
        # No check-ins yet, but tenant is old enough — fires.
        tenant = make_tenant(
            db, age_days=MANAGER_SILENCE_MIN_TENANT_AGE_DAYS + 10,
        )
        db.commit()
        result = detect_manager_silence(tenant.id, TODAY, db)
        assert result is not None
        # Severity should reflect 7 missed days (window).
        assert result.severity_score >= 6.0

    def test_severity_grows_as_silence_extends(self, db):
        tenant = make_tenant(
            db, age_days=MANAGER_SILENCE_MIN_TENANT_AGE_DAYS + 5,
        )
        # Only 1 check-in → 6 silent days
        make_attendance_event(
            db, tenant=tenant,
            for_date=TODAY - timedelta(days=1),
            absent_employee_ids=[],
            created_at=datetime.now(timezone.utc) - timedelta(days=1),
        )
        db.commit()
        r = detect_manager_silence(tenant.id, TODAY, db)
        assert r is not None
        assert r.severity_score == 6.0
