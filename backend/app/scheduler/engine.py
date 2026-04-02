"""
```python
"""
backend/app/scheduler/engine.py — Pure Python Scheduling Engine

FILE PURPOSE
This file contains the core scheduling algorithm for the ZetaOps Copilot workforce and job scheduling system. It implements a greedy priority-based scheduler that takes jobs, steps, resources, and existing locked entries as input, then produces a schedule that assigns time slots to job steps while respecting resource constraints and sequential dependencies. This is a pure computational engine with zero database dependencies, following design principle #1 (Engine computes, AI only narrates). The file was introduced in the early versions of the system and serves as the mathematical heart of the scheduling functionality, converting business requirements into concrete time-based resource allocations.

WHAT THIS FILE DOES — step by step
1. Defines input dataclasses (ResourceSlot, StepInput, JobInput, LockedEntry) that represent the scheduling problem
2. Defines output dataclasses (ScheduleEntry, ConflictEntry, SchedulerResult) that represent the scheduling solution
3. Sets up priority ranking system for jobs (critical > urgent > low)
4. Implements helper functions for datetime manipulation and resource conflict detection
5. Builds occupancy maps from existing locked entries to track resource availability
6. Sorts unlocked jobs by priority, profit, and deadline to establish scheduling order
7. Iterates through each job's steps in sequence order, applying sequential gates and resource constraints
8. Performs minute-by-minute scanning to find available time slots within shift windows
9. Records successful assignments in the resolved list and conflicts in the unresolved list
10. Returns a complete SchedulerResult containing both successful and failed scheduling attempts

KEY FUNCTIONS / CLASSES / COMPONENTS

Name         : ResourceSlot
Type         : dataclass
Purpose      : Represents a schedulable resource (machine or helper) with availability windows. Contains the resource's basic identification and shift timing constraints that determine when it can be scheduled.
Parameters   : id (int) - unique resource identifier, name (str) - human-readable resource name, type (str) - either 'machine' or 'helper' for resource category, shift_start (time) - when resource becomes available, shift_end (time) - when resource becomes unavailable
Returns      : N/A (dataclass)
Calls        : None
DB/API       : None (pure dataclass)
Side effects : None

Name         : StepInput
Type         : dataclass
Purpose      : Represents a single step within a job that needs to be scheduled. Contains all the resource requirements, timing constraints, and sequencing information needed to place this step in the schedule.
Parameters   : id (int) - unique step identifier, job_id (int) - parent job reference, sequence_order (int) - position in job workflow, step_type (str) - 'regular' or 'setup' classification, duration_minutes (int) - how long step takes, required_machine_ids (List[int]) - machines needed for step, required_helper_ids (List[int]) - helpers needed for step, reserve_machine_id (Optional[int]) - exclusive machine reservation for setup steps
Returns      : N/A (dataclass)
Calls        : None
DB/API       : None (pure dataclass)
Side effects : None

Name         : JobInput
Type         : dataclass
Purpose      : Represents a complete job containing multiple steps. Provides job-level metadata used for prioritization and scheduling decisions including business priority and profitability metrics.
Parameters   : id (int) - unique job identifier, name (str) - human-readable job name, priority (str) - business priority level ('critical', 'urgent', 'low'), expected_profit (Optional[float]) - projected revenue for prioritization, deadline (datetime) - when job must complete, shift (str) - preferred shift timing ('morning', 'evening'), lock_status (bool) - whether job is already locked in schedule
Returns      : N/A (dataclass)
Calls        : None
DB/API       : None (pure dataclass)
Side effects : None

Name         : LockedEntry
Type         : dataclass
Purpose      : Represents an already-scheduled time block that cannot be moved. Used to build the initial occupancy map so the scheduler respects existing commitments and locked assignments.
Parameters   : job_id (int) - which job owns this time block, step_id (int) - which step this represents, resource_id (int) - which resource is occupied, resource_type (str) - classification ('machine', 'helper', 'reserve'), start (datetime) - when occupation begins, end (datetime) - when occupation ends
Returns      : N/A (dataclass)
Calls        : None
DB/API       : None (pure dataclass)
Side effects : None

Name         : ScheduleEntry
Type         : dataclass
Purpose      : Represents a successfully scheduled step with concrete time assignments and resource allocations. This is the primary output format showing exactly when and where each step will execute.
Parameters   : job_id (int) - parent job reference, step_id (int) - which step was scheduled, assigned_machine_ids (List[int]) - machines allocated to step, assigned_helper_ids (List[int]) - helpers allocated to step, scheduled_start (datetime) - when step begins execution, scheduled_end (datetime) - when step completes execution
Returns      : N/A (dataclass)
Calls        : None
DB/API       : None (pure dataclass)
Side effects : None

Name         : ConflictEntry
Type         : dataclass
Purpose      : Represents a step that could not be scheduled due to resource conflicts, timing constraints, or dependency issues. Provides diagnostic information explaining why scheduling failed.
Parameters   : job_id (int) - parent job reference, step_id (int) - which step failed, sequence_order (int) - step position for context, reason (str) - human-readable explanation of scheduling failure
Returns      : N/A (dataclass)
Calls        : None
DB/API       : None (pure dataclass)
Side effects : None

Name         : SchedulerResult
Type         : dataclass
Purpose      : Container for complete scheduling results including both successful assignments and failures. Ensures every step of every unlocked job appears exactly once across resolved or unresolved lists.
Parameters   : resolved (List[ScheduleEntry]) - successfully scheduled steps, unresolved (List[ConflictEntry]) - steps that could not be scheduled
Returns      : N/A (dataclass)
Calls        : None
DB/API       : None (pure dataclass)
Side effects : None

Name         : _dt
Type         : function
Purpose      : Utility function that combines separate date and time objects into a single naive datetime. Used throughout the scheduler to convert shift timing information into schedulable datetime objects.
Parameters   : d (date) - the date component, t (time) - the time component
Returns      : datetime - naive datetime combining the date and time inputs
Calls        : datetime constructor
DB/API       : None
Side effects : None

Name         : _overlaps
Type         : function
Purpose      : Determines whether two half-open time intervals overlap using mathematical interval logic. Critical for detecting resource conflicts during scheduling by checking if proposed assignments conflict with existing occupancy.
Parameters   : s1 (datetime) - start of first interval, e1 (datetime) - end of first interval, s2 (datetime) - start of second interval, e2 (datetime) - end of second interval
Returns      : bool - True if intervals overlap, False if they don't conflict
Calls        : None (pure mathematical comparison)
DB/API       : None
Side effects : None

Name         : _is_free
Type         : function
Purpose      : Checks whether a specific resource is available during a proposed time window by scanning its occupancy map for conflicts. Returns True only if the entire proposed window is clear of existing assignments.
Parameters   : occupancy (OccupancyMap) - current resource occupancy
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from typing import Dict, List, Optional, Tuple


# ─── Input dataclasses ────────────────────────────────────────────────────────

@dataclass
class ResourceSlot:
    id:          int
    name:        str
    type:        str          # 'machine' | 'helper'
    shift_start: time
    shift_end:   time


@dataclass
class StepInput:
    id:                   int
    job_id:               int
    sequence_order:       int
    step_type:            str   # 'regular' | 'setup'
    duration_minutes:     int
    required_machine_ids: List[int] = field(default_factory=list)
    required_helper_ids:  List[int] = field(default_factory=list)
    reserve_machine_id:   Optional[int] = None


@dataclass
class JobInput:
    id:              int
    name:            str
    priority:        str    # 'critical' | 'urgent' | 'low'
    expected_profit: Optional[float]
    deadline:        datetime
    shift:           str    # 'morning' | 'evening'
    lock_status:     bool


@dataclass
class LockedEntry:
    job_id:        int
    step_id:       int
    resource_id:   int
    resource_type: str      # 'machine' | 'helper' | 'reserve'
    start:         datetime
    end:           datetime


# ─── Output dataclasses ───────────────────────────────────────────────────────

@dataclass
class ScheduleEntry:
    job_id:               int
    step_id:              int
    assigned_machine_ids: List[int]
    assigned_helper_ids:  List[int]
    scheduled_start:      datetime
    scheduled_end:        datetime


@dataclass
class ConflictEntry:
    job_id:         int
    step_id:        int
    sequence_order: int
    reason:         str


@dataclass
class SchedulerResult:
    resolved:   List[ScheduleEntry]
    unresolved: List[ConflictEntry]


# ─── Priority ordering ────────────────────────────────────────────────────────

_PRIORITY_RANK = {"critical": 3, "urgent": 2, "low": 1}


# ─── Internal types ───────────────────────────────────────────────────────────

# occupancy[resource_id] = list of (start, end) blocked windows
OccupancyMap = Dict[int, List[Tuple[datetime, datetime]]]


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _dt(d: date, t: time) -> datetime:
    """Combine a date and a time into a naive datetime."""
    return datetime(d.year, d.month, d.day, t.hour, t.minute, t.second)


def _overlaps(s1: datetime, e1: datetime, s2: datetime, e2: datetime) -> bool:
    """True when two half-open intervals [s1,e1) and [s2,e2) overlap."""
    return s1 < e2 and s2 < e1


def _is_free(
    occupancy: OccupancyMap,
    resource_id: int,
    start: datetime,
    end: datetime,
) -> bool:
    """Return True when resource_id has no blocked window overlapping [start, end)."""
    for (blocked_start, blocked_end) in occupancy.get(resource_id, []):
        if _overlaps(start, end, blocked_start, blocked_end):
            return False
    return True


def _block(
    occupancy: OccupancyMap,
    resource_id: int,
    start: datetime,
    end: datetime,
) -> None:
    occupancy.setdefault(resource_id, []).append((start, end))


# ─── Main scheduler ───────────────────────────────────────────────────────────

def run_scheduler(
    jobs:           List[JobInput],
    steps:          List[StepInput],
    resources:      List[ResourceSlot],
    locked_entries: List[LockedEntry],
    schedule_date:  date,
) -> SchedulerResult:
    """
    Run the greedy priority-based scheduler.

    Returns a SchedulerResult where every step of every unlocked job
    appears in exactly one of resolved or unresolved.
    Locked jobs are never touched — their windows are pre-loaded into occupancy.
    """

    # ── Resource lookup maps ─────────────────────────────────────────────────
    res_by_id: Dict[int, ResourceSlot] = {r.id: r for r in resources}

    # ── Step lookup: job_id → sorted list of StepInput ──────────────────────
    steps_by_job: Dict[int, List[StepInput]] = {}
    for s in steps:
        steps_by_job.setdefault(s.job_id, []).append(s)
    for job_steps in steps_by_job.values():
        job_steps.sort(key=lambda s: s.sequence_order)

    # ── Step status map (from existing DB status — passed implicitly via
    #    lock_status on job; we trust confirmed dict for ordering) ────────────
    step_by_id: Dict[int, StepInput] = {s.id: s for s in steps}

    # ── Step 1: build occupancy from locked_entries ──────────────────────────
    occupancy: OccupancyMap = {}
    locked_job_ids = {e.job_id for e in locked_entries}

    for entry in locked_entries:
        # treat 'machine' and 'reserve' as exclusive; 'helper' is shareable
        if entry.resource_type in ("machine", "reserve"):
            _block(occupancy, entry.resource_id, entry.start, entry.end)
        # helpers are shareable — intentionally NOT blocked in occupancy

    # ── Step 2: sort unlocked jobs ───────────────────────────────────────────
    unlocked_jobs = [j for j in jobs if not j.lock_status]
    unlocked_jobs.sort(
        key=lambda j: (
            -_PRIORITY_RANK.get(j.priority, 0),
            -(j.expected_profit or 0),
            j.deadline,
        )
    )

    # ── Step 3: schedule each unlocked job ───────────────────────────────────
    resolved:   List[ScheduleEntry]  = []
    unresolved: List[ConflictEntry]  = []

    for job in unlocked_jobs:
        job_steps = steps_by_job.get(job.id, [])
        if not job_steps:
            continue

        # confirmed: step_id → scheduled_end (for sequential gate)
        confirmed: Dict[int, datetime] = {}
        job_blocked = False   # once a step can't resolve, skip rest

        for step in job_steps:

            # ── a. Sequential gate ──────────────────────────────────────────
            if job_blocked:
                unresolved.append(ConflictEntry(
                    job_id=step.job_id,
                    step_id=step.id,
                    sequence_order=step.sequence_order,
                    reason=(
                        f"Step {step.sequence_order} blocked: "
                        f"step {step.sequence_order - 1} not yet resolved"
                    ),
                ))
                continue

            # Check all predecessor steps exist in confirmed
            predecessors = [
                s for s in job_steps
                if s.sequence_order < step.sequence_order
            ]
            for pred in predecessors:
                if pred.id not in confirmed:
                    unresolved.append(ConflictEntry(
                        job_id=step.job_id,
                        step_id=step.id,
                        sequence_order=step.sequence_order,
                        reason=(
                            f"Step {step.sequence_order} blocked: "
                            f"step {pred.sequence_order} not yet resolved"
                        ),
                    ))
                    job_blocked = True
                    break
            if job_blocked:
                continue

            # ── b. Earliest start ───────────────────────────────────────────
            # Collect all resource shift_start times
            all_resource_ids = (
                step.required_machine_ids
                + step.required_helper_ids
                + ([step.reserve_machine_id] if step.reserve_machine_id else [])
            )
            resource_shift_starts = []
            resource_shift_ends   = []
            for rid in all_resource_ids:
                res = res_by_id.get(rid)
                if res:
                    resource_shift_starts.append(_dt(schedule_date, res.shift_start))
                    resource_shift_ends.append(_dt(schedule_date, res.shift_end))

            # Earliest possible start
            shift_open = (
                max(resource_shift_starts)
                if resource_shift_starts
                else datetime(schedule_date.year, schedule_date.month, schedule_date.day, 0, 0)
            )

            # Shift end = minimum shift_end across all required resources
            # (step can't run past the earliest resource that goes home)
            shift_close = (
                min(resource_shift_ends)
                if resource_shift_ends
                else datetime(schedule_date.year, schedule_date.month, schedule_date.day, 23, 59)
            )

            # Previous step's confirmed end
            prev_steps = [s for s in job_steps if s.sequence_order < step.sequence_order]
            if prev_steps:
                last_prev = max(prev_steps, key=lambda s: s.sequence_order)
                prev_end = confirmed.get(last_prev.id, shift_open)
            else:
                prev_end = shift_open

            earliest_start = max(shift_open, prev_end)

            # ── c. Find slot (minute-by-minute scan) ────────────────────────
            slot_found      = False
            slot_start:  datetime = earliest_start
            slot_end:    datetime = earliest_start

            duration = timedelta(minutes=step.duration_minutes)
            scan_start = earliest_start

            # Scan up to shift_close
            current = scan_start
            while current + duration <= shift_close:
                proposed_start = current
                proposed_end   = current + duration

                ok = True

                # Check machines (exclusive)
                for mid in step.required_machine_ids:
                    if not _is_free(occupancy, mid, proposed_start, proposed_end):
                        ok = False
                        break

                # Check reserve machine (exclusive, setup steps only)
                if ok and step.reserve_machine_id is not None:
                    if not _is_free(occupancy, step.reserve_machine_id, proposed_start, proposed_end):
                        ok = False

                # Helpers are shareable — no overlap check

                if ok:
                    slot_found  = True
                    slot_start  = proposed_start
                    slot_end    = proposed_end
                    break

                current += timedelta(minutes=1)

            # ── d / e. Record result ─────────────────────────────────────────
            if slot_found:
                # Block machines and reserve in occupancy
                for mid in step.required_machine_ids:
                    _block(occupancy, mid, slot_start, slot_end)
                if step.reserve_machine_id is not None:
                    _block(occupancy, step.reserve_machine_id, slot_start, slot_end)

                confirmed[step.id] = slot_end

                resolved.append(ScheduleEntry(
                    job_id=step.job_id,
                    step_id=step.id,
                    assigned_machine_ids=list(step.required_machine_ids),
                    assigned_helper_ids=list(step.required_helper_ids),
                    scheduled_start=slot_start,
                    scheduled_end=slot_end,
                ))

            else:
                # Determine best conflict reason
                if current + duration > shift_close and not resource_shift_ends:
                    reason = (
                        f"No available slot for step {step.sequence_order} "
                        f"before shift end"
                    )
                else:
                    # Identify the blocking resource by name
                    blocking_name = "unknown resource"
                    for mid in step.required_machine_ids:
                        if not _is_free(occupancy, mid, shift_close - duration, shift_close):
                            res = res_by_id.get(mid)
                            blocking_name = res.name if res else f"machine#{mid}"
                            break
                    if (
                        step.reserve_machine_id is not None
                        and blocking_name == "unknown resource"
                    ):
                        res = res_by_id.get(step.reserve_machine_id)
                        blocking_name = res.name if res else f"machine#{step.reserve_machine_id}"

                    # Check deadline too
                    if slot_end > job.deadline:
                        reason = (
                            f"Cannot complete step {step.sequence_order} "
                            f"before deadline {job.deadline.strftime('%Y-%m-%d %H:%M')}"
                        )
                    else:
                        reason = (
                            f"No available slot for {blocking_name} "
                            f"before shift end"
                        )

                unresolved.append(ConflictEntry(
                    job_id=step.job_id,
                    step_id=step.id,
                    sequence_order=step.sequence_order,
                    reason=reason,
                ))
                job_blocked = True   # subsequent steps of this job can't proceed

    return SchedulerResult(resolved=resolved, unresolved=unresolved)
