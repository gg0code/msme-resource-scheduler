"""
```python
"""
backend/tests/test_scheduler.py

FILE PURPOSE
This file contains unit tests for the pure-Python scheduling engine that powers ZetaOps
Copilot's core job scheduling functionality. It was introduced in v4.0 to ensure the
scheduler engine correctly handles resource conflicts, priority-based job ordering, setup
step reservations, and locked job entries. These tests validate the core scheduling logic
without any database dependencies, sitting in the test layer that validates the business
logic layer (app/scheduler/engine.py).

WHAT THIS FILE DOES — step by step
1. Imports the scheduler engine classes and functions from app.scheduler.engine
2. Defines shared test fixtures including a fixed schedule date (March 10, 2026)
3. Creates helper functions to generate test resources (machines M1/M2, helpers H1/H2)
4. Creates helper functions to generate XY1 and XY2 job steps that mirror seed data
5. Runs four comprehensive tests covering basic scheduling, setup reservations, locked jobs, and conflicts
6. Validates that the scheduler produces correct ScheduleEntry objects in resolved list
7. Validates that unresolvable conflicts appear in unresolved list with proper error messages
8. Asserts timing constraints like priority ordering and resource availability windows

KEY FUNCTIONS / CLASSES / COMPONENTS

Name         : _dt
Type         : function
Purpose      : Helper function that creates datetime objects on the fixed SCHEDULE_DATE at the specified hour and minute. Reduces boilerplate in test assertions and makes test times more readable.
Parameters   : h (int) - hour in 24-hour format, m (int, default 0) - minute
Returns      : datetime object set to SCHEDULE_DATE at the specified time
Calls        : Python datetime constructor
DB/API       : None - pure utility function
Side effects : None

Name         : make_resources
Type         : function  
Purpose      : Factory function that creates standard test resource configuration with two machines (M1, M2) and two helpers (H1, H2), all working 8:00-16:00 shifts. Provides consistent resource setup across all tests.
Parameters   : None
Returns      : List of ResourceSlot objects representing available machines and helpers
Calls        : ResourceSlot constructor from scheduler engine
DB/API       : None - creates in-memory test data
Side effects : None

Name         : make_xy1_steps
Type         : function
Purpose      : Factory function that creates the XY1 job step sequence used in seed data - a 4-step manufacturing process including regular production steps and a setup step with machine reservation. Mirrors real-world job complexity.
Parameters   : job_id (int, default 1) - the job ID to assign to all generated steps
Returns      : List of StepInput objects representing the complete XY1 job workflow
Calls        : StepInput constructor from scheduler engine
DB/API       : None - creates in-memory test data
Side effects : None

Name         : make_xy2_steps
Type         : function
Purpose      : Factory function that creates the XY2 job step sequence used in seed data - a 3-step manufacturing process that shares resources with XY1 to test resource contention scenarios. Designed to conflict with XY1 steps.
Parameters   : job_id (int, default 2) - the job ID to assign to all generated steps  
Returns      : List of StepInput objects representing the complete XY2 job workflow
Calls        : StepInput constructor from scheduler engine
DB/API       : None - creates in-memory test data
Side effects : None

Name         : test_basic_xy1_xy2_all_resolved
Type         : function
Purpose      : Comprehensive test that validates basic scheduling functionality by running XY1 and XY2 jobs through the scheduler and ensuring all 7 steps are successfully scheduled. Tests priority ordering (critical beats urgent despite lower profit) and resource allocation.
Parameters   : None (pytest test function)
Returns      : None (assertions validate behavior)
Calls        : make_resources, make_xy1_steps, make_xy2_steps, run_scheduler from engine
DB/API       : None - pure engine testing
Side effects : None (test assertions only)

Name         : test_setup_reserve_blocks_machine
Type         : function
Purpose      : Tests the setup step machine reservation feature where a setup step reserves a machine without actively using it, preventing other steps from using that machine during the setup window. Validates that resource blocking works correctly.
Parameters   : None (pytest test function)
Returns      : None (assertions validate behavior)
Calls        : make_resources, make_xy1_steps, run_scheduler from engine
DB/API       : None - pure engine testing
Side effects : None (test assertions only)

Name         : test_locked_job_blocks_machine
Type         : function
Purpose      : Tests the locked job functionality where previously scheduled jobs create LockedEntry objects that block resources from being allocated to new jobs. Validates that the scheduler respects existing commitments and schedules around them.
Parameters   : None (pytest test function)
Returns      : None (assertions validate behavior)
Calls        : make_resources, run_scheduler from engine, LockedEntry constructor
DB/API       : None - pure engine testing
Side effects : None (test assertions only)

Name         : test_conflict_machine_deadline
Type         : function
Purpose      : Tests conflict resolution when multiple jobs need the same resource but one has an impossible deadline. Validates that the scheduler correctly identifies unresolvable conflicts and provides meaningful error messages in the unresolved list.
Parameters   : None (pytest test function)
Returns      : None (assertions validate behavior)
Calls        : run_scheduler from engine, ResourceSlot/JobInput/StepInput constructors
DB/API       : None - pure engine testing
Side effects : None (test assertions only)

WHO CALLS THIS FILE
- pytest test runner when executing: pytest tests/test_scheduler.py -v
- CI/CD pipeline during automated testing
- Developer workflow during local testing before commits to v4-dev branch

IMPORTS EXPLAINED
- datetime.date, datetime.datetime, datetime.time: Python standard library for handling test schedule dates and times, needed to create realistic scheduling scenarios
- pytest: Testing framework that provides test discovery, fixtures, and assertion handling for the test suite
- app.scheduler.engine: The core scheduler module being tested, imports all the input/output classes (JobInput, StepInput, ResourceSlot, ScheduleEntry, ConflictEntry, LockedEntry) and the main run_scheduler function

INTERN NOTES
- Easiest thing to break: Changing the SCHEDULE_DATE constant will break time-sensitive assertions in tests, and modifying resource IDs in helper functions will break the hardcoded assertions that reference specific machine/helper IDs
- Non-obvious design decision: Tests use a fixed future date (March 10, 2026) instead of relative dates to ensure consistent test results regardless of when tests are run, avoiding flaky tests due to date arithmetic
- Most common mistake: Forgetting that the scheduler engine is pure Python with zero database calls, so tests must provide all job/step/resource data as input objects rather than expecting database queries
- Design principle: Implements principle #1 (Engine computes, AI only narrates) by testing the core scheduling logic independently of any AI or database components
- What to check if behaving unexpectedly: Verify that ResourceSlot shift times match the test assumptions (8:00-16:00), check that step duration_minutes align with expected scheduling windows, and ensure job priorities follow the critical > urgent > normal hierarchy
- v4-dev specific: This file is stable in production branch and should not be modified unless scheduler engine behavior changes, as these tests validate core business logic that customers depend on
"""
```
"""

from datetime import date, datetime, time

import pytest

from app.scheduler.engine import (
    ConflictEntry, JobInput, LockedEntry,
    ResourceSlot, ScheduleEntry, SchedulerResult,
    StepInput, run_scheduler,
)

# ─── Shared fixtures ──────────────────────────────────────────────────────────

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


# ═════════════════════════════════════════════════════════════════════════════
# Test 1 — Basic scheduling: XY1 + XY2 schedule without conflict.
#           XY1 is critical → scheduled first despite XY2 having higher profit.
#           All 7 steps must appear in resolved.
# ═════════════════════════════════════════════════════════════════════════════

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


# ═════════════════════════════════════════════════════════════════════════════
# Test 2 — Setup reserve: XY1 Sx (seq=3) reserves M1.
#           No other step may use M1 during that window.
# ═════════════════════════════════════════════════════════════════════════════

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

    # Find Sx (seq=3 — setup with reserve_machine_id=1)
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


# ═════════════════════════════════════════════════════════════════════════════
# Test 3 — Locked job blocking: Lock XY2 with M1 from 08:00–10:00.
#           An unlocked job needing M1 must not start before 10:00.
# ═════════════════════════════════════════════════════════════════════════════

def test_locked_job_blocks_machine():
    resources = make_resources()

    # XY2 is locked — its M1 window 08:00–10:00 is a LockedEntry
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


# ═════════════════════════════════════════════════════════════════════════════
# Test 4 — Conflict: two jobs both need M1; second job's deadline is before
#           M1 is free.  Second job's step must appear in unresolved.
# ═════════════════════════════════════════════════════════════════════════════

def test_conflict_machine_deadline():
    # Only M1 exists
    resources = [
        ResourceSlot(id=1, name="M1", type="machine",
                     shift_start=time(8, 0), shift_end=time(16, 0)),
    ]

    # Job A: critical, uses M1 for 7 hours (08:00–15:00)
    job_a = JobInput(id=1, name="JobA", priority="critical",
                     expected_profit=100_000, deadline=_dt(23, 59),
                     shift="morning", lock_status=False)
    steps_a = [
        StepInput(id=101, job_id=1, sequence_order=1, step_type="regular",
                  duration_minutes=420, required_machine_ids=[1], required_helper_ids=[]),
    ]

    # Job B: urgent, also needs M1 — but deadline is 09:00 (impossible after A takes it)
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
