# app/services/assignment_service.py - Version 2.0
# Branch: both
#
# FILE PURPOSE
# Assigns employees and machines to a job. Writes JobAssignment rows.
# v2.0: Removed all "is busy" / date overlap checks. Duplicate assignments
# are now explicitly allowed. Conflict detection and resolution is the
# scheduler engine's job (app/scheduler/engine.py), not this service.
#
# WHAT THIS FILE DOES
# 1. Validates that each employee/machine belongs to the tenant and is active
# 2. Clears existing assignments for the job (full replace on each call)
# 3. Writes new JobAssignment rows for all provided employees and machines
# 4. Promotes job status from "Pending Assignment" to "Scheduled"
#
# WHAT THIS FILE INTENTIONALLY DOES NOT DO
# - It does NOT check if a resource is busy on overlapping dates
# - It does NOT block assignment of a resource already on another job
# - It does NOT check availability overrides at assignment time
# These were removed in v2.0. Rationale:
#   Blocking overlaps at assignment time forces the user to manually
#   resolve scheduling conflicts before the scheduler runs. This defeats
#   the purpose of the auto-scheduler. The correct flow is:
#     1. User assigns any resources to any jobs freely
#     2. Conflicts are detected by the availability engine
#     3. Auto-scheduler resolves conflicts by priority (Critical > locked > profit margin)
#   The Dashboard and Jobs page show conflict banners so the user knows
#   when to run the scheduler.
#
# WHO CALLS THIS FILE
# - app/routers/assignments.py - POST /api/assignments/
#
# INTERN NOTES
# - AssignmentError is still raised for hard violations (resource not found,
#   resource inactive) but NOT for date overlap or busy conflicts
# - The full replace pattern (delete then insert) is intentional -
#   it avoids partial update bugs and keeps assignment state consistent
# - tenant_id is enforced on every query - cross-tenant leakage is a
#   security bug not a style issue

from typing import List
from sqlalchemy.orm import Session

from app.models.job import Job, JobAssignment
from app.models.employee import Employee
from app.models.machine import Machine


class AssignmentError(Exception):
    """Raised when an assignment cannot be created due to a hard constraint.

    Hard constraints (raise AssignmentError):
      - Resource does not exist or belongs to a different tenant
      - Employee is not Active
      - Machine is not Operational

    Soft constraints (do NOT raise - handled by scheduler):
      - Resource already assigned to another job on overlapping dates
      - Resource has an availability override on these dates
    """


def assign_resources(
    db: Session,
    job_id: int,
    employee_ids: List[int],
    machine_ids: List[int],
    tenant_id: int,
) -> list:
    """
    Assign employees and machines to a job.

    Replaces all existing assignments for the job on every call.
    Allows any resource to be assigned regardless of date overlap with
    other jobs - conflict resolution is handled by the scheduler engine.

    Args:
        db:           SQLAlchemy session
        job_id:       ID of the job to assign resources to
        employee_ids: List of employee IDs to assign
        machine_ids:  List of machine IDs to assign
        tenant_id:    Tenant scope - all queries are filtered by this

    Returns:
        List of dicts describing created assignments:
        [{"type": "employee", "id": 1}, {"type": "machine", "id": 2}]

    Raises:
        AssignmentError: If job, employee, or machine not found or inactive
    """
    # -- Verify job exists and belongs to this tenant -------------------------
    job = db.query(Job).filter(
        Job.id == job_id,
        Job.tenant_id == tenant_id,
    ).first()
    if not job:
        raise AssignmentError(f"Job {job_id} not found")

    # -- Validate employees ---------------------------------------------------
    # Only hard checks: existence, tenant ownership, active status
    # Date overlap is NOT checked here - scheduler handles conflicts
    for emp_id in employee_ids:
        emp = db.query(Employee).filter(
            Employee.id == emp_id,
            Employee.tenant_id == tenant_id,
        ).first()
        if not emp:
            raise AssignmentError(f"Employee {emp_id} not found")
        if emp.status != "Active":
            raise AssignmentError(
                f"Employee '{emp.full_name}' is not Active (status: {emp.status}). "
                f"Only Active employees can be assigned to jobs."
            )

    # -- Validate machines ----------------------------------------------------
    # Only hard checks: existence, tenant ownership, operational status
    # Date overlap is NOT checked here - scheduler handles conflicts
    for machine_id in machine_ids:
        machine = db.query(Machine).filter(
            Machine.id == machine_id,
            Machine.tenant_id == tenant_id,
        ).first()
        if not machine:
            raise AssignmentError(f"Machine {machine_id} not found")
        if machine.status != "Operational":
            raise AssignmentError(
                f"Machine '{machine.name}' is not Operational (status: {machine.status}). "
                f"Only Operational machines can be assigned to jobs."
            )

    # -- Clear existing assignments for this job ------------------------------
    # Full replace pattern: safer than partial update, avoids stale rows
    db.query(JobAssignment).filter(
        JobAssignment.job_id == job_id,
        JobAssignment.tenant_id == tenant_id,
    ).delete()

    # -- Create new assignment rows -------------------------------------------
    created: list = []

    for emp_id in employee_ids:
        db.add(JobAssignment(
            job_id=job_id,
            employee_id=emp_id,
            tenant_id=tenant_id,
        ))
        created.append({"type": "employee", "id": emp_id})

    for machine_id in machine_ids:
        db.add(JobAssignment(
            job_id=job_id,
            machine_id=machine_id,
            tenant_id=tenant_id,
        ))
        created.append({"type": "machine", "id": machine_id})

    # -- Promote job status if it was waiting for assignment ------------------
    if job.status == "Pending Assignment":
        job.status = "Scheduled"

    db.commit()
    return created
