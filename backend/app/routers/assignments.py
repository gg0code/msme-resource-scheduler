"""
routers/assignments.py — V3.7.1
Added: JWT auth, tenant_id scoping on all endpoints + passed to availability engine
  POST /api/assignments/                        — scheduler+
  GET  /api/assignments/check/{job_id}          — any authenticated user
  GET  /api/assignments/employee/{employee_id}  — any authenticated user
  GET  /api/assignments/machine/{machine_id}    — any authenticated user

V3.7.1 — Pain Point 4 + 1 fix:
  - Overbooking check: before saving, query existing assignments for each machine
    in the same date window. If a clash is found, return a warm conflict message
    that names the clashing job specifically.
  - Machine clash message now says which job is clashing, not just "conflict".
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session, selectinload
from pydantic import BaseModel
from typing import List
from datetime import date

from app.database import get_db
from app.core.dependencies import get_current_user, require_role
from app.models.auth import User
from app.services.assignment_service import assign_resources, AssignmentError
from app.services.availability_engine import (
    check_availability, _date_range, _effective_availability,
    _is_employee_busy, _is_machine_busy,
)
from app.models.job import JobAssignment, Job, JobSkillRequirement
from app.models.employee import Employee
from app.models.machine import Machine
from app.models.availability import AvailabilityOverride

router = APIRouter()


class AssignRequest(BaseModel):
    job_id: int
    employee_ids: List[int] = []
    machine_ids: List[int] = []


# ── V3.7.1 — Overbooking check helper ────────────────────────────────────────

def _check_machine_overbooking(
    db: Session,
    job_id: int,
    machine_ids: List[int],
    tenant_id: int,
) -> list[dict]:
    """
    For each machine_id being assigned, check if it is already assigned
    to a different job with overlapping dates.

    Returns a list of conflict dicts:
      { "machine_name": str, "clashing_job_name": str,
        "clashing_start": str, "clashing_end": str }

    Returns empty list if no conflicts.
    """
    if not machine_ids:
        return []

    # Get the job being assigned — need its date range
    job = db.query(Job).filter(
        Job.id == job_id,
        Job.tenant_id == tenant_id,
    ).first()

    if not job or not job.start_date or not job.end_date:
        return []  # no dates set yet — skip check

    # Always call .date() on datetime columns per architecture rules
    new_start = job.start_date.date() if hasattr(job.start_date, 'date') else job.start_date
    new_end   = job.end_date.date()   if hasattr(job.end_date,   'date') else job.end_date

    conflicts = []

    for machine_id in machine_ids:
        # Find any existing assignment for this machine that overlaps the date range
        # Overlap condition: existing.start <= new_end AND existing.end >= new_start
        clashing = (
            db.query(JobAssignment)
            .join(Job, JobAssignment.job_id == Job.id)
            .filter(
                JobAssignment.machine_id == machine_id,
                JobAssignment.tenant_id  == tenant_id,
                JobAssignment.job_id     != job_id,          # exclude the job being assigned
                Job.start_date           <= new_end,
                Job.end_date             >= new_start,
                Job.status.notin_(["Completed", "Cancelled"]),  # ignore closed jobs
            )
            .options(selectinload(JobAssignment.job))
            .first()
        )

        if clashing and clashing.job:
            machine = db.query(Machine).filter(
                Machine.id        == machine_id,
                Machine.tenant_id == tenant_id,
            ).first()

            machine_name = machine.name if machine else f"Machine #{machine_id}"

            # .date() on clashing job dates per architecture rules
            c_start = clashing.job.start_date.date() if hasattr(clashing.job.start_date, 'date') else clashing.job.start_date
            c_end   = clashing.job.end_date.date()   if hasattr(clashing.job.end_date,   'date') else clashing.job.end_date

            conflicts.append({
                "machine_name":      machine_name,
                "clashing_job_name": clashing.job.name,
                "clashing_start":    str(c_start),
                "clashing_end":      str(c_end),
            })

    return conflicts


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post("/", status_code=status.HTTP_201_CREATED)
def create_assignment(
    payload: AssignRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("proprietor", "scheduler")),
):
    # V3.7.1 — Check for machine overbooking before saving
    clashes = _check_machine_overbooking(
        db=db,
        job_id=payload.job_id,
        machine_ids=payload.machine_ids,
        tenant_id=current_user.tenant_id,
    )

    if clashes:
        # Build a clear, specific message naming each clashing job
        messages = []
        for c in clashes:
            messages.append(
                f"{c['machine_name']} is already assigned to "
                f"'{c['clashing_job_name']}' "
                f"({c['clashing_start']} to {c['clashing_end']})"
            )
        detail = "Machine overbooking detected. " + " | ".join(messages)
        raise HTTPException(status_code=409, detail=detail)

    try:
        result = assign_resources(
            db=db,
            job_id=payload.job_id,
            employee_ids=payload.employee_ids,
            machine_ids=payload.machine_ids,
            tenant_id=current_user.tenant_id,
        )
        return {"message": "Resources assigned successfully", "assignments": result}
    except AssignmentError as e:
        raise HTTPException(status_code=409, detail=str(e))


@router.get("/check/{job_id}")
def check_job_availability(
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

    try:
        result = check_availability(db, job_id, tenant_id=current_user.tenant_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    days = _date_range(job.start_date, job.end_date)
    tid = current_user.tenant_id

    # --- Machines scoped to tenant ---
    all_machines = db.query(Machine).filter(
        Machine.tenant_id == tid,
        Machine.status == "Operational",
    ).all()
    machines_info = []
    for m in all_machines:
        overrides = db.query(AvailabilityOverride).filter(AvailabilityOverride.machine_id == m.id).all()
        blocked = any(_effective_availability(m.base_availability_pct, overrides, d) <= 0 for d in days)
        busy = _is_machine_busy(db, m.id, job_id, days, tenant_id=tid)
        busy_reason = None
        if blocked:
            busy_reason = "On maintenance / override"
        elif busy:
            clashing = (
                db.query(JobAssignment)
                .join(Job, JobAssignment.job_id == Job.id)
                .filter(
                    JobAssignment.machine_id == m.id,
                    JobAssignment.tenant_id  == tid,
                    JobAssignment.job_id     != job_id,
                    Job.start_date           <= max(days),
                    Job.end_date             >= min(days),
                    Job.status.notin_(["Completed", "Cancelled"]),
                )
                .options(selectinload(JobAssignment.job))
                .first()
            )
            if clashing and clashing.job:
                c_start = clashing.job.start_date.date() if hasattr(clashing.job.start_date, 'date') else clashing.job.start_date
                c_end   = clashing.job.end_date.date()   if hasattr(clashing.job.end_date,   'date') else clashing.job.end_date
                busy_reason = f"Assigned to '{clashing.job.name}' ({c_start} to {c_end})"
            else:
                busy_reason = "Assigned to another job"

        machines_info.append({
            "id": m.id,
            "name": m.name,
            "machine_type": m.machine_type,
            "location_bay": m.location_bay,
            "hourly_rate": m.hourly_rate,
            "available": not blocked and not busy,
            "busy_reason": busy_reason,
            "skill_requirements": [
                {
                    "skill_id": sr.skill_id,
                    "skill_name": sr.skill.name if sr.skill else f"skill#{sr.skill_id}",
                    "min_skill_level": sr.min_skill_level,
                    "employees_required": sr.employees_required,
                }
                for sr in m.skill_requirements
            ],
        })

    # --- Employees scoped to tenant ---
    all_employees = db.query(Employee).filter(
        Employee.tenant_id == tid,
        Employee.status == "Active",
    ).all()
    employees_info = []
    for emp in all_employees:
        overrides = db.query(AvailabilityOverride).filter(AvailabilityOverride.employee_id == emp.id).all()
        blocked = any(_effective_availability(emp.base_availability_pct, overrides, d) <= 0 for d in days)
        busy = _is_employee_busy(db, emp.id, job_id, days, tenant_id=tid)
        employees_info.append({
            "id": emp.id,
            "full_name": emp.full_name,
            "department": emp.department,
            "employment_type": emp.employment_type,
            "hourly_rate": emp.hourly_rate,
            "available": not blocked and not busy,
            "busy_reason": "Unavailable/on leave" if blocked else ("Assigned to another job" if busy else None),
            "skills": [
                {
                    "skill_id": es.skill_id,
                    "skill_name": es.skill.name if es.skill else f"skill#{es.skill_id}",
                    "skill_level": es.skill_level,
                }
                for es in emp.skills
            ],
        })

    # --- Skill requirements ---
    skill_reqs = db.query(JobSkillRequirement).filter(
        JobSkillRequirement.job_id == job_id,
    ).all()
    skill_reqs_info = []
    for req in skill_reqs:
        avail_ids = result.available_employees.get(req.id, [])
        skill_reqs_info.append({
            "id": req.id,
            "skill_id": req.skill_id,
            "skill_name": req.skill.name if req.skill else f"skill#{req.skill_id}",
            "min_skill_level": req.min_skill_level,
            "employees_required": req.employees_required,
            "available_employee_ids": avail_ids,
        })

    # --- Currently assigned ---
    current = db.query(JobAssignment).filter(
        JobAssignment.job_id == job_id,
        JobAssignment.tenant_id == tid,
    ).all()
    current_emp_ids = [a.employee_id for a in current if a.employee_id]
    current_machine_ids = [a.machine_id for a in current if a.machine_id]

    return {
        "job_id": job_id,
        "feasible": result.feasible,
        "feasibility_score": result.feasibility_score,
        "conflicts": [
            {"resource_type": c.resource_type, "resource_name": c.resource_name, "reason": c.reason}
            for c in result.conflicts
        ],
        "skill_requirements": skill_reqs_info,
        "machines": machines_info,
        "employees": employees_info,
        "currently_assigned_employee_ids": current_emp_ids,
        "currently_assigned_machine_ids": current_machine_ids,
    }


@router.get("/employee/{employee_id}")
def get_employee_assignments(
    employee_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    emp = db.query(Employee).filter(
        Employee.id == employee_id,
        Employee.tenant_id == current_user.tenant_id,
    ).first()
    if not emp:
        raise HTTPException(status_code=404, detail="Employee not found")

    rows = (
        db.query(JobAssignment)
        .options(selectinload(JobAssignment.job))
        .filter(
            JobAssignment.employee_id == employee_id,
            JobAssignment.tenant_id == current_user.tenant_id,
        )
        .join(Job, JobAssignment.job_id == Job.id)
        .order_by(Job.start_date)
        .all()
    )
    return [
        {
            "assignment_id": r.id,
            "job_id": r.job.id,
            "job_name": r.job.name,
            "customer": r.job.customer,
            "start_date": str(r.job.start_date),
            "end_date": str(r.job.end_date),
            "status": r.job.status,
            "priority": r.job.priority,
            "assigned_at": r.assigned_at.isoformat() if r.assigned_at else None,
        }
        for r in rows
    ]


@router.get("/machine/{machine_id}")
def get_machine_assignments(
    machine_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    machine = db.query(Machine).filter(
        Machine.id == machine_id,
        Machine.tenant_id == current_user.tenant_id,
    ).first()
    if not machine:
        raise HTTPException(status_code=404, detail="Machine not found")

    rows = (
        db.query(JobAssignment)
        .options(selectinload(JobAssignment.job))
        .filter(
            JobAssignment.machine_id == machine_id,
            JobAssignment.tenant_id == current_user.tenant_id,
        )
        .join(Job, JobAssignment.job_id == Job.id)
        .order_by(Job.start_date)
        .all()
    )
    return [
        {
            "assignment_id": r.id,
            "job_id": r.job.id,
            "job_name": r.job.name,
            "customer": r.job.customer,
            "start_date": str(r.job.start_date),
            "end_date": str(r.job.end_date),
            "status": r.job.status,
            "priority": r.job.priority,
            "assigned_at": r.assigned_at.isoformat() if r.assigned_at else None,
        }
        for r in rows
    ]
