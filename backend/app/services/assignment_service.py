"""
```python
"""
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
FILE PURPOSE
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

This file handles manual resource assignment for jobs in ZetaOps Copilot. It validates
that employees and machines are available and not already assigned to other jobs during
the requested time period, then creates JobAssignment records to link resources to jobs.
This is a core business logic layer introduced in v1.0 and updated to v1.1 with tenant
scoping for multi-tenant security. It sits between the API router layer and the database,
providing controlled access to resource assignment operations.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
WHAT THIS FILE DOES — step by step
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

1. Imports required models (Job, JobAssignment, Employee, Machine) and availability functions
2. Defines AssignmentError custom exception for validation failures
3. Retrieves target job from database with tenant scoping
4. Calculates date range from job start_date to end_date
5. Validates each requested employee exists, is Active, has availability, and isn't busy
6. Validates each requested machine exists, is Operational, has availability, and isn't busy
7. Deletes existing JobAssignment records for the job (tenant-scoped)
8. Creates new JobAssignment records for employees and machines
9. Updates job status from "Pending Assignment" to "Scheduled" if applicable
10. Commits transaction and returns list of created assignments

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
KEY FUNCTIONS / CLASSES / COMPONENTS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Name         : AssignmentError
Type         : Exception class
Purpose      : Custom exception raised when resource assignment validation fails. Used to
               provide clear error messages about why an assignment cannot be completed,
               such as employee unavailability or conflicting schedules.
Parameters   : message (str) - descriptive error message
Returns      : N/A (exception class)
Calls        : Inherits from built-in Exception
DB/API       : None
Side effects : None when defined, raises exception when instantiated

Name         : assign_resources
Type         : Function
Purpose      : Main function that assigns employees and machines to a job after validating
               availability and conflicts. This is the primary entry point for manual resource
               assignment operations. It ensures data integrity by validating all resources
               before making any database changes, then atomically updates assignments.
Parameters   : db (Session) - SQLAlchemy database session for queries and transactions
               job_id (int) - ID of the job to assign resources to
               employee_ids (List[int]) - list of employee IDs to assign to the job
               machine_ids (List[int]) - list of machine IDs to assign to the job
               tenant_id (int) - tenant ID for multi-tenant scoping and security
Returns      : list - list of dictionaries with "type" ("employee"/"machine") and "id" keys
               representing successfully created assignments
Calls        : _date_range() from availability_engine to calculate job date span
               _is_employee_busy() from availability_engine to check for conflicts
               _is_machine_busy() from availability_engine to check for conflicts
               _effective_availability() from availability_engine to calculate availability
DB/API       : Queries Job, Employee, Machine, AvailabilityOverride tables with tenant filtering
               Deletes existing JobAssignment records for the job
               Inserts new JobAssignment records for each resource
               Updates job status if currently "Pending Assignment"
Side effects : Modifies database by deleting old assignments and creating new ones
               Changes job status to "Scheduled"
               Commits database transaction

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
WHO CALLS THIS FILE
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

backend/app/routers/jobs_router.py - imports assign_resources for manual assignment endpoints
backend/app/routers/scheduler_router.py - may import for programmatic assignments
backend/app/services/scheduler_service.py - likely imports for automated scheduling

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
IMPORTS EXPLAINED
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

from typing import List
  Provides List type annotation for function parameters expecting lists of integers

from sqlalchemy.orm import Session
  SQLAlchemy Session class for database connections and transaction management

from app.models.job import Job, JobAssignment
  Job model represents manufacturing jobs, JobAssignment links jobs to resources

from app.models.employee import Employee
  Employee model represents workers who can be assigned to jobs

from app.models.machine import Machine
  Machine model represents equipment that can be assigned to jobs

from app.models.availability import AvailabilityOverride
  AvailabilityOverride model stores temporary availability changes for resources

from app.services.availability_engine import (_date
"""

from typing import List
from sqlalchemy.orm import Session

from app.models.job import Job, JobAssignment
from app.models.employee import Employee
from app.models.machine import Machine
from app.models.availability import AvailabilityOverride
from app.services.availability_engine import (
    _date_range,
    _is_employee_busy,
    _is_machine_busy,
    _effective_availability,
)


class AssignmentError(Exception):
    pass


def assign_resources(
    db: Session,
    job_id: int,
    employee_ids: List[int],
    machine_ids: List[int],
    tenant_id: int,          # ← ADDED
) -> list:
    job = db.query(Job).filter(
        Job.id == job_id,
        Job.tenant_id == tenant_id,     # ← tenant scoped
    ).first()
    if not job:
        raise AssignmentError(f"Job {job_id} not found")

    days = _date_range(job.start_date, job.end_date)

    # --- Validate employees ---
    for emp_id in employee_ids:
        emp = db.query(Employee).filter(
            Employee.id == emp_id,
            Employee.tenant_id == tenant_id,    # ← tenant scoped
        ).first()
        if not emp:
            raise AssignmentError(f"Employee {emp_id} not found")
        if emp.status != "Active":
            raise AssignmentError(f"Employee '{emp.full_name}' is not Active (status: {emp.status})")

        emp_overrides = (
            db.query(AvailabilityOverride)
            .filter(AvailabilityOverride.employee_id == emp_id)
            .all()
        )
        for d in days:
            eff = _effective_availability(emp.base_availability_pct, emp_overrides, d)
            if eff <= 0:
                raise AssignmentError(f"Employee '{emp.full_name}' is unavailable on {d}")

        if _is_employee_busy(db, emp_id, job_id, days, tenant_id=tenant_id):
            raise AssignmentError(
                f"Employee '{emp.full_name}' is already assigned to another job in this date range"
            )

    # --- Validate machines ---
    for machine_id in machine_ids:
        machine = db.query(Machine).filter(
            Machine.id == machine_id,
            Machine.tenant_id == tenant_id,     # ← tenant scoped
        ).first()
        if not machine:
            raise AssignmentError(f"Machine {machine_id} not found")
        if machine.status != "Operational":
            raise AssignmentError(f"Machine '{machine.name}' is not Operational (status: {machine.status})")

        machine_overrides = (
            db.query(AvailabilityOverride)
            .filter(AvailabilityOverride.machine_id == machine_id)
            .all()
        )
        for d in days:
            eff = _effective_availability(machine.base_availability_pct, machine_overrides, d)
            if eff <= 0:
                raise AssignmentError(f"Machine '{machine.name}' is unavailable on {d}")

        if _is_machine_busy(db, machine_id, job_id, days, tenant_id=tenant_id):
            raise AssignmentError(
                f"Machine '{machine.name}' is already assigned to another job in this date range"
            )

    # --- All validations passed — clear and re-insert ---
    db.query(JobAssignment).filter(
        JobAssignment.job_id == job_id,
        JobAssignment.tenant_id == tenant_id,   # ← tenant scoped delete
    ).delete()

    created = []
    for emp_id in employee_ids:
        db.add(JobAssignment(
            job_id=job_id,
            employee_id=emp_id,
            tenant_id=tenant_id,                # ← ADDED
        ))
        created.append({"type": "employee", "id": emp_id})

    for machine_id in machine_ids:
        db.add(JobAssignment(
            job_id=job_id,
            machine_id=machine_id,
            tenant_id=tenant_id,                # ← ADDED
        ))
        created.append({"type": "machine", "id": machine_id})

    if job.status == "Pending Assignment":
        job.status = "Scheduled"

    db.commit()
    return created
