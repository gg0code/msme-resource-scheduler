from __future__ import annotations
# app/routers/scheduler_router.py - Version 3.0
# Branch: both
#
# FILE PURPOSE
# Multi-day priority-based auto-scheduler for production jobs.
# Runs the scheduling engine across the full job date range, pushing
# lower-priority jobs to available slots when resources conflict.
#
# KEY DESIGN DECISIONS
# - Uses raw SQL (not ORM) for job date reads to avoid SQLAlchemy identity
#   map contamination when job dates are updated mid-run.
# - Synthetic steps (one per day) are generated for jobs with no JobStep rows.
#   sequence_order=1 for all so engine treats each day as independent.
# - Original dates captured before any writes so re-runs generate consistent
#   step counts regardless of how many times the scheduler has run.
# - Deadline extended by 60 days per job so pushed steps resolve past end_date.
# - range_end extended by 2x longest job to handle cascading pushes.
#
# WHO CALLS THIS FILE
# - POST /api/scheduler/run  - runs the scheduler for the tenant
# - GET  /api/scheduler/entries - returns all persisted schedule entries

from datetime import date, datetime, time, timedelta, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import Column, DateTime, Integer, select
from sqlalchemy.dialects.postgresql import ARRAY as PG_ARRAY
from sqlalchemy.orm import Session

from app.database import Base, get_db
from app.models.job import Job
from app.models.job_steps import JobStep, StepResource
from app.models.machine import Machine
from app.models.employee import Employee
from app.core.dependencies import get_current_user
from app.scheduler.engine import (
    ConflictEntry, JobInput, LockedEntry,
    ResourceSlot, ScheduleEntry, SchedulerResult,
    StepInput, run_scheduler,
)
from app.utils.feature_guard import require_feature

router = APIRouter()

# --- Shift defaults (Job model has no shift field) ---------------------------

_DEFAULT_SHIFT_START = time(8, 0)
_DEFAULT_SHIFT_END   = time(17, 0)

# --- Priority normalisation ---------------------------------------------------
# Job.priority uses Title case: Critical / High / Medium / Low
# Engine expects lowercase:     critical / urgent / low

def _norm_priority(p: str) -> str:
    mapping = {
        "critical": "critical",
        "high":     "urgent",
        "medium":   "low",
        "low":      "low",
    }
    return mapping.get((p or "").lower(), "low")


# --- DB Model for persisted schedule entries ---------------------------------

class ScheduleEntryModel(Base):
    __tablename__ = "schedule_entries"

    id                   = Column(Integer, primary_key=True, index=True)
    tenant_id            = Column(Integer, nullable=False, index=True)
    job_id               = Column(Integer, nullable=False, index=True)
    step_id              = Column(Integer, nullable=False)
    assigned_machine_ids = Column(PG_ARRAY(Integer), nullable=False, default=[])
    assigned_helper_ids  = Column(PG_ARRAY(Integer), nullable=False, default=[])
    scheduled_start      = Column(DateTime, nullable=False)
    scheduled_end        = Column(DateTime, nullable=False)
    created_at           = Column(DateTime, default=lambda: datetime.now(timezone.utc))


# --- Pydantic response models -------------------------------------------------

class ScheduleEntryOut(BaseModel):
    id:                   int
    tenant_id:            int
    job_id:               int
    step_id:              int
    assigned_machine_ids: List[int]
    assigned_helper_ids:  List[int]
    scheduled_start:      datetime
    scheduled_end:        datetime
    created_at:           datetime

    model_config = {"from_attributes": True}


class ConflictEntryOut(BaseModel):
    job_id:         int
    step_id:        int
    sequence_order: int
    reason:         str


class SchedulerResultOut(BaseModel):
    resolved:   List[ScheduleEntryOut]
    unresolved: List[ConflictEntryOut]


class RunSchedulerRequest(BaseModel):
    schedule_date: Optional[date] = None   # defaults to today


# --- Auth helper -------------------------------------------------------------

def _tenant(current_user=Depends(get_current_user)) -> int:
    return current_user.tenant_id


# --- Loaders -----------------------------------------------------------------

def _load_resources(db: Session, tenant_id: int) -> List[ResourceSlot]:
    """
    Build ResourceSlot list from Machine + Employee tables.
    Machines → type='machine', Employees → type='helper'.
    Shift times default to 08:00–17:00 (Job model has no shift field).
    """
    slots: List[ResourceSlot] = []

    machines = db.scalars(
        select(Machine).where(Machine.tenant_id == tenant_id)
    ).all()
    for m in machines:
        slots.append(ResourceSlot(
            id=m.id,
            name=m.name,
            type="machine",
            shift_start=_DEFAULT_SHIFT_START,
            shift_end=_DEFAULT_SHIFT_END,
        ))

    employees = db.scalars(
        select(Employee).where(Employee.tenant_id == tenant_id)
    ).all()
    for e in employees:
        slots.append(ResourceSlot(
            id=e.id,
            name=e.full_name,
            type="helper",
            shift_start=_DEFAULT_SHIFT_START,
            shift_end=_DEFAULT_SHIFT_END,
        ))

    return slots


def _load_jobs(db: Session, tenant_id: int) -> List[JobInput]:
    """
    Build JobInput list from the Job table.
    Skips Completed and Cancelled jobs — no point scheduling them.
    """
    # Use raw SQL to get job data - ORM objects share session state and
    # may reflect scheduler-updated end_date values from mid-run updates.
    # The deadline MUST use original_end_date (user's requested window) so
    # pushed steps can still schedule beyond the original end_date.
    from sqlalchemy import text as _tjobs
    raw = db.execute(
        _tjobs(
            "SELECT id, name, priority, tentative_profit, end_date, "
            "original_end_date, is_locked "
            "FROM jobs WHERE tenant_id = :tid "
            "AND status NOT IN ('Completed', 'Cancelled')"
        ),
        {"tid": tenant_id},
    ).all()

    result = []
    for r in raw:
        # Deadline = original_end_date if set (user's request), else end_date.
        # Add max_job_days buffer so pushed steps can resolve beyond original end.
        deadline_date = r[5] or r[4]  # original_end_date or end_date
        # Extend deadline 60 days beyond user-requested end so pushed steps
        # resolve past the original end_date. The date range loop enforces
        # the actual scheduling window - the engine deadline is just a hard stop.
        deadline_dt = datetime(
            deadline_date.year, deadline_date.month, deadline_date.day,
            _DEFAULT_SHIFT_END.hour, _DEFAULT_SHIFT_END.minute,
        ) + timedelta(days=60)
        result.append(JobInput(
            id=r[0],
            name=r[1],
            priority=_norm_priority(r[2]),
            expected_profit=r[3],
            deadline=deadline_dt,
            shift="morning",
            lock_status=bool(r[6]),
        ))
    return result


def _load_steps(db: Session, tenant_id: int) -> List[StepInput]:
    """
    Build StepInput list from JobStep + StepResource tables.

    Handles two cases:
      1. Jobs WITH steps: uses real JobStep rows. Resource resolution per step:
         a. If the step has explicit StepResource rows -> use those.
         b. If use_job_resources=True (default) and no step-level resources exist
            -> fall back to the job-level JobAssignment rows.
      2. Jobs WITHOUT steps: auto-synthesises one default step per job using:
         - duration = estimated_hours_per_day x job_days x 60 minutes
         - resources = all job-level JobAssignment rows (machines + employees)
         - sequence_order = 1, step_type = "regular"
         - id uses a negative synthetic ID: -(job_id * 1000) to avoid clashing
           with real step IDs which are always positive integers

    This ensures simple jobs (no step breakdown) participate fully in conflict
    detection and auto-scheduling alongside complex jobs that have detailed steps.
    A real-world MSME will have both types simultaneously.

    IMPORTANT: job duration is read using raw SQL (not ORM) to avoid SQLAlchemy
    identity map contamination. The scheduler updates job.end_date mid-run;
    if we used ORM objects, subsequent calls within the same session would see
    the updated (shorter) end_date and generate fewer synthetic steps.
    """
    from app.models.job import JobAssignment

    # Load job durations via raw SQL to get uncontaminated original values.
    # This bypasses SQLAlchemy identity map so we always see committed DB values.
    from sqlalchemy import text as _text  # noqa - local import avoids circular dep
    raw_jobs = db.execute(
        _text(
            "SELECT id, start_date, end_date, original_start_date, original_end_date, "
            "estimated_hours_per_day "
            "FROM jobs WHERE tenant_id = :tid "
            "AND status NOT IN ('Completed', 'Cancelled')"
        ),
        {"tid": tenant_id},
    ).all()
    if not raw_jobs:
        return []

    # Build a plain dict snapshot - no ORM tracking, immune to session updates
    job_snapshot: dict[int, dict] = {
        row[0]: {
            "start_date":          row[1],
            "end_date":            row[2],
            "original_start_date": row[3],
            "original_end_date":   row[4],
            "hours_per_day":       row[5],
        }
        for row in raw_jobs
    }

    active_job_ids = list(job_snapshot.keys())

    # Still need ORM objects for relationships (assignments, steps)
    active_jobs = db.scalars(
        select(Job).where(
            Job.tenant_id == tenant_id,
            Job.status.notin_(["Completed", "Cancelled"]),
        )
    ).all()
    active_job_map: dict[int, Job] = {j.id: j for j in active_jobs}

    # Load all real steps for active jobs
    real_steps = db.scalars(
        select(JobStep).where(JobStep.job_id.in_(active_job_ids))
    ).all()

    # Track which jobs have real steps defined
    jobs_with_steps: set[int] = {s.job_id for s in real_steps}

    # Step-level explicit resource overrides
    step_ids = [s.id for s in real_steps]
    step_resources = db.scalars(
        select(StepResource).where(StepResource.step_id.in_(step_ids))
    ).all() if step_ids else []

    step_machine_map: dict[int, list[int]] = {}
    step_helper_map:  dict[int, list[int]] = {}
    for r in step_resources:
        if r.resource_type == "machine" and r.resource_id:
            step_machine_map.setdefault(r.step_id, []).append(r.resource_id)
        elif r.resource_type == "employee" and r.resource_id:
            step_helper_map.setdefault(r.step_id, []).append(r.resource_id)

    # Job-level assignments used as fallback for both real steps and synthetic steps
    job_assignments = db.scalars(
        select(JobAssignment).where(JobAssignment.job_id.in_(active_job_ids))
    ).all()

    job_machine_map: dict[int, list[int]] = {}
    job_helper_map:  dict[int, list[int]] = {}
    for a in job_assignments:
        if a.machine_id:
            job_machine_map.setdefault(a.job_id, []).append(a.machine_id)
        if a.employee_id:
            job_helper_map.setdefault(a.job_id, []).append(a.employee_id)

    result: list[StepInput] = []

    # --- Real steps for jobs that have them -----------------------------------
    for s in real_steps:
        has_step_resources = s.id in step_machine_map or s.id in step_helper_map
        if has_step_resources or not s.use_job_resources:
            # Use step-level resource assignments
            machine_ids = step_machine_map.get(s.id, [])
            helper_ids  = step_helper_map.get(s.id, [])
        else:
            # Inherit from job-level assignments (Option B fallback)
            machine_ids = job_machine_map.get(s.job_id, [])
            helper_ids  = job_helper_map.get(s.job_id, [])

        result.append(StepInput(
            id=s.id,
            job_id=s.job_id,
            sequence_order=s.sequence_no,
            step_type="setup" if s.step_type == "setup" else "regular",
            duration_minutes=s.duration_minutes,
            required_machine_ids=machine_ids,
            required_helper_ids=helper_ids,
            reserve_machine_id=None,
        ))

    # --- Synthetic steps for jobs with no steps defined ----------------------
    # Simple jobs (no step breakdown) get one synthetic step per working day.
    # This is correct because the scheduler engine operates on a single
    # schedule_date and finds slots within a shift window (08:00-17:00).
    # A 7-day job needs 7 daily steps, not one 56-hour mega-step that can
    # never fit in a single shift. Each daily step = estimated_hours_per_day
    # minutes of work, representing that day's portion of the job.
    #
    # Synthetic step ID scheme: -(job_id * 1000 + day_offset)
    #   day_offset 0 = first day, 1 = second day, etc.
    #   Always negative to guarantee no clash with real step IDs (positive ints).
    # Capture original dates for jobs that don't have them yet.
    # Must happen BEFORE generating steps so ref_start/ref_end are correct
    # even on the very first scheduler run. Once captured, original dates
    # never change - they represent the user's requested scheduling window.
    for job_id, snap in job_snapshot.items():
        if snap["original_start_date"] is None or snap["original_end_date"] is None:
            db.execute(
                _text(
                    "UPDATE jobs SET "
                    "original_start_date = COALESCE(original_start_date, start_date), "
                    "original_end_date   = COALESCE(original_end_date,   end_date) "
                    "WHERE id = :jid AND tenant_id = :tid"
                ),
                {"jid": job_id, "tid": tenant_id},
            )
            # Update snapshot so this run uses the correct values
            if snap["original_start_date"] is None:
                snap["original_start_date"] = snap["start_date"]
            if snap["original_end_date"] is None:
                snap["original_end_date"] = snap["end_date"]
    db.flush()  # Write originals before generating steps

    for job_id in active_job_ids:
        if job_id in jobs_with_steps:
            continue  # Real steps handled above

        snap = job_snapshot[job_id]

        # Use raw SQL snapshot values for duration calculation.
        # This is immune to SQLAlchemy identity map: if this session has
        # already updated job.end_date (from a prior scheduler run), the
        # ORM object reflects the new shorter date. Raw snapshot always
        # has the committed DB value from before this run started.
        # Prefer original dates (user's requested window) over current dates
        # so re-runs always generate the same number of steps.
        ref_start = snap["original_start_date"] or snap["start_date"]
        ref_end   = snap["original_end_date"]   or snap["end_date"]
        job_days  = max(1, (ref_end - ref_start).days + 1)
        duration_per_day = int((snap["hours_per_day"] or 8.0) * 60)
        machines = job_machine_map.get(job_id, [])
        helpers  = job_helper_map.get(job_id, [])

        for day_offset in range(job_days):
            synthetic_step_id = -(job_id * 1000 + day_offset)
            result.append(StepInput(
                id=synthetic_step_id,
                job_id=job_id,
                # sequence_order = 1 for ALL synthetic steps.
                # Each synthetic step represents one independent day of work.
                # Days don't depend on each other - Monday's work doesn't
                # require Sunday to be confirmed first. Using sequence_order=1
                # for all ensures the engine's sequential gate never blocks them.
                sequence_order=1,
                step_type="regular",
                duration_minutes=duration_per_day,
                required_machine_ids=machines,
                required_helper_ids=helpers,
                reserve_machine_id=None,
            ))

    return result


def _load_locked_entries(db: Session, tenant_id: int) -> List[LockedEntry]:
    """
    Build LockedEntry list from existing schedule_entries for locked jobs.
    These represent committed windows the scheduler must not overwrite.
    """
    locked_job_ids = db.scalars(
        select(Job.id).where(
            Job.tenant_id == tenant_id,
            Job.is_locked == True,
        )
    ).all()
    if not locked_job_ids:
        return []

    entries = db.scalars(
        select(ScheduleEntryModel).where(
            ScheduleEntryModel.tenant_id == tenant_id,
            ScheduleEntryModel.job_id.in_(locked_job_ids),
        )
    ).all()

    locked: List[LockedEntry] = []
    for e in entries:
        for mid in (e.assigned_machine_ids or []):
            locked.append(LockedEntry(
                job_id=e.job_id, step_id=e.step_id,
                resource_id=mid, resource_type="machine",
                start=e.scheduled_start, end=e.scheduled_end,
            ))
        for hid in (e.assigned_helper_ids or []):
            locked.append(LockedEntry(
                job_id=e.job_id, step_id=e.step_id,
                resource_id=hid, resource_type="helper",
                start=e.scheduled_start, end=e.scheduled_end,
            ))
    return locked


# --- Endpoints ---------------------------------------------------------------

@router.post("/scheduler/run")
def run_scheduler_endpoint(
    body: RunSchedulerRequest = RunSchedulerRequest(),
    db: Session = Depends(get_db),
    tenant_id: int = Depends(_tenant),
):
    # Feature flag guard
    guard = require_feature("scheduler")
    if guard:
        return guard

    resources      = _load_resources(db, tenant_id)
    jobs           = _load_jobs(db, tenant_id)
    steps          = _load_steps(db, tenant_id)
    locked_entries = _load_locked_entries(db, tenant_id)

    # Run the scheduler across the full date range of all active jobs.
    # The engine is a single-day slot finder - it assigns work for one date
    # at a time within a shift window (08:00-17:00). Multi-day jobs require
    # multiple passes: one per working day. Each pass carries forward the
    # occupancy from previous days so resource conflicts are detected correctly
    # across the entire planning horizon.
    #
    # Date range: from earliest job start_date to latest job end_date.
    # Falls back to today if no jobs have dates (shouldn't happen in practice).
    # Load active job date ranges via raw SQL to avoid SQLAlchemy identity map.
    # The scheduler updates job.start_date / end_date mid-run; ORM objects would
    # reflect those changes in subsequent reads within the same session.
    # Raw SQL always returns the committed DB values from before this run.
    from sqlalchemy import text as _text2  # noqa
    raw_active = db.execute(
        _text2(
            "SELECT id, start_date, end_date, original_start_date, original_end_date "
            "FROM jobs WHERE tenant_id = :tid "
            "AND status NOT IN ('Completed', 'Cancelled')"
        ),
        {"tid": tenant_id},
    ).all()

    if raw_active:
        # Use original dates when available so range covers the user's requested window
        def _ref_start(row): return row[3] or row[1]  # original_start or start
        def _ref_end(row):   return row[4] or row[2]  # original_end   or end

        range_start = min(_ref_start(r) for r in raw_active)
        range_end   = max(_ref_end(r)   for r in raw_active)
        max_job_days = max(
            max(1, (_ref_end(r) - _ref_start(r)).days + 1)
            for r in raw_active
        )
        # Buffer = 2x longest job duration to handle cascading pushes.
        # When multiple jobs compete for the same resources, lower-priority
        # jobs get pushed further than a single job duration would cover.
        range_end = range_end + timedelta(days=max_job_days * 2)
    else:
        range_start = range_end = date.today()

    # Build a plain dict map for preferred_date calculation in the day loop.
    # Keyed by job_id, value is the reference start_date (original if available).
    active_job_map: dict[int, date] = {
        row[0]: (row[3] or row[1])  # original_start_date or start_date
        for row in raw_active
    }

    # Override with explicit schedule_date if caller provides one
    if body.schedule_date:
        range_start = range_end = body.schedule_date

    # Accumulate resolved/unresolved across all days
    all_resolved:   list = []
    all_unresolved: list = []

    # Track step IDs already resolved so we don't re-schedule them
    resolved_step_ids: set = set()
    # Build locked entries once - these never change across the loop
    locked_entries_base = locked_entries

    current_date = range_start
    one_day = timedelta(days=1)

    while current_date <= range_end:
        # Build locked_entries for this day = base locked entries
        # + everything resolved on previous days (so resources stay blocked)
        day_locked: list = list(locked_entries_base)
        for entry in all_resolved:
            for mid in (entry.assigned_machine_ids or []):
                day_locked.append(LockedEntry(
                    job_id=entry.job_id, step_id=entry.step_id,
                    resource_id=mid, resource_type="machine",
                    start=entry.scheduled_start, end=entry.scheduled_end,
                ))

        # Only pass steps not yet resolved.
        # For synthetic steps (negative IDs), only pass the step matching
        # today's date offset from the job's start_date. This ensures each
        # daily synthetic step is scheduled on its correct calendar date,
        # not all on the same day.
        day_steps = []
        for s in steps:
            if s.id in resolved_step_ids:
                continue
            if s.id >= 0:
                # Real step - always include if not yet resolved
                day_steps.append(s)
            else:
                # Synthetic step scheduling rule:
                # Each synthetic step has a preferred date = job.start_date + day_offset.
                # On the preferred date, try to schedule it (may be blocked by higher priority).
                # If blocked, the step stays unresolved and is retried on every subsequent day
                # until a free slot is found. This is what allows lower-priority jobs to be
                # pushed past higher-priority jobs and still complete all their days.
                # ID scheme: -(job_id * 1000 + day_offset), so:
                #   day_offset = (-s.id) % 1000
                #   job_id    = (-s.id) // 1000
                day_offset = (-s.id) % 1000
                job_id_from_step = (-s.id) // 1000
                # active_job_map[job_id] is a plain date (reference start_date)
                ref_job_start = active_job_map.get(job_id_from_step)
                if ref_job_start is not None:
                    preferred_date = ref_job_start + timedelta(days=day_offset)
                    # Include step on its preferred date OR any later date (retry if blocked)
                    if current_date >= preferred_date:
                        day_steps.append(s)

        remaining_steps = day_steps

        if not remaining_steps:
            current_date += one_day
            continue  # No steps eligible today - move to next day

        day_result = run_scheduler(
            jobs=jobs,
            steps=remaining_steps,
            resources=resources,
            locked_entries=day_locked,
            schedule_date=current_date,
        )

        for entry in day_result.resolved:
            all_resolved.append(entry)
            resolved_step_ids.add(entry.step_id)

        for conflict in day_result.unresolved:
            # Only record conflicts for steps that truly cannot be resolved
            # (step 1 of each job failing on day 1 should be retried on day 2)
            # We only finalise a conflict when all days are exhausted
            pass  # Collect after loop

        current_date += one_day

    # After all days: any step not in resolved_step_ids is a true conflict
    # Steps with no resources assigned are silently skipped - they are not
    # ready to schedule and should not appear as conflicts. The job's
    # 0% Feasibility badge already signals that resources need to be assigned.
    from app.scheduler.engine import ConflictEntry as EngineConflict
    for step in steps:
        if step.id in resolved_step_ids:
            continue
        has_resources = bool(step.required_machine_ids or step.required_helper_ids)
        if not has_resources:
            continue  # No resources assigned - not a conflict, job not ready
        # Build a human-readable reason identifying which resource was blocked
        # Use machine names from the resource list if available
        res_map = {r.id: r.name for r in resources}
        blocked_names = [res_map.get(mid, f"machine#{mid}")
                         for mid in step.required_machine_ids]
        resource_str = ", ".join(blocked_names) if blocked_names else "assigned resources"
        all_unresolved.append(EngineConflict(
            job_id=step.job_id,
            step_id=step.id,
            sequence_order=step.sequence_order,
            reason=(
                f"Resource conflict: {resource_str} fully booked "
                f"by a higher-priority job on overlapping dates. "
                f"Run auto-schedule after adjusting dates or priority."
            ),
        ))

    # Build final result object
    from app.scheduler.engine import SchedulerResult as EngineResult
    result = EngineResult(resolved=all_resolved, unresolved=all_unresolved)

    locked_job_ids = {j.id for j in jobs if j.lock_status}

    # Delete stale entries for unlocked jobs
    stale = db.scalars(
        select(ScheduleEntryModel).where(
            ScheduleEntryModel.tenant_id == tenant_id,
            ScheduleEntryModel.job_id.not_in(locked_job_ids) if locked_job_ids
            else ScheduleEntryModel.tenant_id == tenant_id,
        )
    ).all()
    for row in stale:
        if row.job_id not in locked_job_ids:
            db.delete(row)
    db.flush()

    # Persist resolved entries for unlocked jobs
    for entry in result.resolved:
        if entry.job_id in locked_job_ids:
            continue
        db.add(ScheduleEntryModel(
            tenant_id=tenant_id,
            job_id=entry.job_id,
            step_id=entry.step_id,
            assigned_machine_ids=entry.assigned_machine_ids,
            assigned_helper_ids=entry.assigned_helper_ids,
            scheduled_start=entry.scheduled_start,
            scheduled_end=entry.scheduled_end,
        ))

    # --- Update job start_date and end_date from scheduled slots ---------------
    # For jobs that were successfully scheduled (at least one step resolved),
    # update the job's start_date and end_date to reflect the actual scheduled
    # window. This is what the user sees in the Jobs page timeline.
    # Locked jobs are not updated - their dates are fixed by design.
    # Jobs with conflicts (some steps unresolved) are also not updated -
    # their dates remain as-is so the user can see the original request.
    resolved_by_job: dict[int, list] = {}
    for entry in result.resolved:
        resolved_by_job.setdefault(entry.job_id, []).append(entry)

    # Update dates for ALL resolved jobs - including those with some conflicts.
    # The scheduler pushes lower-priority jobs to available slots beyond their
    # original dates. The updated dates reflect what was actually scheduled.
    # Jobs with zero steps resolved keep their original dates (not in resolved_by_job).
    for job_id, entries in resolved_by_job.items():
        if job_id in locked_job_ids:
            continue  # Never move locked job dates

        # Find earliest scheduled start and latest scheduled end for this job
        earliest = min(e.scheduled_start for e in entries).date()
        latest   = max(e.scheduled_end   for e in entries).date()

        job_row = db.scalars(
            select(Job).where(Job.id == job_id, Job.tenant_id == tenant_id)
        ).first()
        if job_row:
            # Always capture original dates on first scheduling run.
            # Do this BEFORE updating start/end_date so we save the user's
            # requested dates. This powers both the "Rescheduled" icon in
            # the UI and the synthetic step count on re-runs.
            # Condition: original not yet set AND dates are actually changing.
            # We set original_end_date independently of original_start_date
            # because only end_date may change (job pushed later, same start).
            if job_row.original_start_date is None and job_row.start_date != earliest:
                job_row.original_start_date = job_row.start_date
            if job_row.original_end_date is None and job_row.end_date != latest:
                job_row.original_end_date = job_row.end_date
            job_row.start_date = earliest
            job_row.end_date   = latest

    db.commit()

    # Reload saved rows to get DB-assigned IDs
    saved = db.scalars(
        select(ScheduleEntryModel).where(
            ScheduleEntryModel.tenant_id == tenant_id,
            ScheduleEntryModel.step_id.in_([e.step_id for e in result.resolved]),
        )
    ).all()
    saved_map = {row.step_id: row for row in saved}

    resolved_out = []
    for entry in result.resolved:
        row = saved_map.get(entry.step_id)
        if row:
            resolved_out.append(ScheduleEntryOut.model_validate(row))
        else:
            resolved_out.append(ScheduleEntryOut(
                id=0, tenant_id=tenant_id,
                job_id=entry.job_id, step_id=entry.step_id,
                assigned_machine_ids=entry.assigned_machine_ids,
                assigned_helper_ids=entry.assigned_helper_ids,
                scheduled_start=entry.scheduled_start,
                scheduled_end=entry.scheduled_end,
                created_at=datetime.now(timezone.utc),
            ))

    return SchedulerResultOut(
        resolved=resolved_out,
        unresolved=[
            ConflictEntryOut(
                job_id=c.job_id, step_id=c.step_id,
                sequence_order=c.sequence_order, reason=c.reason,
            )
            for c in result.unresolved
        ],
    )


@router.get("/scheduler/entries")
def get_schedule_entries(
    db: Session = Depends(get_db),
    tenant_id: int = Depends(_tenant),
):
    guard = require_feature("scheduler")
    if guard:
        return guard

    rows = db.scalars(
        select(ScheduleEntryModel)
        .where(ScheduleEntryModel.tenant_id == tenant_id)
        .order_by(ScheduleEntryModel.scheduled_start)
    ).all()
    return [ScheduleEntryOut.model_validate(r) for r in rows]
