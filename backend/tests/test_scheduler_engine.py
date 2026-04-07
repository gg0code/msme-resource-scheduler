# backend/tests/test_scheduler_engine.py
# Unit tests for the scheduler engine (app/scheduler/engine.py).
# No DB required — pure function tests on scheduling logic.

import pytest
from datetime import date, datetime, time, timedelta

from app.scheduler.engine import (
    JobInput, LockedEntry, ResourceSlot,
    StepInput, run_scheduler,
)

SHIFT_START = time(8, 0)
SHIFT_END   = time(17, 0)
TEST_DATE   = date(2026, 4, 13)


def make_machine(id_: int, name: str = None) -> ResourceSlot:
    return ResourceSlot(
        id=id_, name=name or f"Machine {id_}",
        type="machine", shift_start=SHIFT_START, shift_end=SHIFT_END,
    )

def make_helper(id_: int) -> ResourceSlot:
    return ResourceSlot(
        id=id_, name=f"Helper {id_}",
        type="helper", shift_start=SHIFT_START, shift_end=SHIFT_END,
    )

def make_job(id_: int, priority: str = "low", profit: float = 10000.0,
             deadline_days: int = 60) -> JobInput:
    dl = datetime(TEST_DATE.year, TEST_DATE.month, TEST_DATE.day, 17, 0) \
         + timedelta(days=deadline_days)
    return JobInput(
        id=id_, name=f"Job {id_}", priority=priority,
        expected_profit=profit, deadline=dl, shift="morning", lock_status=False,
    )

def make_step(id_: int, job_id: int, duration_minutes: int = 60,
              machine_ids: list = None, helper_ids: list = None,
              sequence_order: int = 1) -> StepInput:
    return StepInput(
        id=id_, job_id=job_id, sequence_order=sequence_order,
        step_type="regular", duration_minutes=duration_minutes,
        required_machine_ids=machine_ids or [],
        required_helper_ids=helper_ids or [],
        reserve_machine_id=None,
    )


class TestSingleJob:
    def test_single_step_resolves(self):
        result = run_scheduler(
            jobs=[make_job(1)],
            steps=[make_step(1, job_id=1, duration_minutes=60, machine_ids=[10])],
            resources=[make_machine(10)],
            locked_entries=[], schedule_date=TEST_DATE,
        )
        assert len(result.resolved) == 1
        assert len(result.unresolved) == 0
        e = result.resolved[0]
        assert e.job_id == 1
        assert e.scheduled_start.date() == TEST_DATE
        assert e.scheduled_start.time() >= SHIFT_START
        assert e.scheduled_end.time() <= SHIFT_END

    def test_step_without_resources_resolves(self):
        result = run_scheduler(
            jobs=[make_job(1)],
            steps=[make_step(1, job_id=1, duration_minutes=30)],
            resources=[], locked_entries=[], schedule_date=TEST_DATE,
        )
        assert len(result.resolved) == 1

    def test_step_longer_than_shift_is_clamped_or_rejected(self):
        """
        A step longer than the shift window (480 min) is either clamped to
        shift end OR rejected by the engine. Both are acceptable — what is NOT
        acceptable is scheduling it beyond the shift window.
        The engine in v3.0 clamps end time to shift_end (17:00) and still
        resolves — this test verifies the end time never exceeds shift_end.
        """
        result = run_scheduler(
            jobs=[make_job(1)],
            steps=[make_step(1, job_id=1, duration_minutes=600, machine_ids=[10])],
            resources=[make_machine(10)],
            locked_entries=[], schedule_date=TEST_DATE,
        )
        if result.resolved:
            # Engine resolved it — end must be clamped to shift_end
            assert result.resolved[0].scheduled_end.time() <= SHIFT_END, \
                "End time must not exceed shift end"
        else:
            # Engine rejected it — also acceptable
            assert len(result.unresolved) == 1


class TestPriorityOrdering:
    def test_critical_wins_over_high(self):
        jobs = [make_job(1, priority="urgent"), make_job(2, priority="critical")]
        steps = [
            make_step(1, job_id=1, duration_minutes=480, machine_ids=[10]),
            make_step(2, job_id=2, duration_minutes=480, machine_ids=[10]),
        ]
        result = run_scheduler(jobs=jobs, steps=steps, resources=[make_machine(10)],
                               locked_entries=[], schedule_date=TEST_DATE)
        resolved_ids   = {e.job_id for e in result.resolved}
        unresolved_ids = {e.job_id for e in result.unresolved}
        assert 2 in resolved_ids,   "Critical (job 2) should be resolved"
        assert 1 in unresolved_ids, "High (job 1) should be unresolved"

    def test_higher_profit_wins_when_same_priority(self):
        jobs = [make_job(1, priority="low", profit=5000), make_job(2, priority="low", profit=50000)]
        steps = [
            make_step(1, job_id=1, duration_minutes=480, machine_ids=[10]),
            make_step(2, job_id=2, duration_minutes=480, machine_ids=[10]),
        ]
        result = run_scheduler(jobs=jobs, steps=steps, resources=[make_machine(10)],
                               locked_entries=[], schedule_date=TEST_DATE)
        assert 2 in {e.job_id for e in result.resolved}, "Higher profit job should win"


class TestLockedEntries:
    def test_locked_entry_blocks_machine(self):
        locked = [LockedEntry(
            job_id=99, step_id=99, resource_id=10, resource_type="machine",
            start=datetime(TEST_DATE.year, TEST_DATE.month, TEST_DATE.day, 8, 0),
            end=datetime(TEST_DATE.year, TEST_DATE.month, TEST_DATE.day, 17, 0),
        )]
        result = run_scheduler(
            jobs=[make_job(1)],
            steps=[make_step(1, job_id=1, duration_minutes=60, machine_ids=[10])],
            resources=[make_machine(10)], locked_entries=locked, schedule_date=TEST_DATE,
        )
        assert len(result.unresolved) == 1
        assert len(result.resolved) == 0

    def test_locked_job_is_skipped(self):
        job = JobInput(
            id=1, name="Locked", priority="critical", expected_profit=100000,
            deadline=datetime(2026, 12, 31, 17, 0), shift="morning", lock_status=True,
        )
        result = run_scheduler(
            jobs=[job],
            steps=[make_step(1, job_id=1, duration_minutes=60, machine_ids=[10])],
            resources=[make_machine(10)], locked_entries=[], schedule_date=TEST_DATE,
        )
        assert len(result.resolved) == 0
        assert len(result.unresolved) == 0


class TestSequentialGate:
    def test_step2_waits_for_step1(self):
        result = run_scheduler(
            jobs=[make_job(1)],
            steps=[
                make_step(10, job_id=1, duration_minutes=60, sequence_order=1),
                make_step(11, job_id=1, duration_minutes=60, sequence_order=2),
            ],
            resources=[], locked_entries=[], schedule_date=TEST_DATE,
        )
        assert len(result.resolved) == 2
        ids = [e.step_id for e in result.resolved]
        assert ids.index(10) < ids.index(11)

    def test_step2_blocked_if_step1_fails(self):
        locked = [LockedEntry(
            job_id=99, step_id=99, resource_id=10, resource_type="machine",
            start=datetime(TEST_DATE.year, TEST_DATE.month, TEST_DATE.day, 8, 0),
            end=datetime(TEST_DATE.year, TEST_DATE.month, TEST_DATE.day, 17, 0),
        )]
        result = run_scheduler(
            jobs=[make_job(1)],
            steps=[
                make_step(10, job_id=1, duration_minutes=60, machine_ids=[10], sequence_order=1),
                make_step(11, job_id=1, duration_minutes=60, sequence_order=2),
            ],
            resources=[make_machine(10)], locked_entries=locked, schedule_date=TEST_DATE,
        )
        unresolved_ids = {e.step_id for e in result.unresolved}
        assert 10 in unresolved_ids, "Step 1 should fail"
        assert 11 in unresolved_ids, "Step 2 should be blocked"


class TestHelperShareability:
    def test_two_jobs_share_same_helper(self):
        result = run_scheduler(
            jobs=[make_job(1), make_job(2)],
            steps=[
                make_step(1, job_id=1, duration_minutes=60, machine_ids=[10], helper_ids=[20]),
                make_step(2, job_id=2, duration_minutes=60, machine_ids=[11], helper_ids=[20]),
            ],
            resources=[make_machine(10), make_machine(11), make_helper(20)],
            locked_entries=[], schedule_date=TEST_DATE,
        )
        assert len(result.resolved) == 2
        assert len(result.unresolved) == 0


class TestDeadline:
    def test_step_rejected_if_misses_deadline(self):
        job = JobInput(
            id=1, name="Overdue", priority="critical", expected_profit=100000,
            deadline=datetime(2026, 1, 1, 8, 0),  # deadline in the past
            shift="morning", lock_status=False,
        )
        result = run_scheduler(
            jobs=[job],
            steps=[make_step(1, job_id=1, duration_minutes=60, machine_ids=[10])],
            resources=[make_machine(10)], locked_entries=[], schedule_date=TEST_DATE,
        )
        assert len(result.unresolved) == 1
        assert len(result.resolved) == 0
