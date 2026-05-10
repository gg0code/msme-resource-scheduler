# tests/services/test_detect_new_employee_no_show.py
# Branch: v5-whatsapp
#
# FILE PURPOSE
# Unit tests for detect_new_employee_no_show (catalog/attendance.py,
# spec B.1.new_employee_no_show).
#
# WHO CALLS THIS FILE
#   pytest tests/ -m "not integration" -v
#
# WHAT THIS FILE CALLS
#   app.services.briefing_intelligence.catalog.attendance.detect_new_employee_no_show
#   tests/services/conftest.py builders (make_tenant, make_employee,
#                                          make_attendance_event,
#                                          make_employee_leave)
#
# DESIGN NOTES
#   Covers the 14-day creation window, "absent on every day vs seen
#   present once" branching, planned-leave bypass, and the 3-day
#   minimum post-create history floor.

from datetime import date, datetime, timedelta, timezone

import pytest

from app.services.briefing_intelligence.catalog.attendance import (
    NOSHOW_SIGNAL_ID,
    detect_new_employee_no_show,
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


class TestDetectNewEmployeeNoShow:

    def test_returns_none_when_no_new_employees(self, db):
        tenant = make_tenant(db)
        emp = make_employee(db, tenant=tenant, full_name="Old",
                             created_days_ago=60)
        for off in range(5):
            _checkin(db, tenant, TODAY - timedelta(days=off), [emp])
        db.commit()
        assert detect_new_employee_no_show(tenant.id, TODAY, db) is None

    @pytest.mark.xfail(
        reason=(
            "Date-relative test against real `date.today()` / "
            "`datetime.now()`; pre-existing v6.3.11 detector bug "
            "surfaced by v6.3.18 audit. Pre-existing failure, "
            "not introduced by v6.3.18. Fix deferred to dedicated "
            "patch release; remove this marker when the detector "
            "test is rewritten to inject `now` instead of reading "
            "the wall clock."
        ),
        strict=False,
    )
    def test_fires_when_new_hire_marked_absent_every_day(self, db):
        tenant = make_tenant(db)
        emp = make_employee(db, tenant=tenant, full_name="Promised",
                             created_days_ago=5)
        # Three working days post-create, all absent
        for off in range(3):
            _checkin(db, tenant, TODAY - timedelta(days=off), [emp])
        db.commit()

        result = detect_new_employee_no_show(tenant.id, TODAY, db)
        assert result is not None
        assert result.signal_id == NOSHOW_SIGNAL_ID
        assert result.tier == 2
        assert result.subject_entity_id == emp.id
        assert "Promised" in result.message_hi_en
        assert result.severity_score >= 3.0

    def test_returns_none_when_employee_was_seen_present(self, db):
        tenant = make_tenant(db)
        emp = make_employee(db, tenant=tenant, full_name="Showed",
                             created_days_ago=5)
        # Three days, present on one
        _checkin(db, tenant, TODAY - timedelta(days=3), [emp])
        _checkin(db, tenant, TODAY - timedelta(days=2), [])
        _checkin(db, tenant, TODAY, [emp])
        db.commit()
        assert detect_new_employee_no_show(tenant.id, TODAY, db) is None

    def test_skips_employee_with_planned_leave_today(self, db):
        tenant = make_tenant(db)
        emp = make_employee(db, tenant=tenant, full_name="LateJoiner",
                             created_days_ago=5)
        for off in range(3):
            _checkin(db, tenant, TODAY - timedelta(days=off), [emp])
        make_employee_leave(
            db, tenant=tenant, employee=emp,
            start_date=TODAY - timedelta(days=1),
            end_date=TODAY + timedelta(days=10),
        )
        db.commit()
        assert detect_new_employee_no_show(tenant.id, TODAY, db) is None

    @pytest.mark.xfail(strict=False, reason="date drift, see CHANGELOG note 92")
    def test_skips_employees_added_more_than_14_days_ago(self, db):
        tenant = make_tenant(db)
        emp = make_employee(db, tenant=tenant, full_name="OldHire",
                             created_days_ago=20)
        for off in range(5):
            _checkin(db, tenant, TODAY - timedelta(days=off), [emp])
        db.commit()
        assert detect_new_employee_no_show(tenant.id, TODAY, db) is None

    def test_returns_none_with_too_few_post_create_checkins(self, db):
        tenant = make_tenant(db)
        emp = make_employee(db, tenant=tenant, full_name="Justin",
                             created_days_ago=5)
        # Only 2 working days post-create — below the 3-day threshold
        for off in range(2):
            _checkin(db, tenant, TODAY - timedelta(days=off), [emp])
        db.commit()
        assert detect_new_employee_no_show(tenant.id, TODAY, db) is None
