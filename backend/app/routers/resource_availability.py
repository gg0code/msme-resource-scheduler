"""
resource_availability.py  (backend/app/routers/)
Defines the GET /api/jobs/{job_id}/resource-availability endpoint.
Returns computed real-time free capacity for every employee and machine assigned to a job,
scoped to the job's specific date range. Replaces the static base_availability_pct display
that was misleading users into thinking resources were free when they were already committed.

Depends on:
  app/schemas/resource_availability.py  — response shape
  app/models/job.py                     — Job, JobAssignment
  app/models/employee.py                — Employee
  app/models/machine.py                 — Machine
  app/services/availability_engine.py  — _date_range, _is_employee_busy, _is_machine_busy
  app/core/dependencies.py             — get_current_user, get_db

Added in v3.9.4.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List

from app.core.dependencies import get_current_user, get_db
from app.models.job import Job, JobAssignment
from app.models.employee import Employee
from app.models.machine import Machine
from app.schemas.resource_availability import (
    ResourceAvailabilityResponse,
    EmployeeAvailability,
    MachineAvailability,
    BlockingJob,
    DateRange,
)
from app.services.availability_engine import _date_range

router = APIRouter()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_employee_blocking_jobs(
    db: Session,
    employee_id: int,
    job_id: int,
    job_days: list,
    tenant_id: int,
) -> tuple[float, List[BlockingJob]]:
    """
    Calculates the total allocation percentage this employee has on other jobs
    that overlap the given job_days, and returns the list of those blocking jobs.

    Returns a tuple of (total_allocated_pct, list_of_BlockingJob).
    Excludes the current job_id so a job does not count as blocking itself.
    Scoped to tenant_id to prevent cross-tenant data leakage.
    """
    other_assignments = (
        db.query(JobAssignment)
        .join(Job, Job.id == JobAssignment.job_id)
        .filter(
            JobAssignment.employee_id == employee_id,
            JobAssignment.job_id != job_id,
            Job.tenant_id == tenant_id,
        )
        .all()
    )

    total_allocated = 0.0
    blocking: List[BlockingJob] = []

    for assignment in other_assignments:
        other_job = db.query(Job).filter(Job.id == assignment.job_id).first()
        if not other_job or not other_job.start_date or not other_job.end_date:
            continue

        other_days = set(_date_range(other_job.start_date, other_job.end_date))
        overlaps = any(d in other_days for d in job_days)
        if not overlaps:
            continue

        alloc = assignment.allocation_pct or 100
        total_allocated += alloc
        blocking.append(BlockingJob(
            job_id=other_job.id,
            job_name=other_job.name or f"Job #{other_job.id}",
            allocation_pct=alloc,
        ))

    return total_allocated, blocking


def _get_machine_blocking_jobs(
    db: Session,
    machine_id: int,
    job_id: int,
    job_days: list,
    tenant_id: int,
) -> List[BlockingJob]:
    """
    Returns a list of other jobs that have this machine assigned on dates
    overlapping the given job_days.

    An empty list means the machine is free. A non-empty list means it is busy.
    Excludes the current job_id. Scoped to tenant_id.
    """
    other_jobs = (
        db.query(Job)
        .join(JobAssignment, JobAssignment.job_id == Job.id)
        .filter(
            JobAssignment.machine_id == machine_id,
            JobAssignment.job_id != job_id,
            Job.tenant_id == tenant_id,
        )
        .all()
    )

    blocking: List[BlockingJob] = []
    for other_job in other_jobs:
        if not other_job.start_date or not other_job.end_date:
            continue
        other_days = set(_date_range(other_job.start_date, other_job.end_date))
        if any(d in other_days for d in job_days):
            blocking.append(BlockingJob(
                job_id=other_job.id,
                job_name=other_job.name or f"Job #{other_job.id}",
                start_date=other_job.start_date,
                end_date=other_job.end_date,
            ))

    return blocking


# ---------------------------------------------------------------------------
# Endpoint
# ---------------------------------------------------------------------------

@router.get("/{job_id}/resource-availability", response_model=ResourceAvailabilityResponse)
def get_resource_availability(
    job_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """
    Returns real-time computed availability for every employee and machine
    assigned to the given job, scoped to the job's specific date range.

    For employees:
      free_pct = base_availability_pct - sum of allocation_pct on overlapping jobs
      status   = 'free' | 'partial' | 'unavailable'

    For machines:
      is_free  = True if no other job uses this machine on overlapping dates
      status   = 'free' | 'busy'

    Returns error='no_dates' if the job has no start_date or end_date set.
    All queries are scoped to current_user.tenant_id to prevent cross-tenant leakage.
    The materials list is always empty in v3.9.4 — populated in v3.9.5.
    """
    tenant_id = current_user.tenant_id

    # Fetch job — tenant scoped
    job = (
        db.query(Job)
        .filter(Job.id == job_id, Job.tenant_id == tenant_id)
        .first()
    )
    if not job:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found")

    # No dates — return early with clear error signal
    if not job.start_date or not job.end_date:
        return ResourceAvailabilityResponse(
            job_id=job_id,
            date_range=None,
            employees=[],
            machines=[],
            materials=[],
            error="no_dates",
        )

    job_days = _date_range(job.start_date, job.end_date)

    # --- Employees assigned to this job ---
    employee_assignments = (
        db.query(JobAssignment)
        .filter(
            JobAssignment.job_id == job_id,
            JobAssignment.employee_id.isnot(None),
        )
        .all()
    )

    employee_results: List[EmployeeAvailability] = []
    for assignment in employee_assignments:
        emp = (
            db.query(Employee)
            .filter(Employee.id == assignment.employee_id, Employee.tenant_id == tenant_id)
            .first()
        )
        if not emp:
            continue

        base_pct = emp.base_availability_pct or 100.0
        allocated_pct, blocking_jobs = _get_employee_blocking_jobs(
            db, emp.id, job_id, job_days, tenant_id
        )
        free_pct = max(0.0, base_pct - allocated_pct)

        if allocated_pct == 0:
            status = "free"
        elif free_pct <= 0:
            status = "unavailable"
        else:
            status = "partial"

        employee_results.append(EmployeeAvailability(
            employee_id=emp.id,
            name=emp.full_name or f"Employee #{emp.id}",
            base_pct=base_pct,
            allocated_pct=allocated_pct,
            free_pct=free_pct,
            status=status,
            blocking_jobs=blocking_jobs,
        ))

    # --- Machines assigned to this job ---
    machine_assignments = (
        db.query(JobAssignment)
        .filter(
            JobAssignment.job_id == job_id,
            JobAssignment.machine_id.isnot(None),
        )
        .all()
    )

    machine_results: List[MachineAvailability] = []
    for assignment in machine_assignments:
        machine = (
            db.query(Machine)
            .filter(Machine.id == assignment.machine_id, Machine.tenant_id == tenant_id)
            .first()
        )
        if not machine:
            continue

        blocking_jobs = _get_machine_blocking_jobs(
            db, machine.id, job_id, job_days, tenant_id
        )
        is_free = len(blocking_jobs) == 0

        machine_results.append(MachineAvailability(
            machine_id=machine.id,
            name=machine.name or f"Machine #{machine.id}",
            is_free=is_free,
            status="free" if is_free else "busy",
            blocking_jobs=blocking_jobs,
        ))

    return ResourceAvailabilityResponse(
        job_id=job_id,
        date_range=DateRange(start=job.start_date, end=job.end_date),
        employees=employee_results,
        machines=machine_results,
        materials=[],   # reserved for v3.9.5
        error=None,
    )
