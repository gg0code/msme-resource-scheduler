from datetime import date, datetime, time

import pytest

from app.scheduler.engine import (
    ConflictEntry, JobInput, LockedEntry,
    ResourceSlot, ScheduleEntry, SchedulerResult,
    StepInput, run_scheduler,
)

# --- Shared fixtures ----------------------------------------------------------

SCHEDULE_DATE = date(2026, 3, 10)   # a Monday — arbitrary fixed date


def _dt(h: int, m: int = 0) -> datetime:
    """Shorthand: datetime on SCHEDULE_DATE at HH:MM."""
    return datetime(SCHEDULE_DATE.year, SCHEDULE_DATE.month, SCHEDULE_DATE.day, h, m)


def make_resources():
    return [
        ResourceSlot(id=1, name="M1", type="machine", shift_start=time(8, 0), shift_end=time(16, 0)),
        ResourceSlot(id=2, name="M2", type="machine", shift_start=time(8, 0), shift_end=time(16, 0)),
        ResourceSlot(id=3, name="H1", type="helper",  shift_start=time(8, 0), shift_end=time(16, 0)),
        ResourceSlot(id=4, name="H2", type="helper",  shift_start=time(8, 0), shift_end=time(16, 0)),
    ]


def make_xy1_steps(job_id: int = 1) -> list:
    """
    XY1 steps (from seed data):
      seq=1  regular  M1 + H1   120 min
      seq=2  regular  M2 + H2    90 min
      seq=3  setup    H1 only, reserve=M1  30 min
      seq=4  regular  M1 + H1    60 min
    """
    return [
        StepInput(id=101, job_id=job_id, sequence_order=1, step_type="regular",
                  duration_minutes=120, required_machine_ids=[1], required_helper_ids=[3]),
        StepInput(id=102, job_id=job_id, sequence_order=2, step_type="regular",
                  duration_minutes=90,  required_machine_ids=[2], required_helper_ids=[4]),
        StepInput(id=103, job_id=job_id, sequence_order=3, step_type="setup",
                  duration_minutes=30,  required_machine_ids=[], required_helper_ids=[3],
                  reserve_machine_id=1),
        StepInput(id=104, job_id=job_id, sequence_order=4, step_type="regular",
                  duration_minutes=60,  required_machine_ids=[1], required_helper_ids=[3]),
    ]


def make_xy2_steps(job_id: int = 2) -> list:
    """
    XY2 steps (from seed data):
      seq=1  regular  M2 + H2   60 min
      seq=2  setup    H2 only, reserve=M1  20 min
      seq=3  regular  M1 + H2  120 min
    """
    return [
        StepInput(id=201, job_id=job_id, sequence_order=1, step_type="regular",
                  duration_minutes=60,  required_machine_ids=[2], required_helper_ids=[4]),
        StepInput(id=202, job_id=job_id, sequence_order=2, step_type="setup",
                  duration_minutes=20,  required_machine_ids=[], required_helper_ids=[4],
                  reserve_machine_id=1),
        StepInput(id=203, job_id=job_id, sequence_order=3, step_type="regular",
                  duration_minutes=120, required_machine_ids=[1], required_helper_ids=[4]),
    ]


# -----------------------------------------------------------------------------
# Test 1 - Basic scheduling: XY1 + XY2 schedule without conflict.
#           XY1 is critical -> scheduled first despite XY2 having higher profit.
#           All 7 steps must appear in resolved.
# -----------------------------------------------------------------------------

def test_basic_xy1_xy2_all_resolved():
    resources = make_resources()

    jobs = [
        JobInput(id=1, name="XY1", priority="critical",
                 expected_profit=70_000, deadline=_dt(23, 59),
                 shift="morning", lock_status=False),
        JobInput(id=2, name="XY2", priority="urgent",
                 expected_profit=90_000, deadline=_dt(23, 59),
                 shift="morning", lock_status=False),
    ]

    steps = make_xy1_steps(1) + make_xy2_steps(2)

    result = run_scheduler(
        jobs=jobs, steps=steps, resources=resources,
        locked_entries=[], schedule_date=SCHEDULE_DATE,
    )

    # All 7 steps resolved
    assert len(result.unresolved) == 0, (
        f"Expected 0 conflicts, got {len(result.unresolved)}: "
        + ", ".join(c.reason for c in result.unresolved)
    )
    assert len(result.resolved) == 7

    resolved_step_ids = {e.step_id for e in result.resolved}
    for step in steps:
        assert step.id in resolved_step_ids, f"Step {step.id} missing from resolved"

    # XY1 (critical) must be scheduled BEFORE XY2 (urgent) where they share M1
    xy1_s1 = next(e for e in result.resolved if e.step_id == 101)
    xy2_s1 = next(e for e in result.resolved if e.step_id == 201)

    # XY1 step 1 starts at shift open (08:00) because it has priority
    assert xy1_s1.scheduled_start == _dt(8, 0), (
        f"XY1 step 1 should start at 08:00, got {xy1_s1.scheduled_start}"
    )


# -----------------------------------------------------------------------------
# Test 2 - Setup reserve: XY1 Sx (seq=3) reserves M1.
#           No other step may use M1 during that window.
# -----------------------------------------------------------------------------

def test_setup_reserve_blocks_machine():
    resources = make_resources()

    jobs = [
        JobInput(id=1, name="XY1", priority="critical",
                 expected_profit=70_000, deadline=_dt(23, 59),
                 shift="morning", lock_status=False),
    ]

    steps = make_xy1_steps(1)
    result = run_scheduler(
        jobs=jobs, steps=steps, resources=resources,
        locked_entries=[], schedule_date=SCHEDULE_DATE,
    )

    assert len(result.unresolved) == 0

    # Find Sx (seq=3 - setup with reserve_machine_id=1)
    sx = next(e for e in result.resolved if e.step_id == 103)
    sx_start = sx.scheduled_start
    sx_end   = sx.scheduled_end

    # Find step seq=4 (uses M1)
    s4 = next(e for e in result.resolved if e.step_id == 104)

    # S4 must NOT overlap with Sx's window on M1
    overlaps = sx_start < s4.scheduled_end and s4.scheduled_start < sx_end
    assert not overlaps, (
        f"S4 ({s4.scheduled_start}–{s4.scheduled_end}) overlaps "
        f"with Sx reserve window ({sx_start}–{sx_end}) on M1"
    )

    # S4 must start at or after Sx ends
    assert s4.scheduled_start >= sx_end, (
        f"S4 must start after Sx ends ({sx_end}), got {s4.scheduled_start}"
    )


# -----------------------------------------------------------------------------
# Test 3 - Locked job blocking: Lock XY2 with M1 from 08:00-10:00.
#           An unlocked job needing M1 must not start before 10:00.
# -----------------------------------------------------------------------------

def test_locked_job_blocks_machine():
    resources = make_resources()

    # XY2 is locked - its M1 window 08:00-10:00 is a LockedEntry
    locked_entries = [
        LockedEntry(
            job_id=2, step_id=201,
            resource_id=1, resource_type="machine",   # M1
            start=_dt(8, 0), end=_dt(10, 0),
        )
    ]

    # Unlocked job that needs M1 for 60 min
    new_job = JobInput(id=3, name="NewJob", priority="urgent",
                       expected_profit=50_000, deadline=_dt(23, 59),
                       shift="morning", lock_status=False)
    new_steps = [
        StepInput(id=301, job_id=3, sequence_order=1, step_type="regular",
                  duration_minutes=60, required_machine_ids=[1], required_helper_ids=[]),
    ]

    result = run_scheduler(
        jobs=[new_job], steps=new_steps, resources=resources,
        locked_entries=locked_entries, schedule_date=SCHEDULE_DATE,
    )

    assert len(result.unresolved) == 0, (
        "Expected new job to resolve: " + str([c.reason for c in result.unresolved])
    )

    entry = result.resolved[0]
    assert entry.scheduled_start >= _dt(10, 0), (
        f"Job needing M1 must start at 10:00 or later, got {entry.scheduled_start}"
    )


# -----------------------------------------------------------------------------
# Test 4 - Conflict: two jobs both need M1; second job's deadline is before
#           M1 is free.  Second job's step must appear in unresolved.
# -----------------------------------------------------------------------------

def test_conflict_machine_deadline():
    # Only M1 exists
    resources = [
        ResourceSlot(id=1, name="M1", type="machine",
                     shift_start=time(8, 0), shift_end=time(16, 0)),
    ]

    # Job A: critical, uses M1 for 7 hours (08:00-15:00)
    job_a = JobInput(id=1, name="JobA", priority="critical",
                     expected_profit=100_000, deadline=_dt(23, 59),
                     shift="morning", lock_status=False)
    steps_a = [
        StepInput(id=101, job_id=1, sequence_order=1, step_type="regular",
                  duration_minutes=420, required_machine_ids=[1], required_helper_ids=[]),
    ]

    # Job B: urgent, also needs M1 - but deadline is 09:00 (impossible after A takes it)
    job_b = JobInput(id=2, name="JobB", priority="urgent",
                     expected_profit=50_000, deadline=_dt(9, 0),   # tight deadline
                     shift="morning", lock_status=False)
    steps_b = [
        StepInput(id=201, job_id=2, sequence_order=1, step_type="regular",
                  duration_minutes=60, required_machine_ids=[1], required_helper_ids=[]),
    ]

    result = run_scheduler(
        jobs=[job_a, job_b],
        steps=steps_a + steps_b,
        resources=resources,
        locked_entries=[],
        schedule_date=SCHEDULE_DATE,
    )

    # Job A (critical) resolves on M1
    resolved_ids = {e.step_id for e in result.resolved}
    assert 101 in resolved_ids, "Job A step should be resolved"

    # Job B should be in unresolved
    unresolved_ids = {c.step_id for c in result.unresolved}
    assert 201 in unresolved_ids, (
        "Job B step should be unresolved because M1 is taken and deadline passes"
    )

    # Conflict reason must be a non-empty string
    conflict = next(c for c in result.unresolved if c.step_id == 201)
    assert isinstance(conflict.reason, str) and len(conflict.reason) > 0
    assert "M1" in conflict.reason or "deadline" in conflict.reason or "slot" in conflict.reason, (
        f"Expected reason to mention M1, deadline, or slot. Got: {conflict.reason}"
    )
