"""
services/assignment_service.py — V1.1
Added: tenant_id scoping on all queries and inserts
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

        if _is_employee_busy(db, emp_id, job_id, days):
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

        if _is_machine_busy(db, machine_id, job_id, days):
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
