# tests/services/conftest.py
# Branch: v5-whatsapp
#
# FILE PURPOSE
# Shared fixtures + builders for v6.3.11 evaluator unit tests. Reuses
# the parent tests/conftest.py `db` SQLite fixture and adds:
#   - patch_now_defaults_for_sqlite — autouse; swaps text("now()")
#     server defaults to CURRENT_TIMESTAMP for the tables touched by
#     the evaluator tests.
#   - Builder helpers (make_tenant, make_employee, make_machine,
#     make_job, make_assignment, make_attendance_event,
#     make_employee_leave, make_machine_downtime) so each evaluator
#     test stays focused on the signal under test.
#
# WHO CALLS THIS FILE
#   Every test module under tests/services/ — pytest auto-loads the
#   nearest conftest.py for fixture resolution. The `db` fixture from
#   tests/conftest.py (parent) is also visible here; this file only
#   adds the evaluator-specific patch + builders on top.
#
# WHAT THIS FILE CALLS
#   - app.models.{auth, employee, event, job, machine, unavailability}
#     — ORM constructors invoked by the builders.
#   - sqlalchemy DefaultClause + text — used by the autouse patch.
#
# DESIGN NOTES
#   - Builders return the flushed (not committed) ORM instance so each
#     test can chain additional setup before its single db.commit().
#   - Builder defaults match the v6.3.11 spec's printing-vertical
#     reference tenant where it matters (industry_type='printing',
#     status='Active' / 'Operational', worker_type='permanent').
#     Tests that need a different shape pass overrides explicitly.

from datetime import date, datetime, timedelta, timezone

import pytest
from freezegun import freeze_time
from sqlalchemy import text as sa_text
from sqlalchemy.sql.schema import DefaultClause

from app.models.auth import RefreshToken, Tenant, User
from app.models.employee import Employee
from app.models.event import Event
from app.models.extraction_candidate import ExtractionCandidate
from app.models.job import Job, JobAssignment
from app.models.machine import Machine
from app.models.unavailability import EmployeeLeave, MachineDowntime


# v6.3.19.1 slice 3A — detector test date-anchoring fix.
#
# Every test file under tests/services/test_detect_*.py hard-codes
# `TODAY = date(2026, 5, 4)` and passes that constant into the
# detector under test. The fixture builders (make_employee,
# make_machine, make_job, etc.) call `datetime.now(timezone.utc) -
# timedelta(days=N)` to derive `created_at` / `updated_at`. Without
# alignment between the two anchors, fixture rows fall outside the
# detector's `created_at >= cutoff_dt` window where `cutoff_dt` is
# derived from TODAY — and trigger conditions silently fail. This is
# the root cause of CHANGELOG note 92.
#
# Pinning wall-clock now() to TODAY via freezegun aligns both
# anchors. The freeze is autouse + scope="function" so any test that
# wants to deviate can do so via a local @freeze_time decorator that
# overrides this one.
#
# Production behaviour is unaffected — real attendance.recorded
# events carry true now() created_at timestamps and the dispatcher
# passes the live tenant-local today, so the two anchors stay in sync
# at runtime regardless of this autouse.

_DETECTOR_TEST_TODAY = "2026-05-04"


@pytest.fixture(autouse=True)
def freeze_clock_at_detector_today():
    """Pin wall-clock now() to date(2026, 5, 4) for every test that
    inherits this conftest. See header note for context.

    The freeze covers datetime.now(), datetime.utcnow(), and time.time().
    Tests that need a different anchor can stack their own
    @freeze_time decorator — freezegun's last-in-wins rule applies.
    """
    with freeze_time(_DETECTOR_TEST_TODAY):
        yield


@pytest.fixture(autouse=True)
def patch_now_defaults_for_sqlite():
    """Swap text("now()") server defaults to CURRENT_TIMESTAMP for SQLite.

    Mirrors the local fixture used by tests/test_briefing_intelligence_*
    and tests/test_signup_v6_4.py. Centralised here so each evaluator
    test file does not re-declare the same patch.
    """
    targets = (
        Tenant.__table__, User.__table__, RefreshToken.__table__,
        Event.__table__, Job.__table__, JobAssignment.__table__,
        Employee.__table__, Machine.__table__,
        EmployeeLeave.__table__, MachineDowntime.__table__,
        # v6.3.14 — extractor unit tests insert into this table.
        ExtractionCandidate.__table__,
    )
    patched = []
    for tbl in targets:
        for col in tbl.columns:
            if col.server_default is None:
                continue
            arg = getattr(col.server_default, "arg", None)
            text_value = str(arg) if arg is not None else ""
            if "now()" in text_value.lower():
                patched.append((col, col.server_default))
                col.server_default = DefaultClause(sa_text("CURRENT_TIMESTAMP"))
    yield
    for col, original in patched:
        col.server_default = original


# ---------------------------------------------------------------------------
# ID counter — keeps slug + name uniqueness across tests in one session.
# ---------------------------------------------------------------------------

_COUNTER = {"n": 0}


def _next_id() -> int:
    """Monotonic counter for unique slugs / names across builders.

    Called by:    every make_* builder below.
    Calls into:   nothing.
    Side effects: mutates module-level _COUNTER.
    """
    _COUNTER["n"] += 1
    return _COUNTER["n"]


# ---------------------------------------------------------------------------
# Builders
# ---------------------------------------------------------------------------

def make_tenant(
    db,
    *,
    age_days: int | None = 30,
    industry_type: str = "printing",
    created_at: datetime | None = None,
    today: date | None = None,
) -> Tenant:
    """Build a Tenant whose created_at is `age_days` days before the anchor.

    Called by:    every evaluator test, plus the integration tests.
    Calls into:   _next_id (this file), Tenant ORM constructor.
    Side effects: stages a Tenant row in the supplied test session.

    Args:
        today: Optional date anchor for the age calculation. When set,
               created_at = today - age_days (interpreted as UTC midnight).
               When None, real datetime.now() is used.

               Tests that pin `TODAY = date(...)` and pass it to a
               detector MUST also pass `today=TODAY` here. Otherwise
               UTC-midnight rollover during a CI run can drift the
               tenant's created_at by one day relative to the detector's
               anchor and flip boundary assertions (day-2 / day-7 /
               recurring-customer markers). Bug found 2026-05-05 when
               UTC clock crossed 04 -> 05 mid-session and 8 evaluator
               tests started failing.
    """
    n = _next_id()
    now = datetime.now(timezone.utc)
    if created_at is None and age_days is not None:
        if today is not None:
            anchor = datetime.combine(
                today, datetime.min.time()
            ).replace(tzinfo=timezone.utc)
            created_at = anchor - timedelta(days=age_days)
        else:
            created_at = now - timedelta(days=age_days)
    if created_at is None:
        created_at = now
    t = Tenant(
        name=f"T-{n}", slug=f"t-{n}", plan="free",
        is_active=True, industry_type=industry_type,
        created_at=created_at, updated_at=now,
    )
    db.add(t)
    db.flush()
    return t


def make_employee(
    db,
    *,
    tenant: Tenant,
    full_name: str,
    worker_type: str = "permanent",
    status: str = "Active",
    created_days_ago: int = 30,
) -> Employee:
    """Build an Employee tied to `tenant` with the given onboarding age.

    Called by:    attendance + day-2 evaluator tests.
    Calls into:   Employee ORM constructor.
    Side effects: stages an Employee row in the supplied test session.
    """
    now = datetime.now(timezone.utc)
    created = now - timedelta(days=created_days_ago)
    e = Employee(
        tenant_id=tenant.id,
        full_name=full_name,
        status=status,
        worker_type=worker_type,
        source="manual",
        employment_type="Full-time",
        base_availability_pct=100.0,
        created_at=created,
        updated_at=now,
    )
    db.add(e)
    db.flush()
    return e


def make_machine(
    db,
    *,
    tenant: Tenant,
    name: str,
    status: str = "Operational",
    updated_days_ago: float = 30.0,
) -> Machine:
    """Build a Machine tied to `tenant` with the given updated_at age.

    Called by:    machine + day-2 evaluator tests.
    Calls into:   Machine ORM constructor.
    Side effects: stages a Machine row in the supplied test session.
    """
    now = datetime.now(timezone.utc)
    updated = now - timedelta(days=updated_days_ago)
    m = Machine(
        tenant_id=tenant.id,
        name=name,
        status=status,
        source="manual",
        base_availability_pct=100.0,
        created_at=updated,
        updated_at=updated,
    )
    db.add(m)
    db.flush()
    return m


def make_job(
    db,
    *,
    tenant: Tenant,
    name: str,
    start_date: date,
    end_date: date,
    status: str = "in_progress",
    customer: str | None = None,
    order_value: float | None = None,
    is_locked: bool = False,
    actual_start_at: datetime | None = None,
    updated_days_ago: float | None = None,
    created_days_ago: float = 5.0,
    estimated_hours_per_day: float = 8.0,
) -> Job:
    """Build a Job tied to `tenant` with caller-controlled date window.

    Called by:    job, machine, customer evaluator tests + the
                  integration tests.
    Calls into:   Job ORM constructor.
    Side effects: stages a Job row in the supplied test session.
    """
    now = datetime.now(timezone.utc)
    if updated_days_ago is None:
        updated_at = now
    else:
        updated_at = now - timedelta(days=updated_days_ago)
    created_at = now - timedelta(days=created_days_ago)
    j = Job(
        tenant_id=tenant.id, name=name,
        start_date=start_date, end_date=end_date,
        status=status, customer=customer,
        order_value=order_value, is_locked=is_locked,
        actual_start_at=actual_start_at,
        estimated_hours_per_day=estimated_hours_per_day,
        created_at=created_at, updated_at=updated_at,
    )
    db.add(j)
    db.flush()
    return j


def make_assignment(
    db,
    *,
    tenant: Tenant,
    job: Job | None = None,
    machine: Machine | None = None,
    employee: Employee | None = None,
    days_ago: float = 0.0,
) -> JobAssignment:
    """Build a JobAssignment row linking the optional resource(s) to a job.

    Called by:    machine evaluator tests + the integration tests.
    Calls into:   JobAssignment ORM constructor.
    Side effects: stages a JobAssignment row in the supplied test session.
    """
    now = datetime.now(timezone.utc)
    assigned_at = now - timedelta(days=days_ago)
    a = JobAssignment(
        tenant_id=tenant.id,
        job_id=job.id if job else None,
        machine_id=machine.id if machine else None,
        employee_id=employee.id if employee else None,
        assigned_at=assigned_at,
    )
    db.add(a)
    db.flush()
    return a


def make_attendance_event(
    db,
    *,
    tenant: Tenant,
    for_date: date,
    absent_employee_ids: list[int],
    down_machine_ids: list[int] | None = None,
    created_at: datetime | None = None,
) -> Event:
    """Insert one attendance.recorded Event row for the timeline.

    Called by:    attendance, health, integration tests.
    Calls into:   Event ORM constructor.
    Side effects: stages an Event row in the supplied test session.

    The payload mirrors what whatsapp_checkin.save_checkin_state writes
    in production (`for_date`, `absent_employee_ids`, `down_machine_ids`).
    """
    if created_at is None:
        created_at = datetime.combine(
            for_date, datetime.min.time(),
        ).replace(tzinfo=timezone.utc)
    ev = Event(
        tenant_id=tenant.id,
        event_type="attendance.recorded",
        entity_type="checkin",
        entity_id=None,
        actor_user_id=None,
        source="whatsapp",
        payload={
            "for_date": for_date.isoformat(),
            "absent_employee_ids": list(absent_employee_ids),
            "down_machine_ids": list(down_machine_ids or []),
        },
        created_at=created_at,
    )
    db.add(ev)
    db.flush()
    return ev


def make_employee_leave(
    db,
    *,
    tenant: Tenant,
    employee: Employee,
    start_date: date,
    end_date: date,
    reason: str = "planned",
) -> EmployeeLeave:
    """Build an EmployeeLeave row covering [start_date, end_date].

    Called by:    consecutive_absence + new_employee_no_show tests
                  to verify the planned-leave suppression rule.
    Calls into:   EmployeeLeave ORM constructor.
    Side effects: stages an EmployeeLeave row in the supplied test session.
    """
    leave = EmployeeLeave(
        tenant_id=tenant.id,
        employee_id=employee.id,
        start_date=start_date,
        end_date=end_date,
        reason=reason,
    )
    db.add(leave)
    db.flush()
    return leave


def make_machine_downtime(
    db,
    *,
    tenant: Tenant,
    machine: Machine,
    start_date: date,
    end_date: date,
    reason: str = "down",
) -> MachineDowntime:
    """Build a MachineDowntime row covering [start_date, end_date].

    Called by:    idle_machine test to verify the open-downtime
                  suppression rule.
    Calls into:   MachineDowntime ORM constructor.
    Side effects: stages a MachineDowntime row in the supplied test session.
    """
    md = MachineDowntime(
        tenant_id=tenant.id,
        machine_id=machine.id,
        start_date=start_date,
        end_date=end_date,
        reason=reason,
    )
    db.add(md)
    db.flush()
    return md
