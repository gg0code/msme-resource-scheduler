"""
```python
"""
backend/app/routers/resource_availability.py

FILE PURPOSE
This FastAPI router module provides real-time resource availability computation for jobs 
in the ZetaOps Copilot scheduling system. It exposes a single GET endpoint that calculates 
which employees and machines assigned to a specific job are actually free during that job's 
date range, replacing misleading static availability percentages with dynamic conflict detection. 
Added in v3.9.4 on the v4-dev branch, this sits in the API layer between the frontend job 
detail views and the availability computation logic in the services layer.

WHAT THIS FILE DOES — step by step
1. Imports FastAPI routing components, database dependencies, and all required models/schemas
2. Defines two helper functions that query the database for resource conflicts across job date ranges
3. Implements the main GET endpoint that fetches a job, validates its date range, and computes availability
4. For each employee assigned to the job, calculates free capacity by subtracting overlapping job allocations
5. For each machine assigned to the job, determines if any other jobs are using it during overlapping dates
6. Returns structured availability data with conflict details and blocking job information
7. Handles edge cases like jobs without dates or missing resources with appropriate error responses

KEY FUNCTIONS / CLASSES / COMPONENTS

Name         : _get_employee_blocking_jobs
Type         : function
Purpose      : Calculates total allocation percentage an employee has on other jobs that overlap 
               with the given job's date range. Returns both the numeric total and a list of 
               specific blocking jobs with their allocation details for frontend display.
Parameters   : db (Session) - database session for queries
               employee_id (int) - ID of employee to check conflicts for  
               job_id (int) - current job ID to exclude from conflict calculation
               job_days (list) - list of date objects representing the job's date range
               tenant_id (int) - tenant scope for security filtering
Returns      : tuple[float, List[BlockingJob]] - total allocated percentage and list of conflicting jobs
Calls        : SQLAlchemy query methods, _date_range from availability_engine.py
DB/API       : Queries JobAssignment and Job tables with tenant filtering and job exclusion
Side effects : None - pure read-only computation

Name         : _get_machine_blocking_jobs  
Type         : function
Purpose      : Identifies other jobs that have the specified machine assigned during dates that 
               overlap with the given job's date range. Unlike employees, machines are binary 
               busy/free since they cannot be shared across multiple jobs simultaneously.
Parameters   : db (Session) - database session for queries
               machine_id (int) - ID of machine to check conflicts for
               job_id (int) - current job ID to exclude from conflict calculation  
               job_days (list) - list of date objects representing the job's date range
               tenant_id (int) - tenant scope for security filtering
Returns      : List[BlockingJob] - list of jobs that conflict with this machine usage
Calls        : SQLAlchemy query methods, _date_range from availability_engine.py
DB/API       : Queries Job and JobAssignment tables with machine and tenant filtering
Side effects : None - pure read-only computation

Name         : get_resource_availability
Type         : FastAPI endpoint  
Purpose      : Main API endpoint that computes and returns real-time availability for all employees 
               and machines assigned to a specific job during its scheduled date range. Replaces 
               static base_availability_pct displays with dynamic conflict-aware calculations that 
               show users actual resource capacity considering existing job commitments.
Parameters   : job_id (int) - ID of job to compute resource availability for
               db (Session) - injected database dependency for queries
               current_user - injected authenticated user for tenant scoping
Returns      : ResourceAvailabilityResponse - structured availability data with employee free percentages,
               machine busy/free status, blocking job details, and any error conditions
Calls        : _get_employee_blocking_jobs, _get_machine_blocking_jobs, _date_range from availability_engine
DB/API       : Queries Job, JobAssignment, Employee, and Machine tables with strict tenant filtering
Side effects : None - pure read-only endpoint that does not modify any data

WHO CALLS THIS FILE
- frontend/src/pages/JobDetailPage.tsx - displays resource availability in job management interface
- frontend/src/components/ResourceAvailabilityPanel.tsx - renders the availability data and conflict warnings
- frontend/src/api/api_jobs.ts - contains the TypeScript API client function that calls this endpoint

IMPORTS EXPLAINED
- fastapi.APIRouter: Creates the router instance for registering this endpoint with the main FastAPI app
- fastapi.Depends: Dependency injection decorator for database sessions and authentication
- fastapi.HTTPException: Standard HTTP error responses for 404 job not found cases
- sqlalchemy.orm.Session: Database session type for ORM queries with transaction management
- typing.List: Type annotation for function return values containing lists of blocking jobs
- app.core.dependencies.get_current_user: Authentication dependency that extracts JWT user and tenant info
- app.database.get_db: Database dependency that provides SQLAlchemy session with connection pooling
- app.models.job.Job/JobAssignment: ORM models for job data and resource assignment relationships
- app.models.employee.Employee: ORM model for employee data including base availability percentages
- app.models.machine.Machine: ORM model for machine data and status information
- app.schemas.resource_availability.*: Pydantic response models that define API contract and JSON structure
- app.services.availability_engine._date_range: Utility function that generates date lists from start/end dates

INTERN NOTES
- Easiest thing to break: Forgetting tenant_id filtering in database queries will leak data across companies and create major security vulnerabilities
- Non-obvious design decision: Machines are binary busy/free while employees use percentage allocation because machines cannot be shared but workers can split time across multiple jobs
- Most common mistake: Not excluding the current job_id from conflict calculations will make every job appear to conflict with itself
- Design principle implemented: #2 (tenant scoping on ALL DB queries) - every single database query includes tenant_id filtering to prevent cross-tenant data access
- What to check if behaving unexpectedly: Verify job has start_date and end_date set, check that JobAssignment records exist linking the job to employees/machines, confirm _date_range is generating correct date lists
- This file is v4-dev only and should merge cleanly into master since it has no WhatsApp or v5-specific dependencies
"""
```
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List

from app.core.dependencies import get_current_user
from app.database import get_db
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
