# app/routers/assignments.py - Version 1.2
# Branch: both
#
# FILE PURPOSE
# Handles all job resource assignment operations.
# Layer: router
#
# WHAT THIS FILE DOES
# 1. POST /        - assign employees and machines to a job
# 2. GET  /check/{job_id}     - full availability check with conflict details
# 3. GET  /employee/{id}      - list all assignments for an employee
# 4. GET  /machine/{id}       - list all assignments for a machine
# 5. DELETE /{id}             - remove a single assignment row (v1.2)
# 6. PATCH /{job_id}/allocation - bulk update allocation_pct on assignments (v1.2)
#
# WHO CALLS THIS FILE
# - app/main.py - registered at prefix /api/assignments
# - frontend Employees.tsx, Machines.tsx - DELETE /{id}
# - frontend Jobs.tsx - PATCH /{job_id}/allocation
#
# INTERN NOTES
# - Every query filters by tenant_id - never cross-tenant
# - DELETE checks tenant ownership before deleting
# - allocation_pct added to JobAssignment in migration 020

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import List, Optional

from app.database import get_db
from app.core.dependencies import get_current_user, require_operational
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


# -- Schemas ------------------------------------------------------------------

class AssignRequest(BaseModel):
    job_id: int
    employee_ids: List[int] = []
    machine_ids: List[int] = []


class AllocationItem(BaseModel):
    type: str            # "employee" or "machine"
    resource_id: int
    allocation_pct: float


class AllocationPatchRequest(BaseModel):
    allocations: List[AllocationItem]


# -- POST / -------------------------------------------------------------------

@router.post("/", status_code=status.HTTP_201_CREATED)
def create_assignment(
    payload: AssignRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_operational()),
):
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


# -- DELETE /{id} -------------------------------------------------------------

@router.delete("/{assignment_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_assignment(
    assignment_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_operational()),
):
    """
    Remove a single assignment row.
    Verifies tenant ownership before deletion - never cross-tenant.
    """
    assignment = db.query(JobAssignment).filter(
        JobAssignment.id == assignment_id,
        JobAssignment.tenant_id == current_user.tenant_id,
    ).first()
    if not assignment:
        raise HTTPException(status_code=404, detail="Assignment not found")

    db.delete(assignment)
    db.commit()


# -- PATCH /{job_id}/allocation -----------------------------------------------

@router.patch("/{job_id}/allocation")
def update_allocation(
    job_id: int,
    payload: AllocationPatchRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_operational()),
):
    """
    Bulk update allocation_pct for all assignments on a job.

    Frontend sends:
      { allocations: [{ type: "employee"|"machine", resource_id, allocation_pct }] }

    Finds the matching JobAssignment row for each item and updates allocation_pct.
    Only updates rows belonging to this tenant.
    Returns count of rows updated.
    """
    tid = current_user.tenant_id

    # Verify job belongs to tenant
    job = db.query(Job).filter(
        Job.id == job_id,
        Job.tenant_id == tid,
    ).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    updated = 0
    for item in payload.allocations:
        if item.type == "employee":
            row = db.query(JobAssignment).filter(
                JobAssignment.job_id == job_id,
                JobAssignment.employee_id == item.resource_id,
                JobAssignment.tenant_id == tid,
            ).first()
        elif item.type == "machine":
            row = db.query(JobAssignment).filter(
                JobAssignment.job_id == job_id,
                JobAssignment.machine_id == item.resource_id,
                JobAssignment.tenant_id == tid,
            ).first()
        else:
            continue

        if row:
            row.allocation_pct = max(0.0, min(100.0, item.allocation_pct))
            updated += 1

    db.commit()
    return {"updated": updated}


# -- GET /check/{job_id} ------------------------------------------------------

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

    all_machines = db.query(Machine).filter(
        Machine.tenant_id == tid,
        Machine.status == "Operational",
    ).all()
    machines_info = []
    for m in all_machines:
        overrides = db.query(AvailabilityOverride).filter(AvailabilityOverride.machine_id == m.id).all()
        blocked = any(_effective_availability(m.base_availability_pct, overrides, d) <= 0 for d in days)
        busy = _is_machine_busy(db, m.id, job_id, days, tenant_id=tid)
        machines_info.append({
            "id": m.id,
            "name": m.name,
            "machine_type": m.machine_type,
            "location_bay": m.location_bay,
            "hourly_rate": m.hourly_rate,
            "available": not blocked and not busy,
            "busy_reason": "On maintenance/override" if blocked else ("Assigned to another job" if busy else None),
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


# -- GET /employee/{employee_id} ----------------------------------------------

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
            "allocation_pct": r.allocation_pct,
            "assigned_at": r.assigned_at.isoformat() if r.assigned_at else None,
        }
        for r in rows
    ]


# -- GET /machine/{machine_id} ------------------------------------------------

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
            "allocation_pct": r.allocation_pct,
            "assigned_at": r.assigned_at.isoformat() if r.assigned_at else None,
        }
        for r in rows
    ]
