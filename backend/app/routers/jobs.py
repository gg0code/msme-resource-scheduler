"""
routers/jobs.py — V1.1
Added: JWT auth, tenant_id scoping, RBAC, plan limit enforcement
  GET    — any authenticated user
  POST   — scheduler+ (+ free plan: max 5 jobs)
  PATCH  — scheduler+
  DELETE — proprietor only
  timer  — scheduler+
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import List, Optional, Any
from datetime import datetime

from app.database import get_db
from app.models.job import Job, JobSkillRequirement, JobAssignment
from app.core.dependencies import get_current_user, require_role
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

class TimerAction(BaseModel):
    action: str  # start | pause | resume | end


# ── Helper ────────────────────────────────────────────────────────────────────
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
        "created_at": job.created_at.isoformat() if job.created_at else None,
        # Rescheduled date tracking - non-null means scheduler moved this job
        "original_start_date": str(job.original_start_date) if job.original_start_date else None,
        "original_end_date":   str(job.original_end_date)   if job.original_end_date   else None,
        "skill_requirements": [
            {"id": r.id, "skill_id": r.skill_id, "min_skill_level": r.min_skill_level, "employees_required": r.employees_required}
            for r in job.skill_requirements
        ],
        "assigned_employees": [
            {"id": a.employee.id, "full_name": a.employee.full_name, "department": a.employee.department}
            for a in job.assignments if a.employee_id is not None
        ],
        "assigned_machines": [
            {"id": a.machine.id, "name": a.machine.name, "machine_type": a.machine.machine_type}
            for a in job.assignments if a.machine_id is not None
        ],
    }


# ── Routes ────────────────────────────────────────────────────────────────────
@router.get("/")
def list_jobs(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
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
        timer_status="idle", paused_seconds=0, timer_log=[],
    )
    db.add(job)
    db.flush()
    for r in payload.skill_requirements:
        db.add(JobSkillRequirement(
            tenant_id=job.tenant_id, job_id=job.id, skill_id=r.skill_id,
            min_skill_level=r.min_skill_level, employees_required=r.employees_required))
    db.commit()
    db.refresh(job)
    return job_to_dict(job)


@router.get("/{job_id}")
def get_job(
    job_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
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
    current_user: User = Depends(require_role("proprietor", "scheduler")),
):
    job = db.query(Job).filter(
        Job.id == job_id,
        Job.tenant_id == current_user.tenant_id,
    ).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    for field, value in payload.model_dump(exclude_unset=True).items():
        if field == "skill_requirements":
            db.query(JobSkillRequirement).filter(JobSkillRequirement.job_id == job_id).delete()
            for r in (value or []):
                db.add(JobSkillRequirement(tenant_id=job.tenant_id,job_id=job_id, skill_id=r["skill_id"],
                    min_skill_level=r["min_skill_level"], employees_required=r["employees_required"]))
        else:
            setattr(job, field, value)

    # When the job is edited, restore dates to originals and clear tracking.
    # This makes the job a true fresh scheduling candidate:
    #   - start_date / end_date go back to user's original request
    #   - original_start_date / original_end_date cleared so scheduler
    #     treats this as a brand-new job on the next run
    # Only restore if originals exist (i.e. scheduler had moved the dates)
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
    job = db.query(Job).filter(
        Job.id == job_id,
        Job.tenant_id == current_user.tenant_id,
    ).first()
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
