"""
```python
"""
FILE PURPOSE
This file is the single source of truth for ALL cost calculations in the ZetaOps Copilot scheduling system. 
It computes job costs using a unified formula for both tentative (planned) and actual costs, with the only 
difference being how hours are calculated. Introduced in v2.0 to centralize cost logic that was previously 
scattered across multiple files. Sits in the services layer between route handlers and the database, providing 
cost calculations for job management, reporting, and the End Job workflow.

WHAT THIS FILE DOES — step by step
1. Defines internal helper functions to calculate raw material costs and assignment costs
2. Provides compute_tentative_cost() for planned job costs based on estimated duration
3. Provides compute_actual_cost() for completed jobs based on actual time tracked
4. Provides compute_cost_preview() for live cost calculations during job completion workflow
5. Returns standardized cost breakdown dictionaries with employee, machine, material, and misc costs
6. Calculates profit as order_value minus total_cost for all cost computation types

KEY FUNCTIONS / CLASSES / COMPONENTS

Name         : _raw_material_cost
Type         : function (internal helper)
Purpose      : Sums the total cost of raw materials for a job by multiplying quantity × unit_cost for each 
               material item in the job's raw_materials JSON array. Handles malformed data gracefully by 
               skipping invalid entries.
Parameters   : raw_materials (list | None) - JSON array of material objects with quantity and unit_cost fields
Returns      : float - total material cost, 0.0 if no materials or invalid data
Calls        : None (pure calculation function)
DB/API       : No database queries or API calls
Side effects : None

Name         : _assignment_costs
Type         : function (internal helper)
Purpose      : Calculates employee and machine costs for a job by fetching current hourly rates from the 
               database and multiplying by hours. Uses sets to avoid double-counting resources assigned 
               to multiple job steps. Always filters by tenant_id for security.
Parameters   : db (Session) - SQLAlchemy database session
               job_id (int) - ID of the job to calculate costs for
               tenant_id (int) - tenant ID for security filtering
               hours (float) - number of hours to multiply by hourly rates
Returns      : tuple[float, float] - (employee_cost, machine_cost) totals
Calls        : SQLAlchemy queries to Employee and Machine models
DB/API       : Queries JobAssignment, Employee, and Machine tables with tenant_id filtering
Side effects : None

Name         : compute_tentative_cost
Type         : function (public API)
Purpose      : Computes projected job costs based on planned start_date and end_date using 
               estimated_hours_per_day. Used for job planning, quotes, and dashboard projections 
               before work begins. Returns empty breakdown if dates are missing.
Parameters   : db (Session) - SQLAlchemy database session for resource lookups
               job (Job) - Job model instance with start_date, end_date, and cost fields
Returns      : dict - standardized cost breakdown with hours, employee_cost, machine_cost, material_cost, 
               misc_cost, total_cost, order_value, and profit (all rounded to 2 decimals)
Calls        : _assignment_costs() and _raw_material_cost() helper functions
DB/API       : Indirect DB queries through _assignment_costs() for employee/machine rates
Side effects : None

Name         : compute_actual_cost
Type         : function (public API)
Purpose      : Computes final job costs based on actual_start_at and actual_end_at timestamps, 
               subtracting paused_seconds to get net working time. Used for final job costing 
               and profit analysis after job completion. Returns None if job is not complete.
Parameters   : db (Session) - SQLAlchemy database session for resource lookups
               job (Job) - Job model instance with actual timing and cost fields
Returns      : dict | None - standardized cost breakdown dict if job complete, None if incomplete
Calls        : _assignment_costs() and _raw_material_cost() helper functions
DB/API       : Indirect DB queries through _assignment_costs() for employee/machine rates
Side effects : None

Name         : compute_cost_preview
Type         : function (public API)
Purpose      : Calculates costs for a custom set of employees and machines with specified hours 
               WITHOUT reading current job assignments. Used in the End Job modal to show live 
               cost updates as users select resources and enter actual hours before saving.
Parameters   : db (Session) - SQLAlchemy database session for resource lookups
               job (Job) - Job model instance for tenant_id and base cost fields
               employee_ids (list[int]) - list of employee IDs to include in cost calculation
               machine_ids (list[int]) - list of machine IDs to include in cost calculation
               actual_hours (float) - hours to multiply by hourly rates
Returns      : dict - standardized cost breakdown with preview calculations
Calls        : Direct SQLAlchemy queries to Employee and Machine tables
DB/API       : Queries Employee and Machine tables filtered by tenant_id for security
Side effects : None

Name         : _empty_breakdown
Type         : function (internal helper)
Purpose      : Returns a standardized cost breakdown dictionary with all fields set to 0.0. 
               Used as fallback when cost calculations cannot be performed due to missing data.
Parameters   : None
Returns      : dict - cost breakdown with all zero values matching the standard structure
Calls        : None
DB/API       : No database queries or API calls
Side effects : None

WHO CALLS THIS FILE
- backend/app/routers/job_router.py - imports cost functions for job CRUD endpoints
- backend/app/routers/scheduler_router.py - uses tentative costs for scheduling decisions
- backend/app/routers/reporting_router.py - generates cost reports and profit analysis
- backend/app/services/job_service.py - integrates costs into job management workflows

IMPORTS EXPLAINED
- datetime (date, datetime): Used for date arithmetic to calculate duration_days and time differences between actual timestamps
- typing (Optional): Provides type hints for functions that may return None, specifically compute_actual_cost
- sqlalchemy.orm (Session): Database session type for all cost calculation functions that need to query hourly rates
- app.models.job (Job, JobAssignment): Job model for cost fields and JobAssignment for employee/machine assignments
- app.models.employee (Employee): Employee model to fetch current hourly_rate values for cost calculations
- app.models.machine (Machine): Machine model to fetch current hourly_rate values for cost calculations

INTERN NOTES
- Easiest thing to break: Forgetting tenant_id filtering in database queries - this creates security vulnerabilities where tenants can see other tenants' cost data
- Non-obvious design decision: Uses sets (seen_employees, seen_machines) to avoid double-counting resources assigned to multiple steps of the same job, preventing inflated cost calculations
- Most common mistake: Assuming job.actual_start_at exists - always check for None before computing actual costs or the function will crash
- Implements design principle #2: All database queries include tenant_id filtering for security, never allowing cross-tenant data access
- What to check if behaving unexpectedly: Verify that Employee and Machine hourly_rate fields are not None/null in the database, and that raw_materials JSON is properly formatted
- This is v4-dev code: No WhatsApp-specific features, safe to merge between branches, but verify that v5 hasn't added new cost calculation requirements
```
"""

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
