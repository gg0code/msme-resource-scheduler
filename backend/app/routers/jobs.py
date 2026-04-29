# app/routers/jobs.py - Version 1.2
# Branch: both
#
# FILE PURPOSE
# CRUD router for production jobs. Single source of truth for all job
# operations including create, read, update, delete, timer control, lock
# toggling, and real-time resource availability checking.
#
# WHO CALLS THIS FILE
#   app/main.py                    - registers router at prefix="/api/jobs"
#   frontend/src/api/api_jobs.ts   - list, get, create, update, delete, timer
#   frontend/src/pages/Jobs.tsx    - lock toggle via PATCH with is_locked
#   frontend/src/api/api_resource_availability.ts
#                                  - GET /{job_id}/resource-availability
#
# WHAT THIS FILE CALLS
#   app/database.py                - get_db (Session)
#   app/models/job.py              - Job, JobSkillRequirement, JobAssignment
#   app/models/employee.py         - Employee (resource-availability endpoint)
#   app/models/machine.py          - Machine  (resource-availability endpoint)
#   app/models/auth.py             - User
#   app/core/dependencies.py       - get_current_user, require_operational, require_top_tier
#   app/core/plan_limits.py        - check_plan_limit
#
# KEY DESIGN DECISIONS
# - job_to_dict() is the single serialiser for all job responses. Any field
#   added to the Job model must also be added here or the frontend won't see it.
# - is_locked is extracted from the PATCH payload before the generic setattr
#   loop to allow explicit handling and future validation hooks.
# - GET /{job_id}/resource-availability is defined BEFORE GET /{job_id} in
#   route order. FastAPI matches top-to-bottom; if /{job_id} came first it
#   would attempt to parse "resource-availability" as an integer and 422.
# - Resource availability computes live from job_assignments + date overlap.
#   No separate table — derived on every request so it is always current.
# - update_job restores original_start_date / original_end_date on any edit
#   so the scheduler treats the job as a fresh candidate on next run.

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import List, Optional, Any
from datetime import datetime, date, timezone

from app.database import get_db
from app.models.job import Job, JobSkillRequirement, JobAssignment
from app.models.employee import Employee
from app.models.machine import Machine
from app.core.dependencies import get_current_user, require_operational, require_top_tier
from app.core.plan_limits import check_plan_limit
from app.models.auth import User

router = APIRouter()


# ── Pydantic schemas ──────────────────────────────────────────────────────────

class RawMaterial(BaseModel):
    name: str
    quantity: float
    unit: str = "pcs"
    unit_cost: float


class SkillReqIn(BaseModel):
    skill_id: int
    min_skill_level: str = "Generic"
    employees_required: int = 1


class JobCreate(BaseModel):
    name: str
    customer: Optional[str] = None
    description: Optional[str] = None
    start_date: date
    end_date: date
    estimated_hours_per_day: float = 8.0
    tentative_profit: Optional[float] = None
    order_value: Optional[float] = None
    misc_cost: Optional[float] = None
    job_type: Optional[str] = None
    quantity: Optional[float] = None
    priority: str = "Medium"
    status: str = "Draft"
    notes: Optional[str] = None
    skill_requirements: List[SkillReqIn] = []
    raw_materials: Optional[List[Any]] = None


class JobUpdate(BaseModel):
    name: Optional[str] = None
    customer: Optional[str] = None
    description: Optional[str] = None
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    estimated_hours_per_day: Optional[float] = None
    tentative_profit: Optional[float] = None
    order_value: Optional[float] = None
    misc_cost: Optional[float] = None
    job_type: Optional[str] = None
    quantity: Optional[float] = None
    priority: Optional[str] = None
    status: Optional[str] = None
    notes: Optional[str] = None
    skill_requirements: Optional[List[SkillReqIn]] = None
    raw_materials: Optional[List[Any]] = None
    is_locked: Optional[bool] = None


class TimerAction(BaseModel):
    action: str  # start | pause | resume | end


# ── Helper ────────────────────────────────────────────────────────────────────

def job_to_dict(job: Job) -> dict:
    """
    Serialise a Job ORM object to a plain dict for API responses.

    Called by:   list_jobs, create_job, get_job, update_job, delete_job,
                 job_timer — every endpoint that returns a job
    Calls:       Nothing — pure serialisation, no DB calls
    Args:
        job: Job ORM instance with skill_requirements and assignments
             relationships already loaded
    Returns:
        dict with all job fields including nested skill_requirements,
        assigned_employees, and assigned_machines
    Side effects: None - pure function
    """
    return {
        "id":                    job.id,
        "name":                  job.name,
        "customer":              job.customer,
        "description":           job.description,
        "start_date":            str(job.start_date),
        "end_date":              str(job.end_date),
        "estimated_hours_per_day": job.estimated_hours_per_day,
        "tentative_profit":      job.tentative_profit,
        "order_value":           job.order_value,
        "misc_cost":             job.misc_cost,
        "job_type":              job.job_type,
        "quantity":              job.quantity,
        "priority":              job.priority,
        "status":                job.status,
        "notes":                 job.notes,
        "is_locked":             job.is_locked,
        "raw_materials":         job.raw_materials or [],
        "timer_status":          job.timer_status,
        "actual_start_at":       job.actual_start_at.isoformat() if job.actual_start_at else None,
        "actual_end_at":         job.actual_end_at.isoformat()   if job.actual_end_at   else None,
        "paused_seconds":        job.paused_seconds,
        "timer_log":             job.timer_log or [],
        "created_at":            job.created_at.isoformat() if job.created_at else None,
        # Rescheduled date tracking - non-null means scheduler moved this job.
        # Cleared to NULL whenever the user edits the job (see update_job).
        "original_start_date":   str(job.original_start_date) if job.original_start_date else None,
        "original_end_date":     str(job.original_end_date)   if job.original_end_date   else None,
        "skill_requirements": [
            {
                "id":                r.id,
                "skill_id":          r.skill_id,
                "min_skill_level":   r.min_skill_level,
                "employees_required": r.employees_required,
            }
            for r in job.skill_requirements
        ],
        "assigned_employees": [
            {
                "id":        a.employee.id,
                "full_name": a.employee.full_name,
                "department": a.employee.department,
            }
            for a in job.assignments if a.employee_id is not None
        ],
        "assigned_machines": [
            {
                "id":           a.machine.id,
                "name":         a.machine.name,
                "machine_type": a.machine.machine_type,
            }
            for a in job.assignments if a.machine_id is not None
        ],
    }


# ── Routes ────────────────────────────────────────────────────────────────────

@router.get("/")
def list_jobs(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Return all jobs for the current tenant ordered by start_date.

    Called by:   GET /api/jobs/ from frontend Jobs.tsx, Dashboard.tsx,
                 useScheduler.ts (via ['jobs'] query key)
    Calls:       job_to_dict() for each job
    Returns:     List of job dicts ordered by start_date ascending
    Side effects: None - read only
    """
    jobs = db.query(Job).filter(
        Job.tenant_id == current_user.tenant_id
    ).order_by(Job.start_date).all()
    return [job_to_dict(j) for j in jobs]


@router.post(
    "/",
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(check_plan_limit("jobs", Job))],
)
def create_job(
    payload: JobCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_operational()),
):
    """
    Create a new production job with optional skill requirements.

    Called by:   POST /api/jobs/ from frontend Jobs.tsx create form
    Calls:       check_plan_limit (dependency), job_to_dict
    Args:
        payload: JobCreate with name, dates, priority, optional skill_requirements
    Returns:     Created job dict (HTTP 201)
    Side effects: Inserts Job row + JobSkillRequirement rows, commits transaction
    """
    job = Job(
        tenant_id=current_user.tenant_id,
        name=payload.name, customer=payload.customer, description=payload.description,
        start_date=payload.start_date, end_date=payload.end_date,
        estimated_hours_per_day=payload.estimated_hours_per_day,
        tentative_profit=payload.tentative_profit, order_value=payload.order_value,
        misc_cost=payload.misc_cost, job_type=payload.job_type, quantity=payload.quantity,
        priority=payload.priority, status=payload.status, notes=payload.notes,
        raw_materials=payload.raw_materials or [],
        timer_status="idle", paused_seconds=0, timer_log=[],
    )
    db.add(job)
    db.flush()
    for r in payload.skill_requirements:
        db.add(JobSkillRequirement(
            tenant_id=job.tenant_id, job_id=job.id, skill_id=r.skill_id,
            min_skill_level=r.min_skill_level, employees_required=r.employees_required,
        ))
    db.commit()
    db.refresh(job)
    return job_to_dict(job)


# NOTE: defined BEFORE /{job_id} — FastAPI matches top-to-bottom.
# If /{job_id} appeared first, "resource-availability" would be parsed
# as a job_id integer and fail with 422 Unprocessable Entity.
@router.get("/{job_id}/resource-availability")
def get_resource_availability(
    job_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Compute real-time resource availability for every employee and machine
    assigned to a job, scoped to the job's date range.

    Called by:   GET /api/jobs/{job_id}/resource-availability
                 frontend api_resource_availability.ts -> Jobs.tsx detail panel
    Calls:       Employee, Machine, JobAssignment, Job queries
    Args:
        job_id: ID of the job to check resources for
    Returns:
        ResourceAvailabilityResponse dict with shape:
        {
          job_id, date_range, employees, machines, materials,
          error (only when no dates set)
        }
        employees: list of EmployeeAvailability (base_pct, allocated_pct,
                   free_pct, status, blocking_jobs)
        machines:  list of MachineAvailability (is_free, status, blocking_jobs)
        materials: always [] — reserved for v3.9.5 stock tracking
    Side effects: None - pure read, no writes
    """
    job = db.query(Job).filter(
        Job.id == job_id,
        Job.tenant_id == current_user.tenant_id,
    ).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    if not job.start_date or not job.end_date:
        return {
            "job_id":     job_id,
            "date_range": None,
            "employees":  [],
            "machines":   [],
            "materials":  [],
            "error":      "no_dates",
        }

    assignments = db.query(JobAssignment).filter(
        JobAssignment.job_id == job_id,
        JobAssignment.tenant_id == current_user.tenant_id,
    ).all()

    assigned_employee_ids = [a.employee_id for a in assignments if a.employee_id]
    assigned_machine_ids  = [a.machine_id  for a in assignments if a.machine_id]

    # ── Employees ─────────────────────────────────────────────────────────────
    # free_pct = base_availability_pct minus sum of allocation_pct from all
    # other active jobs assigned to this employee on overlapping dates.
    # Clamped to 0 — cannot be negative.
    employees_out = []
    for emp_id in assigned_employee_ids:
        emp = db.query(Employee).filter(
            Employee.id == emp_id,
            Employee.tenant_id == current_user.tenant_id,
        ).first()
        if not emp:
            continue

        overlapping = (
            db.query(JobAssignment)
            .join(Job, Job.id == JobAssignment.job_id)
            .filter(
                JobAssignment.employee_id == emp_id,
                JobAssignment.job_id != job_id,
                Job.tenant_id == current_user.tenant_id,
                Job.start_date <= job.end_date,
                Job.end_date   >= job.start_date,
                Job.status.notin_(["Completed", "Cancelled"]),
            )
            .all()
        )

        base_pct      = float(emp.base_availability_pct or 100)
        allocated_pct = sum(float(a.allocation_pct or 100) for a in overlapping)
        free_pct      = max(0.0, base_pct - allocated_pct)

        if free_pct <= 0:
            emp_status = "unavailable"
        elif allocated_pct > 0:
            emp_status = "partial"
        else:
            emp_status = "free"

        employees_out.append({
            "employee_id":   emp_id,
            "name":          emp.full_name,
            "base_pct":      base_pct,
            "allocated_pct": allocated_pct,
            "free_pct":      free_pct,
            "status":        emp_status,
            "blocking_jobs": [
                {
                    "job_id":         a.job_id,
                    "job_name":       a.job.name if a.job else f"Job #{a.job_id}",
                    "allocation_pct": float(a.allocation_pct or 100),
                }
                for a in overlapping
            ],
        })

    # ── Machines ──────────────────────────────────────────────────────────────
    # Machines are exclusive — any date overlap with another active job = busy.
    # Unlike employees there is no partial state: a machine is either free or not.
    machines_out = []
    for machine_id in assigned_machine_ids:
        machine = db.query(Machine).filter(
            Machine.id == machine_id,
            Machine.tenant_id == current_user.tenant_id,
        ).first()
        if not machine:
            continue

        overlapping = (
            db.query(JobAssignment)
            .join(Job, Job.id == JobAssignment.job_id)
            .filter(
                JobAssignment.machine_id == machine_id,
                JobAssignment.job_id != job_id,
                Job.tenant_id == current_user.tenant_id,
                Job.start_date <= job.end_date,
                Job.end_date   >= job.start_date,
                Job.status.notin_(["Completed", "Cancelled"]),
            )
            .all()
        )

        is_free = len(overlapping) == 0

        machines_out.append({
            "machine_id":    machine_id,
            "name":          machine.name,
            "is_free":       is_free,
            "status":        "free" if is_free else "busy",
            "blocking_jobs": [
                {
                    "job_id":     a.job_id,
                    "job_name":   a.job.name if a.job else f"Job #{a.job_id}",
                    "start_date": str(a.job.start_date) if a.job else None,
                    "end_date":   str(a.job.end_date)   if a.job else None,
                }
                for a in overlapping
            ],
        })

    return {
        "job_id":     job_id,
        "date_range": {"start": str(job.start_date), "end": str(job.end_date)},
        "employees":  employees_out,
        "machines":   machines_out,
        "materials":  [],
    }


@router.get("/{job_id}")
def get_job(
    job_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Return a single job by ID.

    Called by:   GET /api/jobs/{id} from frontend Jobs.tsx detail view
    Calls:       job_to_dict
    Args:
        job_id: ID of the job to fetch
    Returns:     Job dict or 404
    Side effects: None - read only
    """
    job = db.query(Job).filter(
        Job.id == job_id,
        Job.tenant_id == current_user.tenant_id,
    ).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job_to_dict(job)


@router.patch("/{job_id}")
def update_job(
    job_id: int,
    payload: JobUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_operational()),
):
    """
    Partial update of a job. Handles skill_requirements replacement and
    is_locked toggling as special cases outside the generic setattr loop.
    Restores original_start_date / original_end_date on any edit so the
    job becomes a fresh scheduling candidate on next auto-schedule run.

    Called by:   PATCH /api/jobs/{id} from frontend Jobs.tsx edit form
                 and lock/unlock toggle button
    Calls:       job_to_dict
    Args:
        job_id:  ID of the job to update
        payload: JobUpdate — all fields optional, only provided fields updated
    Returns:     Updated job dict or 404
    Side effects: Updates Job row, replaces JobSkillRequirement rows if
                  skill_requirements provided, commits transaction
    """
    job = db.query(Job).filter(
        Job.id == job_id,
        Job.tenant_id == current_user.tenant_id,
    ).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    update_data = payload.model_dump(exclude_unset=True)

    # Extract is_locked before the generic loop so it can be applied
    # explicitly after all other fields. This allows future validation
    # (e.g. block locking a job with no assignments) without touching
    # the generic field loop.
    new_lock_state = update_data.pop("is_locked", None)

    for field, value in update_data.items():
        if field == "skill_requirements":
            # Full replacement — delete existing then insert new rows
            db.query(JobSkillRequirement).filter(
                JobSkillRequirement.job_id == job_id
            ).delete()
            for r in (value or []):
                db.add(JobSkillRequirement(
                    tenant_id=job.tenant_id, job_id=job_id,
                    skill_id=r["skill_id"], min_skill_level=r["min_skill_level"],
                    employees_required=r["employees_required"],
                ))
        else:
            setattr(job, field, value)

    if new_lock_state is not None:
        job.is_locked = new_lock_state

    # Restore original dates on any edit — signals to the scheduler that
    # this job should be treated as a fresh candidate on next run.
    # Only restores if originals exist (i.e. scheduler had previously moved dates).
    if job.original_start_date is not None:
        job.start_date = job.original_start_date
        job.original_start_date = None
    if job.original_end_date is not None:
        job.end_date = job.original_end_date
        job.original_end_date = None

    db.commit()
    db.refresh(job)
    return job_to_dict(job)


@router.delete("/{job_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_job(
    job_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_top_tier()),
):
    """
    Permanently delete a job and all its related rows (cascade).

    Called by:   DELETE /api/jobs/{id} from frontend Jobs.tsx delete button
    Calls:       Nothing
    Args:
        job_id: ID of the job to delete
    Returns:     HTTP 204 No Content or 404
    Side effects: Deletes Job row — cascades to JobSkillRequirement,
                  JobAssignment, ScheduleEntry via DB ondelete="CASCADE"
    """
    job = db.query(Job).filter(
        Job.id == job_id,
        Job.tenant_id == current_user.tenant_id,
    ).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    db.delete(job)
    db.commit()


@router.post("/{job_id}/timer")
def job_timer(
    job_id: int,
    payload: TimerAction,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_operational()),
):
    """
    Advance the production timer state machine for a job.

    Valid transitions:
        idle    -> start
        running -> pause | end
        paused  -> resume | end
        ended   -> (no transitions)

    Called by:   POST /api/jobs/{id}/timer from frontend Jobs.tsx timer buttons
    Calls:       job_to_dict
    Args:
        job_id:  ID of the job
        payload: TimerAction with action in {start, pause, resume, end}
    Returns:     Updated job dict plus actual_duration_seconds and
                 actual_duration_hours (both null until job ends)
    Side effects: Updates timer_status, actual_start_at, actual_end_at,
                  paused_seconds, timer_log, status on the Job row, commits
    """
    job = db.query(Job).filter(
        Job.id == job_id,
        Job.tenant_id == current_user.tenant_id,
    ).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    action = payload.action
    now = datetime.now(timezone.utc)
    log = list(job.timer_log or [])
    valid_transitions = {
        "idle":    ["start"],
        "running": ["pause", "end"],
        "paused":  ["resume", "end"],
        "ended":   [],
    }

    if action not in valid_transitions.get(job.timer_status, []):
        raise HTTPException(
            status_code=400,
            detail=f"Cannot '{action}' when timer is '{job.timer_status}'",
        )

    log.append({"event": action, "timestamp": now.isoformat()})

    if action == "start":
        job.actual_start_at = now
        job.timer_status = "running"
        job.status = "In Progress"
    elif action == "pause":
        job.timer_status = "paused"
    elif action == "resume":
        pause_event = next((e for e in reversed(log[:-1]) if e["event"] == "pause"), None)
        if pause_event:
            paused_dur = (now - datetime.fromisoformat(pause_event["timestamp"])).seconds
            job.paused_seconds = (job.paused_seconds or 0) + paused_dur
        job.timer_status = "running"
    elif action == "end":
        if job.timer_status == "paused":
            pause_event = next((e for e in reversed(log[:-1]) if e["event"] == "pause"), None)
            if pause_event:
                paused_dur = (now - datetime.fromisoformat(pause_event["timestamp"])).seconds
                job.paused_seconds = (job.paused_seconds or 0) + paused_dur
        job.actual_end_at = now
        job.timer_status = "ended"
        job.status = "Completed"

    job.timer_log = log
    db.commit()
    db.refresh(job)

    actual_seconds = None
    if job.actual_start_at and job.actual_end_at:
        total = (job.actual_end_at - job.actual_start_at).seconds
        actual_seconds = total - (job.paused_seconds or 0)

    return {
        **job_to_dict(job),
        "actual_duration_seconds": actual_seconds,
        "actual_duration_hours":   round(actual_seconds / 3600, 2) if actual_seconds else None,
    }
