# tests/services/test_detect_consecutive_absence.py
# Branch: v5-whatsapp
#
# FILE PURPOSE
# Unit tests for detect_consecutive_absence (catalog/attendance.py,
# spec B.1.consecutive_absence).
#
# WHO CALLS THIS FILE
#   pytest tests/ -m "not integration" -v
#
# WHAT THIS FILE CALLS
#   app.services.briefing_intelligence.catalog.attendance.detect_consecutive_absence
#   tests/services/conftest.py builders (make_tenant, make_employee,
#                                          make_attendance_event,
#                                          make_employee_leave)
#
# DESIGN NOTES
#   Covers all spec suppression rules (contractor exclusion, new-
#   joinee skip <7d, planned-leave break), the day-2 vs day-N
#   message templates, and the "streak must end today" requirement.

from datetime import date, datetime, timedelta, timezone

from app.services.briefing_intelligence.catalog.attendance import (
    CONSEC_SIGNAL_ID,
    detect_consecutive_absence,
)

from tests.services.conftest import (
    make_attendance_event,
    make_employee,
    make_employee_leave,
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


class TestDetectConsecutiveAbsence:

    def test_returns_none_with_insufficient_history(self, db):
        tenant = make_tenant(db)
        emp = make_employee(db, tenant=tenant, full_name="Solo",
                            created_days_ago=30)
        _checkin(db, tenant, TODAY, [emp])
        db.commit()
        # Only 1 day of history → returns None gracefully
        assert detect_consecutive_absence(tenant.id, TODAY, db) is None

    def test_fires_for_two_day_streak(self, db):
        tenant = make_tenant(db)
        suresh = make_employee(db, tenant=tenant, full_name="Suresh",
                                created_days_ago=30)
        _checkin(db, tenant, TODAY - timedelta(days=1), [suresh])
        _checkin(db, tenant, TODAY, [suresh])
        db.commit()

        result = detect_consecutive_absence(tenant.id, TODAY, db)
        assert result is not None
        assert result.signal_id == CONSEC_SIGNAL_ID
        assert result.tier == 1
        assert result.subject_entity_id == suresh.id
        assert "Suresh" in result.message_hi_en
        assert "2 din" in result.message_hi_en
        assert result.severity_score == 2.0

    def test_uses_n_din_template_for_three_or_more(self, db):
        tenant = make_tenant(db)
        anil = make_employee(db, tenant=tenant, full_name="Anil",
                              created_days_ago=30)
        for off in range(3):
            _checkin(db, tenant, TODAY - timedelta(days=off), [anil])
        db.commit()
        result = detect_consecutive_absence(tenant.id, TODAY, db)
        assert result is not None
        assert result.severity_score == 3.0
        assert "3 din" in result.message_hi_en
        assert "gayab" in result.message_hi_en

    def test_skips_contractors(self, db):
        tenant = make_tenant(db)
        contractor = make_employee(
            db, tenant=tenant, full_name="Tempo",
            worker_type="contractor", created_days_ago=30,
        )
        _checkin(db, tenant, TODAY - timedelta(days=1), [contractor])
        _checkin(db, tenant, TODAY, [contractor])
        db.commit()
        assert detect_consecutive_absence(tenant.id, TODAY, db) is None

    def test_skips_new_joinees(self, db):
        tenant = make_tenant(db)
        new = make_employee(db, tenant=tenant, full_name="Newbie",
                             created_days_ago=2)
        _checkin(db, tenant, TODAY - timedelta(days=1), [new])
        _checkin(db, tenant, TODAY, [new])
        db.commit()
        assert detect_consecutive_absence(tenant.id, TODAY, db) is None

    def test_planned_leave_breaks_streak(self, db):
        tenant = make_tenant(db)
        emp = make_employee(db, tenant=tenant, full_name="OnLeave",
                             created_days_ago=30)
        _checkin(db, tenant, TODAY - timedelta(days=1), [emp])
        _checkin(db, tenant, TODAY, [emp])
        make_employee_leave(
            db, tenant=tenant, employee=emp,
            start_date=TODAY - timedelta(days=2),
            end_date=TODAY + timedelta(days=1),
        )
        db.commit()
        # Both absences fall inside planned leave → no signal.
        assert detect_consecutive_absence(tenant.id, TODAY, db) is None

    def test_returns_none_when_streak_does_not_end_today(self, db):
        tenant = make_tenant(db)
        emp = make_employee(db, tenant=tenant, full_name="Sometimes",
                             created_days_ago=30)
        # Absent two days ago and three days ago, present today
        _checkin(db, tenant, TODAY - timedelta(days=3), [emp])
        _checkin(db, tenant, TODAY - timedelta(days=2), [emp])
        _checkin(db, tenant, TODAY, [])  # present today
        db.commit()
        assert detect_consecutive_absence(tenant.id, TODAY, db) is None
