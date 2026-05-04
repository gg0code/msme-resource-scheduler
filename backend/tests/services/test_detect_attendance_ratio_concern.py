# tests/services/test_detect_attendance_ratio_concern.py
# Branch: v5-whatsapp
#
# FILE PURPOSE
# Unit tests for detect_attendance_ratio_concern (catalog/attendance.py,
# spec B.1.attendance_ratio_concern).
#
# WHO CALLS THIS FILE
#   pytest tests/ -m "not integration" -v
#
# WHAT THIS FILE CALLS
#   app.services.briefing_intelligence.catalog.attendance.detect_attendance_ratio_concern
#   tests/services/conftest.py builders (make_tenant, make_employee,
#                                          make_attendance_event)
#
# DESIGN NOTES
#   Verifies the 7-day minimum-history floor, the 60% ratio threshold,
#   contractor + new-joinee exclusion, and that the worst-ratio
#   employee wins when multiple qualify.

from datetime import date, datetime, timedelta, timezone

from app.services.briefing_intelligence.catalog.attendance import (
    RATIO_MIN_HISTORY_DAYS,
    RATIO_SIGNAL_ID,
    detect_attendance_ratio_concern,
)

from tests.services.conftest import (
    make_attendance_event,
    make_employee,
    make_tenant,
)


TODAY = date(2026, 5, 4)


def _checkin(db, tenant, for_date, absent):
    """Insert one attendance.recorded event row for `for_date`.

    Called by:    every test in this file.
    Calls into:   make_attendance_event (tests/services/conftest.py).
    Side effects: stages an Event row via the test session.
    """
    make_attendance_event(
        db, tenant=tenant, for_date=for_date,
        absent_employee_ids=[e.id for e in absent],
        created_at=datetime.combine(for_date, datetime.min.time())
            .replace(tzinfo=timezone.utc),
    )


class TestDetectAttendanceRatioConcern:

    def test_returns_none_with_insufficient_history(self, db):
        tenant = make_tenant(db)
        emp = make_employee(db, tenant=tenant, full_name="Suresh",
                             created_days_ago=30)
        # Only 4 working days reported — less than min 7
        for off in range(4):
            _checkin(db, tenant, TODAY - timedelta(days=off), [emp])
        db.commit()
        assert detect_attendance_ratio_concern(tenant.id, TODAY, db) is None

    def test_fires_when_ratio_below_60pct(self, db):
        tenant = make_tenant(db)
        emp = make_employee(db, tenant=tenant, full_name="Suresh",
                             created_days_ago=30)
        # 7 working days reported; absent 4 of them → 3/7 ≈ 43% < 60%
        for off in range(RATIO_MIN_HISTORY_DAYS):
            absent = [emp] if off < 4 else []
            _checkin(db, tenant, TODAY - timedelta(days=off), absent)
        db.commit()

        result = detect_attendance_ratio_concern(tenant.id, TODAY, db)
        assert result is not None
        assert result.signal_id == RATIO_SIGNAL_ID
        assert result.tier == 2
        assert "Suresh" in result.message_hi_en
        assert "%" in result.message_hi_en
        # severity_score = (1 - ratio) * 100 = ~57
        assert result.severity_score >= 50.0

    def test_returns_none_when_ratio_above_threshold(self, db):
        tenant = make_tenant(db)
        emp = make_employee(db, tenant=tenant, full_name="Reliable",
                             created_days_ago=30)
        # 7 days, absent 1 → 6/7 = 85% > 60%
        for off in range(RATIO_MIN_HISTORY_DAYS):
            absent = [emp] if off == 3 else []
            _checkin(db, tenant, TODAY - timedelta(days=off), absent)
        db.commit()
        assert detect_attendance_ratio_concern(tenant.id, TODAY, db) is None

    def test_skips_contractors(self, db):
        tenant = make_tenant(db)
        contractor = make_employee(
            db, tenant=tenant, full_name="Tempo",
            worker_type="contractor", created_days_ago=30,
        )
        for off in range(RATIO_MIN_HISTORY_DAYS):
            absent = [contractor] if off < 5 else []
            _checkin(db, tenant, TODAY - timedelta(days=off), absent)
        db.commit()
        assert detect_attendance_ratio_concern(tenant.id, TODAY, db) is None

    def test_skips_new_joinees(self, db):
        tenant = make_tenant(db)
        new = make_employee(db, tenant=tenant, full_name="Newbie",
                             created_days_ago=2)
        for off in range(RATIO_MIN_HISTORY_DAYS):
            absent = [new] if off < 5 else []
            _checkin(db, tenant, TODAY - timedelta(days=off), absent)
        db.commit()
        assert detect_attendance_ratio_concern(tenant.id, TODAY, db) is None

    def test_picks_worst_employee_when_multiple_qualify(self, db):
        tenant = make_tenant(db)
        a = make_employee(db, tenant=tenant, full_name="Aimless",
                           created_days_ago=30)
        b = make_employee(db, tenant=tenant, full_name="Barely",
                           created_days_ago=30)
        # a absent 6/7 (14%), b absent 3/7 (57%); a is worse
        for off in range(RATIO_MIN_HISTORY_DAYS):
            absent = []
            if off < 6:
                absent.append(a)
            if off < 3:
                absent.append(b)
            _checkin(db, tenant, TODAY - timedelta(days=off), absent)
        db.commit()
        result = detect_attendance_ratio_concern(tenant.id, TODAY, db)
        assert result is not None
        assert result.subject_entity_id == a.id
