"""
```python
"""
backend/app/routers/scheduler_router.py

FILE PURPOSE
This file implements the main scheduling API endpoints for the ZetaOps Copilot workforce scheduler.
It serves as the bridge between the FastAPI web layer and the core scheduling engine, handling
data loading from the database, calling the pure Python scheduler, and persisting results back
to the database. Introduced in v3.0 and rewritten in v3.9.5 to read from Job/JobStep tables
instead of legacy SchedJob tables. This sits in the routers layer and orchestrates the entire
scheduling workflow while maintaining strict tenant isolation.

WHAT THIS FILE DOES — step by step
1. Defines SQLAlchemy model (ScheduleEntryModel) for persisting schedule results in database
2. Defines Pydantic response models for API serialization of schedule data
3. Implements helper functions to load scheduling data from Job/JobStep/Machine/Employee tables
4. Builds resource availability slots from Machine and Employee records with default shift times
5. Converts Job records to JobInput format with priority normalization and deadline calculation
6. Loads JobStep records and resolves required resources using fallback logic (step-level first, then job-level)
7. Identifies locked schedule entries that cannot be modified during rescheduling
8. Provides POST /api/scheduler/run endpoint that orchestrates the complete scheduling workflow
9. Provides GET /api/scheduler/entries endpoint to retrieve current schedule for a tenant
10. Handles persistence of new schedule results while preserving locked job schedules

KEY FUNCTIONS / CLASSES / COMPONENTS

Name         : ScheduleEntryModel
Type         : SQLAlchemy ORM class
Purpose      : Database model for persisting scheduled job steps with their assigned resources and time windows. Maps to the schedule_entries table and includes tenant_id for isolation, assigned machine/helper arrays, and scheduled start/end times.
Parameters   : N/A (database model)
Returns      : N/A (database model)
Calls        : None (passive model)
DB/API       : Represents schedule_entries table with tenant_id, job_id, step_id, resource arrays, timestamps
Side effects : None (model definition only)

Name         : _norm_priority
Type         : function
Purpose      : Normalizes Job.priority field from Title case (Critical/High/Medium/Low) to lowercase engine format (critical/urgent/low). This translation layer ensures the database can store human-readable priorities while the engine works with standardized values.
Parameters   : p (str) - priority string from Job.priority field, can be None or empty
Returns      : str - normalized priority ("critical", "urgent", or "low") with "low" as fallback
Calls        : None (pure function)
DB/API       : None
Side effects : None (pure function)

Name         : _tenant
Type         : FastAPI dependency function
Purpose      : Extracts tenant_id from authenticated user for use as FastAPI Depends parameter. Ensures all scheduling operations are scoped to the current user's tenant, implementing design principle #2 (tenant scoping).
Parameters   : current_user (User) - injected by get_current_user dependency
Returns      : int - tenant_id of the authenticated user
Calls        : app.core.dependencies.get_current_user via FastAPI dependency injection
DB/API       : None (uses pre-authenticated user)
Side effects : None

Name         : _load_resources
Type         : function
Purpose      : Builds ResourceSlot list from Machine and Employee database records for the scheduler engine. Converts database models to engine format, assigns default shift times (8AM-5PM) since Job model lacks shift fields, and categorizes machines vs helpers.
Parameters   : db (Session) - SQLAlchemy database session, tenant_id (int) - tenant scope filter
Returns      : List[ResourceSlot] - engine-compatible resource definitions with availability windows
Calls        : SQLAlchemy select queries on Machine and Employee models
DB/API       : Queries Machine and Employee tables filtered by tenant_id
Side effects : None (read-only)

Name         : _load_jobs
Type         : function
Purpose      : Converts Job database records to JobInput format for the scheduling engine. Filters out Completed/Cancelled jobs, normalizes priorities, calculates deadline timestamps from end_date, and sets default shift assignments.
Parameters   : db (Session) - SQLAlchemy database session, tenant_id (int) - tenant scope filter
Returns      : List[JobInput] - engine-compatible job definitions with priorities and deadlines
Calls        : _norm_priority for priority conversion, SQLAlchemy queries on Job model
DB/API       : Queries Job table excluding Completed/Cancelled status, filtered by tenant_id
Side effects : None (read-only)

Name         : _load_steps
Type         : function
Purpose      : Builds StepInput list from JobStep and StepResource tables with intelligent resource resolution fallback. If a step has explicit StepResource assignments, uses those; otherwise falls back to job-level JobAssignment resources if use_job_resources=True. This enables job-level resource assignment to work before per-step UI is built.
Parameters   : db (Session) - SQLAlchemy database session, tenant_id (int) - tenant scope filter
Returns      : List[StepInput] - engine-compatible step definitions with resolved resource requirements
Calls        : SQLAlchemy queries on JobStep, StepResource, JobAssignment models
DB/API       : Queries JobStep, StepResource, and JobAssignment tables for active jobs only
Side effects : None (read-only)

Name         : _load_locked_entries
Type         : function
Purpose      : Extracts existing schedule entries for locked jobs to create LockedEntry constraints for the engine. These represent committed time windows that cannot be rescheduled, ensuring the engine respects previously locked schedules during optimization.
Parameters   : db (Session) - SQLAlchemy database session, tenant_id (int) - tenant scope filter
Returns      : List[LockedEntry] - time window constraints for locked jobs with resource assignments
Calls        : SQLAlchemy queries on Job and ScheduleEntryModel
DB/API       : Queries Job table for is_locked=True jobs, then schedule_entries for those jobs
Side effects : None (read-only)

Name         : run_scheduler_endpoint
Type         : FastAPI endpoint
Purpose      : Main scheduling API that orchestrates the complete workflow: loads data from database, calls the pure Python scheduling engine, cleans up stale entries, and persists new results. Implements design principle #1 (engine computes, AI narrates) by handling all data persistence while letting the engine focus on optimization.
Parameters   : body (RunSchedulerRequest) - optional schedule_date parameter, db (Session) - database dependency, tenant_id (int) - tenant scope dependency
Returns      : SchedulerResult - JSON with resolved schedule entries and unresolved conflicts
Calls        : require_feature for feature flag check, all _load_* functions, run_scheduler from engine, database CRUD operations
DB/API       : Reads from Job/JobStep/Machine/Employee tables, writes to schedule_entries table
Side effects : Deletes stale schedule entries for unlocked jobs, creates new ScheduleEntryModel records, commits database transaction

WHO CALLS THIS FILE
- Frontend scheduling pages via axios API calls to POST /api/scheduler/run
- Frontend schedule display components via GET /api/scheduler/entries
- backend/app/main.py registers this router with /api prefix
- Potentially called by background tasks or other routers needing schedule data

IMPORTS EXPLAINED
- datetime, date, time, timezone: Handle scheduling timestamps and date calculations for deadlines and time windows
- typing List, Optional: Type hints for function parameters and return values in strict TypeScript-like Python
- fastapi APIRouter, Depends
"""

from __future__ import annotations

from datetime import date, datetime, time, timezone
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

# ─── Shift defaults (Job model has no shift field) ───────────────────────────

_DEFAULT_SHIFT_START = time(8, 0)
_DEFAULT_SHIFT_END   = time(17, 0)

# ─── Priority normalisation ───────────────────────────────────────────────────
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


# ─── DB Model for persisted schedule entries ─────────────────────────────────

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


# ─── Pydantic response models ─────────────────────────────────────────────────

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


# ─── Auth helper ─────────────────────────────────────────────────────────────

def _tenant(current_user=Depends(get_current_user)) -> int:
    return current_user.tenant_id  # noqa: used as FastAPI Depends


# ─── Loaders ─────────────────────────────────────────────────────────────────

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
    rows = db.scalars(
        select(Job).where(
            Job.tenant_id == tenant_id,
            Job.status.notin_(["Completed", "Cancelled"]),
        )
    ).all()
    return [
        JobInput(
            id=j.id,
            name=j.name,
            priority=_norm_priority(j.priority),
            expected_profit=j.tentative_profit,
            # Engine needs a datetime deadline — use end_date at shift close
            deadline=datetime(
                j.end_date.year, j.end_date.month, j.end_date.day,
                _DEFAULT_SHIFT_END.hour, _DEFAULT_SHIFT_END.minute,
            ),
            shift="morning",       # Job has no shift field — default morning
            lock_status=j.is_locked,
        )
        for j in rows
    ]


def _load_steps(db: Session, tenant_id: int) -> List[StepInput]:
    """
    Build StepInput list from JobStep + StepResource tables.

    Resource resolution per step (Option B fallback):
      1. If the step has explicit StepResource rows -> use those.
      2. If use_job_resources=True (default) and no step-level resources exist
         -> fall back to the job's JobAssignment rows (machines + employees).

    This means jobs with resources assigned at the job level will schedule
    correctly even before per-step resource assignment UI is built.
    """
    from app.models.job import JobAssignment

    # Only load steps for active jobs
    active_job_ids = db.scalars(
        select(Job.id).where(
            Job.tenant_id == tenant_id,
            Job.status.notin_(["Completed", "Cancelled"]),
        )
    ).all()
    if not active_job_ids:
        return []

    steps = db.scalars(
        select(JobStep).where(JobStep.job_id.in_(active_job_ids))
    ).all()
    if not steps:
        return []

    step_ids = [s.id for s in steps]

    # Step-level resources
    step_resources = db.scalars(
        select(StepResource).where(StepResource.step_id.in_(step_ids))
    ).all()

    step_machine_map: dict[int, list[int]] = {}
    step_helper_map:  dict[int, list[int]] = {}
    for r in step_resources:
        if r.resource_type == "machine" and r.resource_id:
            step_machine_map.setdefault(r.step_id, []).append(r.resource_id)
        elif r.resource_type == "employee" and r.resource_id:
            step_helper_map.setdefault(r.step_id, []).append(r.resource_id)

    # Job-level assignments (fallback when step has no specific resources)
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

    result = []
    for s in steps:
        has_step_resources = s.id in step_machine_map or s.id in step_helper_map
        if has_step_resources or not s.use_job_resources:
            machine_ids = step_machine_map.get(s.id, [])
            helper_ids  = step_helper_map.get(s.id, [])
        else:
            # Fallback: inherit machines and employees from job-level assignments
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


# ─── Endpoints ───────────────────────────────────────────────────────────────

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

    schedule_date = body.schedule_date or date.today()

    resources      = _load_resources(db, tenant_id)
    jobs           = _load_jobs(db, tenant_id)
    steps          = _load_steps(db, tenant_id)
    locked_entries = _load_locked_entries(db, tenant_id)

    result = run_scheduler(
        jobs=jobs,
        steps=steps,
        resources=resources,
        locked_entries=locked_entries,
        schedule_date=schedule_date,
    )

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
