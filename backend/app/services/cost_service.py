from __future__ import annotations
from datetime import date, datetime
from typing import Optional
from sqlalchemy.orm import Session

from app.models.job import Job, JobAssignment
from app.models.employee import Employee
from app.models.machine import Machine


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _raw_material_cost(raw_materials: list | None) -> float:
    """Sum quantity × unit_cost for each raw material item."""
    if not raw_materials:
        return 0.0
    total = 0.0
    for item in raw_materials:
        try:
            total += float(item.get("quantity", 0)) * float(item.get("unit_cost", 0))
        except (TypeError, ValueError):
            pass
    return total


def _assignment_costs(db: Session, job_id: int, tenant_id: int, hours: float) -> tuple[float, float]:
    """
    Returns (employee_cost, machine_cost) for a job given a number of hours.
    Fetches live hourly_rate values from DB.
    """
    assignments = (
        db.query(JobAssignment)
        .filter(JobAssignment.job_id == job_id, JobAssignment.tenant_id == tenant_id)
        .all()
    )

    employee_cost = 0.0
    machine_cost = 0.0

    seen_employees: set[int] = set()
    seen_machines: set[int] = set()

    for a in assignments:
        if a.employee_id and a.employee_id not in seen_employees:
            seen_employees.add(a.employee_id)
            emp = db.query(Employee).filter(
                Employee.id == a.employee_id,
                Employee.tenant_id == tenant_id,
            ).first()
            if emp:
                employee_cost += (emp.hourly_rate or 0.0) * hours

        if a.machine_id and a.machine_id not in seen_machines:
            seen_machines.add(a.machine_id)
            mac = db.query(Machine).filter(
                Machine.id == a.machine_id,
                Machine.tenant_id == tenant_id,
            ).first()
            if mac:
                machine_cost += (mac.hourly_rate or 0.0) * hours

    return employee_cost, machine_cost


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def compute_tentative_cost(db: Session, job: Job) -> dict:
    """
    Compute cost based on planned start_date / end_date and estimated_hours_per_day.
    Returns a breakdown dict.
    """
    if not job.start_date or not job.end_date:
        return _empty_breakdown()

    duration_days = (job.end_date - job.start_date).days + 1
    hours = duration_days * (job.estimated_hours_per_day or 8.0)

    emp_cost, mac_cost = _assignment_costs(db, job.id, job.tenant_id, hours)
    mat_cost = _raw_material_cost(job.raw_materials)
    misc = job.misc_cost or 0.0
    total = emp_cost + mac_cost + mat_cost + misc
    profit = (job.order_value or 0.0) - total

    return {
        "hours": round(hours, 2),
        "employee_cost": round(emp_cost, 2),
        "machine_cost": round(mac_cost, 2),
        "material_cost": round(mat_cost, 2),
        "misc_cost": round(misc, 2),
        "total_cost": round(total, 2),
        "order_value": round(job.order_value or 0.0, 2),
        "profit": round(profit, 2),
    }


def compute_actual_cost(db: Session, job: Job) -> dict | None:
    """
    Compute cost based on actual_start_at / actual_end_at minus paused_seconds.
    Returns None if job has not been completed yet.
    """
    if not job.actual_start_at or not job.actual_end_at:
        return None

    total_seconds = (job.actual_end_at - job.actual_start_at).total_seconds()
    net_seconds = max(0.0, total_seconds - (job.paused_seconds or 0))
    hours = net_seconds / 3600.0

    emp_cost, mac_cost = _assignment_costs(db, job.id, job.tenant_id, hours)
    mat_cost = _raw_material_cost(job.raw_materials)
    misc = job.misc_cost or 0.0
    total = emp_cost + mac_cost + mat_cost + misc
    profit = (job.order_value or 0.0) - total

    return {
        "hours": round(hours, 2),
        "employee_cost": round(emp_cost, 2),
        "machine_cost": round(mac_cost, 2),
        "material_cost": round(mat_cost, 2),
        "misc_cost": round(misc, 2),
        "total_cost": round(total, 2),
        "order_value": round(job.order_value or 0.0, 2),
        "profit": round(profit, 2),
    }


def compute_cost_preview(
    db: Session,
    job: Job,
    employee_ids: list[int],
    machine_ids: list[int],
    actual_hours: float,
) -> dict:
    """
    Used in End Job modal — computes cost for a custom set of employees/machines
    and given actual hours WITHOUT saving to DB.
    """
    emp_cost = 0.0
    mac_cost = 0.0

    for eid in set(employee_ids):
        emp = db.query(Employee).filter(
            Employee.id == eid,
            Employee.tenant_id == job.tenant_id,
        ).first()
        if emp:
            emp_cost += (emp.hourly_rate or 0.0) * actual_hours

    for mid in set(machine_ids):
        mac = db.query(Machine).filter(
            Machine.id == mid,
            Machine.tenant_id == job.tenant_id,
        ).first()
        if mac:
            mac_cost += (mac.hourly_rate or 0.0) * actual_hours

    mat_cost = _raw_material_cost(job.raw_materials)
    misc = job.misc_cost or 0.0
    total = emp_cost + mac_cost + mat_cost + misc
    profit = (job.order_value or 0.0) - total

    return {
        "hours": round(actual_hours, 2),
        "employee_cost": round(emp_cost, 2),
        "machine_cost": round(mac_cost, 2),
        "material_cost": round(mat_cost, 2),
        "misc_cost": round(misc, 2),
        "total_cost": round(total, 2),
        "order_value": round(job.order_value or 0.0, 2),
        "profit": round(profit, 2),
    }


def _empty_breakdown() -> dict:
    return {
        "hours": 0.0,
        "employee_cost": 0.0,
        "machine_cost": 0.0,
        "material_cost": 0.0,
        "misc_cost": 0.0,
        "total_cost": 0.0,
        "order_value": 0.0,
        "profit": 0.0,
    }
