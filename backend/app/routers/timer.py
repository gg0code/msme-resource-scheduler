from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime, timezone

from app.database import get_db
from app.core.dependencies import get_current_user, require_role
from app.models.auth import User
from app.models.job import Job, JobAssignment
from app.models.employee import Employee
from app.models.machine import Machine
from app.services.cost_service import (
    compute_tentative_cost,
    compute_actual_cost,
    compute_cost_preview,
)
from app.services.availability_engine import check_availability

router = APIRouter()


# -- Schemas -------------------------------------------------------------------

class EndJobPayload(BaseModel):
    """Payload for POST /end — user can update resources before finalising."""
    employee_ids: List[int] = []
    machine_ids: List[int] = []

class OutagePayload(BaseModel):
    action: str          # "start" | "end"
    reason: Optional[str] = None


# -- Helpers -------------------------------------------------------------------

def _get_job_or_404(db: Session, job_id: int, tenant_id: int) -> Job:
    job = db.query(Job).filter(
        Job.id == job_id,
        Job.tenant_id == tenant_id,
    ).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


def _log_event(job: Job, event: str, now: datetime) -> list:
    log = list(job.timer_log or [])
    log.append({"event": event, "timestamp": now.isoformat()})
    return log


def _release_resources(db: Session, job: Job) -> None:
    """
    Releasing resources = clearing all JobAssignment rows for this job.
    This makes employees/machines available for other jobs immediately.
    """
    db.query(JobAssignment).filter(
        JobAssignment.job_id == job.id,
        JobAssignment.tenant_id == job.tenant_id,
    ).delete()


def _sync_assignments(
    db: Session,
    job: Job,
    employee_ids: List[int],
    machine_ids: List[int],
) -> None:
    """Replace all assignments with the given employee + machine lists."""
    _release_resources(db, job)
    for eid in set(employee_ids):
        db.add(JobAssignment(
            job_id=job.id,
            tenant_id=job.tenant_id,
            employee_id=eid,
            machine_id=None,
        ))
    for mid in set(machine_ids):
        db.add(JobAssignment(
            job_id=job.id,
            tenant_id=job.tenant_id,
            employee_id=None,
            machine_id=mid,
        ))


def _actual_hours(job: Job, now: Optional[datetime] = None) -> float:
    """Compute net actual hours up to now (or actual_end_at if already ended)."""
    start = job.actual_start_at
    end = job.actual_end_at or now
    if not start or not end:
        return 0.0
    total_seconds = (end - start).total_seconds()
    net_seconds = max(0.0, total_seconds - (job.paused_seconds or 0))
    return net_seconds / 3600.0


def _job_summary(db: Session, job: Job) -> dict:
    """Build full job dict with cost breakdowns for API responses."""
    tentative = compute_tentative_cost(db, job)
    actual = compute_actual_cost(db, job)

    assignments = db.query(JobAssignment).filter(
        JobAssignment.job_id == job.id,
        JobAssignment.tenant_id == job.tenant_id,
    ).all()

    employees = []
    machines = []
    for a in assignments:
        if a.employee_id:
            emp = db.query(Employee).filter(Employee.id == a.employee_id).first()
            if emp:
                employees.append({"id": emp.id, "full_name": emp.full_name, "hourly_rate": emp.hourly_rate})
        if a.machine_id:
            mac = db.query(Machine).filter(Machine.id == a.machine_id).first()
            if mac:
                machines.append({"id": mac.id, "name": mac.name, "hourly_rate": mac.hourly_rate})

    # Conflict check
    has_conflict = False
    conflict_reasons = []
    try:
        avail = check_availability(db, job.id, job.tenant_id)
        has_conflict = not avail.feasible
        conflict_reasons = [c.reason for c in avail.conflicts]
    except Exception:
        pass

    return {
        "id": job.id,
        "name": job.name,
        "status": job.status,
        "timer_status": job.timer_status,
        "priority": job.priority,
        "start_date": str(job.start_date) if job.start_date else None,
        "end_date": str(job.end_date) if job.end_date else None,
        "actual_start_at": job.actual_start_at.isoformat() if job.actual_start_at else None,
        "actual_end_at": job.actual_end_at.isoformat() if job.actual_end_at else None,
        "paused_seconds": job.paused_seconds or 0,
        "timer_log": job.timer_log or [],
        "has_conflict": has_conflict,
        "conflict_reasons": conflict_reasons,
        "assigned_employees": employees,
        "assigned_machines": machines,
        "tentative_cost": tentative,
        "actual_cost": actual,
    }


# -- Routes --------------------------------------------------------------------

@router.post("/{job_id}/start")
def start_job(
    job_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("proprietor", "scheduler")),
):
    """
    Start a job. Only allowed if:
    - timer_status is 'idle'
    - job has NO active conflicts
    """
    job = _get_job_or_404(db, job_id, current_user.tenant_id)

    if job.timer_status != "idle":
        raise HTTPException(
            status_code=400,
            detail=f"Cannot start: timer is already '{job.timer_status}'",
        )

    # Block start if conflicts exist
    try:
        avail = check_availability(db, job.id, current_user.tenant_id)
        if not avail.feasible:
            reasons = "; ".join(c.reason for c in avail.conflicts)
            raise HTTPException(
                status_code=409,
                detail=f"Cannot start: unresolved conflicts — {reasons}",
            )
    except HTTPException:
        raise
    except Exception:
        pass  # If engine fails, allow start

    now = datetime.now(timezone.utc)
    job.actual_start_at = now
    job.timer_status = "running"
    job.status = "In Progress"
    job.timer_log = _log_event(job, "start", now)

    db.commit()
    db.refresh(job)
    return _job_summary(db, job)


@router.post("/{job_id}/pause")
def pause_job(
    job_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("proprietor", "scheduler")),
):
    job = _get_job_or_404(db, job_id, current_user.tenant_id)

    if job.timer_status != "running":
        raise HTTPException(status_code=400, detail="Job is not running")

    now = datetime.now(timezone.utc)
    job.timer_status = "paused"
    job.timer_log = _log_event(job, "pause", now)

    db.commit()
    db.refresh(job)
    return _job_summary(db, job)


@router.post("/{job_id}/resume")
def resume_job(
    job_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("proprietor", "scheduler")),
):
    job = _get_job_or_404(db, job_id, current_user.tenant_id)

    if job.timer_status != "paused":
        raise HTTPException(status_code=400, detail="Job is not paused")

    now = datetime.now(timezone.utc)

    # Accumulate paused duration
    log = list(job.timer_log or [])
    pause_event = next((e for e in reversed(log) if e["event"] == "pause"), None)
    if pause_event:
        paused_dur = (now - datetime.fromisoformat(pause_event["timestamp"])).total_seconds()
        job.paused_seconds = (job.paused_seconds or 0) + int(paused_dur)

    job.timer_status = "running"
    log.append({"event": "resume", "timestamp": now.isoformat()})
    job.timer_log = log

    db.commit()
    db.refresh(job)
    return _job_summary(db, job)


@router.post("/{job_id}/stop")
def stop_job(
    job_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("proprietor", "scheduler")),
):
    """
    Stop job early (black cross button).
    Sets status = 'Stopped', releases all resources.
    """
    job = _get_job_or_404(db, job_id, current_user.tenant_id)

    if job.timer_status not in ("running", "paused", "idle"):
        raise HTTPException(status_code=400, detail="Job cannot be stopped in its current state")

    now = datetime.now(timezone.utc)

    # If paused, accumulate final pause duration
    if job.timer_status == "paused":
        log = list(job.timer_log or [])
        pause_event = next((e for e in reversed(log) if e["event"] == "pause"), None)
        if pause_event:
            paused_dur = (now - datetime.fromisoformat(pause_event["timestamp"])).total_seconds()
            job.paused_seconds = (job.paused_seconds or 0) + int(paused_dur)

    job.actual_end_at = now
    job.timer_status = "ended"
    job.status = "Stopped"
    job.actual_hours = round(_actual_hours(job, now), 2)
    job.timer_log = _log_event(job, "stop", now)

    _release_resources(db, job)
    db.commit()
    db.refresh(job)
    return _job_summary(db, job)


@router.get("/{job_id}/summary")
def get_job_summary(
    job_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Used by End Job modal to show current cost preview.
    Returns current actual hours elapsed + cost breakdown.
    """
    job = _get_job_or_404(db, job_id, current_user.tenant_id)

    now = datetime.now(timezone.utc)
    hours = _actual_hours(job, now)

    # Current assignments
    assignments = db.query(JobAssignment).filter(
        JobAssignment.job_id == job.id,
        JobAssignment.tenant_id == job.tenant_id,
    ).all()
    employee_ids = [a.employee_id for a in assignments if a.employee_id]
    machine_ids = [a.machine_id for a in assignments if a.machine_id]

    # Available employees and machines for the modal dropdowns
    all_employees = db.query(Employee).filter(
        Employee.tenant_id == current_user.tenant_id,
        Employee.status == "Active",
    ).order_by(Employee.full_name).all()

    all_machines = db.query(Machine).filter(
        Machine.tenant_id == current_user.tenant_id,
        Machine.status == "Operational",
    ).order_by(Machine.name).all()

    preview = compute_cost_preview(db, job, employee_ids, machine_ids, hours)

    return {
        "job_id": job.id,
        "job_name": job.name,
        "actual_hours": round(hours, 2),
        "current_employee_ids": employee_ids,
        "current_machine_ids": machine_ids,
        "cost_preview": preview,
        "available_employees": [
            {"id": e.id, "full_name": e.full_name, "hourly_rate": e.hourly_rate or 0.0}
            for e in all_employees
        ],
        "available_machines": [
            {"id": m.id, "name": m.name, "hourly_rate": m.hourly_rate or 0.0}
            for m in all_machines
        ],
    }


@router.post("/{job_id}/end")
def end_job(
    job_id: int,
    payload: EndJobPayload,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("proprietor", "scheduler")),
):
    """
    End job correctly (blue dot).
    - Updates assignments to final employee/machine list
    - Sets actual_end_at
    - Computes and stores final cost
    - Releases all resources
    - Sets status = 'Completed'
    """
    job = _get_job_or_404(db, job_id, current_user.tenant_id)

    if job.timer_status not in ("running", "paused"):
        raise HTTPException(
            status_code=400,
            detail="Job must be running or paused to end it",
        )

    now = datetime.now(timezone.utc)

    # Accumulate final pause if paused
    if job.timer_status == "paused":
        log = list(job.timer_log or [])
        pause_event = next((e for e in reversed(log) if e["event"] == "pause"), None)
        if pause_event:
            paused_dur = (now - datetime.fromisoformat(pause_event["timestamp"])).total_seconds()
            job.paused_seconds = (job.paused_seconds or 0) + int(paused_dur)

    job.actual_end_at = now
    job.timer_status = "ended"
    job.status = "Completed"
    job.actual_hours = round(_actual_hours(job, now), 2)
    job.timer_log = _log_event(job, "end", now)

    # Update assignments to final resource list from modal
    _sync_assignments(db, job, payload.employee_ids, payload.machine_ids)

    db.commit()
    db.refresh(job)

    # Compute final costs AFTER syncing assignments
    actual = compute_actual_cost(db, job)
    tentative = compute_tentative_cost(db, job)

    return {
        **_job_summary(db, job),
        "final_actual_cost": actual,
        "final_tentative_cost": tentative,
    }


@router.post("/{job_id}/outage")
def log_outage(
    job_id: int,
    payload: OutagePayload,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("proprietor", "scheduler")),
):
    """
    Log a power outage / interruption event.
    action=start → records outage_start in timer_log, pauses the timer if running.
    action=end   → records outage_end, accumulates outage duration in paused_seconds, resumes.
    """
    job = _get_job_or_404(db, job_id, current_user.tenant_id)
    if job.timer_status not in ("running", "paused"):
        raise HTTPException(status_code=400, detail="Job must be running or paused to log outage")

    now = datetime.now(timezone.utc)
    log = list(job.timer_log or [])

    if payload.action == "start":
        log.append({"event": "outage_start", "timestamp": now.isoformat(), "reason": payload.reason or "Power outage"})
        job.timer_status = "paused"   # treat outage as pause
        job.timer_log = log

    elif payload.action == "end":
        # Find the most recent outage_start
        outage_start_event = next((e for e in reversed(log) if e["event"] == "outage_start"), None)
        if outage_start_event:
            outage_dur = (now - datetime.fromisoformat(outage_start_event["timestamp"])).total_seconds()
            job.paused_seconds = (job.paused_seconds or 0) + int(outage_dur)
        log.append({"event": "outage_end", "timestamp": now.isoformat(), "reason": payload.reason or "Power restored"})
        job.timer_status = "running"
        job.timer_log = log
    else:
        raise HTTPException(status_code=400, detail="action must be 'start' or 'end'")

    db.commit()
    db.refresh(job)
    return _job_summary(db, job)
