"""
routers/jobs.py — V1.2
Changes:
  - create_job: auto-computes has_conflict after flush via check_availability()
  - update_job: re-computes has_conflict when dates/assignments change
  - POST /auto-schedule: runs scheduling engine on all unlocked jobs
  - GET /tenant: returns tenant info including job_id_prefix
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session, selectinload
from pydantic import BaseModel
from typing import List, Optional, Any
from datetime import datetime, date, timedelta

from app.database import get_db
from app.models.job import Job, JobSkillRequirement, JobAssignment
from app.core.dependencies import get_current_user, require_role
from app.core.plan_limits import check_plan_limit
from app.models.auth import User, Tenant
from app.models.unavailability import EmployeeLeave, MachineDowntime
from app.services.availability_engine import check_availability

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
    start_date: str
    end_date: str
    estimated_hours_per_day: float = 8.0
    tentative_profit: Optional[float] = None
    order_value: Optional[float] = None
    misc_cost: Optional[float] = None
    priority: str = "Medium"
    status: str = "Draft"
    notes: Optional[str] = None
    skill_requirements: List[SkillReqIn] = []
    raw_materials: Optional[List[Any]] = None
    start_mode: Optional[str] = "right_away"
    is_locked: Optional[bool] = False
    earliest_date: Optional[str] = None
    latest_date: Optional[str] = None
    delivery_date: Optional[str] = None
    invoice_number: Optional[str] = None
    invoice_date: Optional[str] = None
    payment_status: Optional[str] = None
    payment_amount: Optional[float] = None
    payment_date: Optional[str] = None
    job_type: Optional[str] = None
    quantity: Optional[float] = None

class JobUpdate(BaseModel):
    name: Optional[str] = None
    customer: Optional[str] = None
    description: Optional[str] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    estimated_hours_per_day: Optional[float] = None
    tentative_profit: Optional[float] = None
    order_value: Optional[float] = None
    misc_cost: Optional[float] = None
    priority: Optional[str] = None
    status: Optional[str] = None
    notes: Optional[str] = None
    skill_requirements: Optional[List[SkillReqIn]] = None
    raw_materials: Optional[List[Any]] = None
    start_mode: Optional[str] = None
    is_locked: Optional[bool] = None
    has_conflict: Optional[bool] = None
    earliest_date: Optional[str] = None
    latest_date: Optional[str] = None
    delivery_date: Optional[str] = None
    invoice_number: Optional[str] = None
    invoice_date: Optional[str] = None
    payment_status: Optional[str] = None
    payment_amount: Optional[float] = None
    payment_date: Optional[str] = None
    job_type: Optional[str] = None
    quantity: Optional[float] = None

class TimerAction(BaseModel):
    action: str  # start | pause | resume | end


# ── Helper: compute and persist has_conflict ──────────────────────────────────
def _refresh_conflict(db: Session, job: Job, tenant_id: int):
    """
    Run check_availability and write has_conflict back to the job row.
    Returns the AvailabilityResult (or None on error).
    Call after flush so job.id exists, but before final commit.
    """
    try:
        result = check_availability(db, job.id, tenant_id)
        job.has_conflict = not result.feasible
        return result
    except Exception:
        # Never crash a save because of conflict-check failure
        job.has_conflict = False
        return None


# ── Helper: cost overrun detection ───────────────────────────────────────────
def _cost_overrun(job: Job) -> dict | None:
    """Returns overrun info if actual_hours × resource_rates > estimated cost by >10%."""
    if not job.actual_hours or not job.start_date or not job.end_date:
        return None
    duration = max((job.end_date - job.start_date).days + 1, 1)
    estimated_hours = duration * (job.estimated_hours_per_day or 8)
    if estimated_hours <= 0:
        return None
    overrun_pct = ((job.actual_hours - estimated_hours) / estimated_hours) * 100
    if overrun_pct > 10:
        return {"overrun_pct": round(overrun_pct, 1), "actual_hours": round(job.actual_hours, 1), "estimated_hours": round(estimated_hours, 1)}
    return None


# ── Helper: serialize job ─────────────────────────────────────────────────────
def job_to_dict(job: Job) -> dict:
    return {
        "id": job.id,
        "name": job.name,
        "customer": job.customer,
        "description": job.description,
        "start_date": str(job.start_date),
        "end_date": str(job.end_date),
        "estimated_hours_per_day": job.estimated_hours_per_day,
        "tentative_profit": job.tentative_profit,
        "order_value": job.order_value,
        "misc_cost": job.misc_cost,
        "priority": job.priority,
        "status": job.status,
        "notes": job.notes,
        "raw_materials": job.raw_materials or [],
        "timer_status": job.timer_status,
        "actual_start_at": job.actual_start_at.isoformat() if job.actual_start_at else None,
        "actual_end_at": job.actual_end_at.isoformat() if job.actual_end_at else None,
        "paused_seconds": job.paused_seconds,
        "timer_log": job.timer_log or [],
        "start_mode": job.start_mode or "right_away",
        "is_locked": job.is_locked or False,
        "has_conflict": job.has_conflict or False,
        "earliest_date":  str(job.earliest_date)  if job.earliest_date  else None,
        "latest_date":    str(job.latest_date)    if job.latest_date    else None,
        # J1.2
        "delivery_date":  str(job.delivery_date)  if job.delivery_date  else None,
        "invoice_number": job.invoice_number,
        "invoice_date":   str(job.invoice_date)   if job.invoice_date   else None,
        "payment_status": job.payment_status or "Unpaid",
        "payment_amount": job.payment_amount,
        "payment_date":   str(job.payment_date)   if job.payment_date   else None,
        "actual_hours":   job.actual_hours,
        # v3.9.6
        "job_type": job.job_type,
        "quantity":  job.quantity,
        # Cost overrun flag: actual > estimated by >10%
        "cost_overrun": _cost_overrun(job),
        "created_at": job.created_at.isoformat() if job.created_at else None,
        "skill_requirements": [
            {"id": r.id, "skill_id": r.skill_id, "min_skill_level": r.min_skill_level,
             "employees_required": r.employees_required}
            for r in job.skill_requirements
        ],
        "assigned_employees": [
            {"id": a.employee.id, "full_name": a.employee.full_name,
             "department": a.employee.department,
             "allocation_pct": getattr(a, 'allocation_pct', None) or 100}
            for a in job.assignments if a.employee_id is not None
        ],
        "assigned_machines": [
            {"id": a.machine.id, "name": a.machine.name,
             "machine_type": a.machine.machine_type,
             "allocation_pct": getattr(a, 'allocation_pct', None) or 100}
            for a in job.assignments if a.machine_id is not None
        ],
    }


# ── PRIORITY ORDER ────────────────────────────────────────────────────────────
PRIORITY_RANK = {"Critical": 0, "High": 1, "Medium": 2, "Low": 3}


# ── Routes ────────────────────────────────────────────────────────────────────

@router.get("/tenant")
def get_tenant_info(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Return tenant info including job_id_prefix."""
    tenant = db.query(Tenant).filter(Tenant.id == current_user.tenant_id).first()
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")
    return {
        "id": tenant.id,
        "name": tenant.name,
        "slug": tenant.slug,
        "plan": tenant.plan,
        "job_id_prefix": getattr(tenant, "job_id_prefix", None),
    }


@router.get("/")
def list_jobs(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    jobs = (
        db.query(Job)
        .options(
            selectinload(Job.assignments).selectinload(JobAssignment.employee),
            selectinload(Job.assignments).selectinload(JobAssignment.machine),
            selectinload(Job.skill_requirements),
        )
        .filter(Job.tenant_id == current_user.tenant_id)
        .order_by(Job.start_date)
        .all()
    )
    return [job_to_dict(j) for j in jobs]


@router.post(
    "/",
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(check_plan_limit("jobs", Job))],
)
def create_job(
    payload: JobCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("proprietor", "scheduler")),
):
    job = Job(
        tenant_id=current_user.tenant_id,
        name=payload.name, customer=payload.customer, description=payload.description,
        start_date=payload.start_date, end_date=payload.end_date,
        estimated_hours_per_day=payload.estimated_hours_per_day,
        tentative_profit=payload.tentative_profit, order_value=payload.order_value,
        misc_cost=payload.misc_cost, priority=payload.priority,
        status=payload.status, notes=payload.notes,
        raw_materials=payload.raw_materials or [],
        start_mode=payload.start_mode or "right_away",
        is_locked=payload.is_locked or False,
        earliest_date=payload.earliest_date,
        latest_date=payload.latest_date,
        delivery_date=payload.delivery_date,
        invoice_number=payload.invoice_number,
        invoice_date=payload.invoice_date,
        payment_status=payload.payment_status or "Unpaid",
        payment_amount=payload.payment_amount,
        payment_date=payload.payment_date,
        job_type=payload.job_type,
        quantity=payload.quantity,
        has_conflict=False,
        timer_status="idle", paused_seconds=0, timer_log=[],
    )
    db.add(job)
    db.flush()  # get job.id without committing

    for r in payload.skill_requirements:
        db.add(JobSkillRequirement(
            tenant_id=current_user.tenant_id,
            job_id=job.id, skill_id=r.skill_id,
            min_skill_level=r.min_skill_level,
            employees_required=r.employees_required,
        ))
    db.flush()

    # ── Auto-compute conflict on create ──────────────────────────────────────
    _refresh_conflict(db, job, current_user.tenant_id)

    db.commit()
    db.refresh(job)

    # Reload with relationships
    job = (
        db.query(Job)
        .options(
            selectinload(Job.assignments).selectinload(JobAssignment.employee),
            selectinload(Job.assignments).selectinload(JobAssignment.machine),
            selectinload(Job.skill_requirements),
        )
        .filter(Job.id == job.id)
        .first()
    )
    return job_to_dict(job)


@router.get("/{job_id}")
def get_job(
    job_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    job = (
        db.query(Job)
        .options(
            selectinload(Job.assignments).selectinload(JobAssignment.employee),
            selectinload(Job.assignments).selectinload(JobAssignment.machine),
            selectinload(Job.skill_requirements),
        )
        .filter(Job.id == job_id, Job.tenant_id == current_user.tenant_id)
        .first()
    )
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job_to_dict(job)


@router.patch("/{job_id}")
def update_job(
    job_id: int,
    payload: JobUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("proprietor", "scheduler")),
):
    job = (
        db.query(Job)
        .options(
            selectinload(Job.assignments).selectinload(JobAssignment.employee),
            selectinload(Job.assignments).selectinload(JobAssignment.machine),
            selectinload(Job.skill_requirements),
        )
        .filter(Job.id == job_id, Job.tenant_id == current_user.tenant_id)
        .first()
    )
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    date_changed = False
    for field_name, value in payload.model_dump(exclude_unset=True).items():
        if field_name == "skill_requirements":
            db.query(JobSkillRequirement).filter(
                JobSkillRequirement.job_id == job_id
            ).delete()
            for r in (value or []):
                db.add(JobSkillRequirement(
                    tenant_id=current_user.tenant_id,
                    job_id=job_id, skill_id=r["skill_id"],
                    min_skill_level=r["min_skill_level"],
                    employees_required=r["employees_required"],
                ))
            date_changed = True  # skill changes can affect conflict
        elif field_name == "has_conflict":
            pass  # never accept client-supplied has_conflict — always compute it
        else:
            if field_name in ("start_date", "end_date", "earliest_date", "latest_date"):
                date_changed = True
            setattr(job, field_name, value)

    db.flush()

    # ── Auto-recompute conflict whenever dates or skills change ──────────────
    if date_changed:
        _refresh_conflict(db, job, current_user.tenant_id)

    db.commit()
    db.refresh(job)

    job = (
        db.query(Job)
        .options(
            selectinload(Job.assignments).selectinload(JobAssignment.employee),
            selectinload(Job.assignments).selectinload(JobAssignment.machine),
            selectinload(Job.skill_requirements),
        )
        .filter(Job.id == job_id)
        .first()
    )
    return job_to_dict(job)


@router.delete("/{job_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_job(
    job_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("proprietor")),
):
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
    current_user: User = Depends(require_role("proprietor", "scheduler")),
):
    job = (
        db.query(Job)
        .options(
            selectinload(Job.assignments).selectinload(JobAssignment.employee),
            selectinload(Job.assignments).selectinload(JobAssignment.machine),
            selectinload(Job.skill_requirements),
        )
        .filter(Job.id == job_id, Job.tenant_id == current_user.tenant_id)
        .first()
    )
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    action = payload.action
    now = datetime.utcnow()
    log = list(job.timer_log or [])
    valid_transitions = {
        "idle":    ["start"],
        "running": ["pause", "end"],
        "paused":  ["resume", "end"],
        "ended":   [],
    }

    if action not in valid_transitions.get(job.timer_status, []):
        raise HTTPException(status_code=400,
            detail=f"Cannot '{action}' when timer is '{job.timer_status}'")

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
        "actual_duration_hours": round(actual_seconds / 3600, 2) if actual_seconds else None,
    }


# ── AUTO-SCHEDULER ────────────────────────────────────────────────────────────

class AutoScheduleResult(BaseModel):
    scheduled: int
    skipped: int
    details: List[dict]

@router.post("/auto-schedule", response_model=AutoScheduleResult)
def auto_schedule(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("proprietor", "scheduler")),
):
    """
    Auto-scheduler: assign start/end dates to all UNLOCKED, non-completed jobs
    in priority order: Critical → High → Medium → Low, then by order_value desc.

    Algorithm:
    1. Collect all unlocked, active jobs sorted by priority then order_value.
    2. For each job, find the earliest available window starting from today
       (or earliest_date if set) where none of its assigned machines/employees
       are already occupied by a locked or previously-scheduled job.
    3. Set start_date / end_date, recompute has_conflict, save.

    Locked jobs are never moved — they act as fixed anchors.
    """
    tenant_id = current_user.tenant_id
    today = date.today()

    # Load ALL tenant jobs with assignments
    all_jobs = (
        db.query(Job)
        .options(
            selectinload(Job.assignments).selectinload(JobAssignment.employee),
            selectinload(Job.assignments).selectinload(JobAssignment.machine),
            selectinload(Job.skill_requirements),
        )
        .filter(Job.tenant_id == tenant_id)
        .all()
    )

    # Separate locked (anchors) from unlocked (to schedule)
    locked_jobs   = [j for j in all_jobs if j.is_locked or j.status in ("Completed", "Cancelled")]
    unlocked_jobs = [j for j in all_jobs if not j.is_locked and j.status not in ("Completed", "Cancelled")]

    # Sort unlocked by priority → order_value desc → profit margin desc
    def _profit_margin(j: Job) -> float:
        if not j.order_value or j.order_value <= 0:
            return 0.0
        return (j.tentative_profit or 0) / j.order_value * 100

    unlocked_jobs.sort(key=lambda j: (
        PRIORITY_RANK.get(j.priority, 99),
        -(j.order_value or 0),
        -_profit_margin(j),
    ))

    # Build occupancy map: resource_id → set of occupied dates (from locked jobs)
    # resource key: "emp:{id}" or "mach:{id}"
    occupied: dict[str, set] = {}

    def _date_range(start: date, end: date) -> list:
        days, cur = [], start
        while cur <= end:
            days.append(cur)
            cur += timedelta(days=1)
        return days

    def _occupy(job: Job):
        if not job.start_date or not job.end_date:
            return
        days = _date_range(job.start_date, job.end_date)
        for a in job.assignments:
            if a.employee_id:
                key = f"emp:{a.employee_id}"
                occupied.setdefault(key, set()).update(days)
            if a.machine_id:
                key = f"mach:{a.machine_id}"
                occupied.setdefault(key, set()).update(days)

    for j in locked_jobs:
        _occupy(j)

    # ── Block out employee leaves ─────────────────────────────────────────────
    emp_leaves = (
        db.query(EmployeeLeave)
        .filter(EmployeeLeave.tenant_id == tenant_id)
        .all()
    )
    for leave in emp_leaves:
        key = f"emp:{leave.employee_id}"
        occupied.setdefault(key, set()).update(
            _date_range(leave.start_date, leave.end_date)
        )

    # ── Block out machine downtimes ───────────────────────────────────────────
    mach_downtimes = (
        db.query(MachineDowntime)
        .filter(MachineDowntime.tenant_id == tenant_id)
        .all()
    )
    for dt in mach_downtimes:
        key = f"mach:{dt.machine_id}"
        occupied.setdefault(key, set()).update(
            _date_range(dt.start_date, dt.end_date)
        )

    def _duration_days(job: Job) -> int:
        if job.start_date and job.end_date:
            return (job.end_date - job.start_date).days
        return 7  # fallback: 1 week

    def _resources(job: Job):
        emp_keys  = [f"emp:{a.employee_id}"  for a in job.assignments if a.employee_id]
        mach_keys = [f"mach:{a.machine_id}"  for a in job.assignments if a.machine_id]
        return emp_keys + mach_keys

    def _find_slot(job: Job) -> Optional[date]:
        """Find earliest start date where all assigned resources are free."""
        duration = _duration_days(job)
        resources = _resources(job)

        # Respect earliest_date boundary
        earliest = today
        if job.start_mode == "flexible" and job.earliest_date:
            earliest = max(today, job.earliest_date)
        elif job.start_mode == "pick_a_date" and job.start_date:
            # Keep existing date if resources are free there
            candidate_days = _date_range(job.start_date, job.end_date)
            if all(
                d not in occupied.get(r, set())
                for r in resources for d in candidate_days
            ):
                return job.start_date
            earliest = job.start_date  # try from existing date

        # Scan forward up to 365 days to find a free window
        latest_boundary = None
        if job.start_mode == "flexible" and job.latest_date:
            latest_boundary = job.latest_date

        candidate = earliest
        for _ in range(365):
            candidate_end = candidate + timedelta(days=duration)
            if latest_boundary and candidate > latest_boundary:
                return None  # can't fit within boundary
            candidate_days = _date_range(candidate, candidate_end)
            if all(
                d not in occupied.get(r, set())
                for r in resources for d in candidate_days
            ):
                return candidate
            candidate += timedelta(days=1)

        return None  # couldn't find a slot

    scheduled_count = 0
    skipped_count   = 0
    details         = []

    for job in unlocked_jobs:
        slot = _find_slot(job)
        if slot is None:
            skipped_count += 1
            details.append({
                "job_id": job.id, "job_name": job.name,
                "result": "skipped", "reason": "No available slot found within constraints",
            })
            continue

        duration = _duration_days(job)
        new_end  = slot + timedelta(days=duration)

        old_start = str(job.start_date)
        job.start_date = slot
        job.end_date   = new_end
        db.flush()

        # Mark occupancy so subsequent jobs respect this slot
        _occupy(job)

        # Recompute conflict
        avail = _refresh_conflict(db, job, tenant_id)
        conflict_reasons = [c.reason for c in avail.conflicts] if avail and avail.conflicts else []

        scheduled_count += 1
        details.append({
            "job_id": job.id, "job_name": job.name,
            "result": "scheduled",
            "old_start": old_start,
            "new_start": str(slot),
            "new_end": str(new_end),
            "has_conflict": job.has_conflict,
            "conflict_reasons": conflict_reasons,
        })

    db.commit()

    return AutoScheduleResult(
        scheduled=scheduled_count,
        skipped=skipped_count,
        details=details,
    )
