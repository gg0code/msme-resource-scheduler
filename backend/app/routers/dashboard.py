# app/routers/dashboard.py - Version 2.3
# Branch: both
#
# FILE PURPOSE
# Dashboard API - aggregates job, resource, and cost state for the dashboard.
#
# KEY DESIGN DECISIONS
# - Conflict detection uses schedule_entries (same as Jobs page), not the
#   availability engine. Date-range overlap != scheduling conflict after
#   auto-schedule has run and resolved jobs into non-overlapping time slots.
# - _build_entry_count_map: loads ALL entry counts in one query (O(1) not O(N))
#   avoids N+1 DB calls that caused login/dashboard slowdown.
# - selectinload used for assignments to avoid lazy-load N+1 on job.assignments.
#
# WHO CALLS THIS FILE
# - GET /api/dashboard/            - Dashboard.tsx
# - GET /api/dashboard/plan-limits - PlanLimitGuard component


from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session, selectinload
from sqlalchemy import func
from datetime import date, timedelta

from app.database import get_db
from app.models.job import Job, JobAssignment
from app.models.employee import Employee
from app.models.machine import Machine
from app.core.dependencies import get_current_user
from app.models.auth import User
from app.services.cost_service import compute_tentative_cost, compute_actual_cost

router = APIRouter()


def _derive_status_icon(job: Job, has_conflict: bool) -> str:
    s = (job.status or "").lower()
    t = (job.timer_status or "idle").lower()
    if s == "completed":
        return "completed"
    if s == "stopped":
        return "stopped"
    if t == "running" or s == "in progress":
        return "in_progress"
    if has_conflict:
        return "conflict"
    return "ready"



def _build_entry_count_map(db, tenant_id: int) -> dict:
    """Load schedule entry counts for ALL jobs in one query - O(1) not O(N).
    Returns {job_id: entry_count}. Call once per request."""
    from app.routers.scheduler_router import ScheduleEntryModel
    from sqlalchemy import select as _sel, func as _func
    rows = db.execute(
        _sel(ScheduleEntryModel.job_id, _func.count().label("cnt"))
        .where(ScheduleEntryModel.tenant_id == tenant_id)
        .group_by(ScheduleEntryModel.job_id)
    ).all()
    return {row[0]: row[1] for row in rows}


def _has_scheduling_conflict(job, entry_count_map: dict) -> tuple:
    """Check conflict using pre-loaded counts. No extra DB query per job."""
    count = entry_count_map.get(job.id, 0)
    if count == 0:
        return False, []
    if job.start_date and job.end_date:
        ref_start = job.original_start_date or job.start_date
        ref_end   = job.original_end_date   or job.end_date
        expected  = max(1, (ref_end - ref_start).days + 1)
        if count < expected:
            return True, [
                f"{expected - count} of {expected} scheduled days unresolved - "
                f"run Auto-Schedule to push to next available slot"
            ]
    return False, []

def _build_job_row(db: Session, job: Job, tenant_id: int, entry_count_map: dict) -> dict:
    """Build a single job row — uses pre-loaded job.assignments (no extra queries)."""

    has_conflict, conflict_reasons = _has_scheduling_conflict(job, entry_count_map)

    # Costs
    tentative = compute_tentative_cost(db, job)
    actual    = compute_actual_cost(db, job)

    # Use pre-loaded assignments — no extra DB queries
    employees = []
    machines  = []
    for a in job.assignments:
        if a.employee:
            employees.append({"id": a.employee.id, "full_name": a.employee.full_name})
        if a.machine:
            machines.append({"id": a.machine.id, "name": a.machine.name})

    return {
        "id":           job.id,
        "name":         job.name,
        "customer":     job.customer,
        "priority":     job.priority,
        "status":       job.status,
        "timer_status": job.timer_status or "idle",
        "start_date":   str(job.start_date)  if job.start_date  else None,
        "end_date":     str(job.end_date)    if job.end_date    else None,
        "actual_start_at": job.actual_start_at.isoformat() if job.actual_start_at else None,
        "actual_end_at":   job.actual_end_at.isoformat()   if job.actual_end_at   else None,
        "paused_seconds":  job.paused_seconds or 0,
        "has_conflict":    has_conflict,
        "conflict_reasons": conflict_reasons,
        "status_icon":     _derive_status_icon(job, has_conflict),
        "assigned_employees": employees,
        "assigned_machines":  machines,
        "tentative_cost":      tentative["total_cost"],
        "tentative_profit":    tentative["profit"],
        "tentative_breakdown": tentative,
        "actual_cost":         actual["total_cost"] if actual else None,
        "actual_profit":       actual["profit"]     if actual else None,
        "actual_breakdown":    actual,
        "order_value":         job.order_value,
    }


@router.get("/")
def get_dashboard(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    today    = date.today()
    week_end = today + timedelta(days=7)
    tid      = current_user.tenant_id

    total_active_jobs = (
        db.query(func.count()).select_from(Job)
        .filter(Job.tenant_id == tid, Job.status.in_(["Scheduled", "In Progress", "Draft"]))
        .scalar()
    )

    available_machines = (
        db.query(func.count()).select_from(Machine)
        .filter(Machine.tenant_id == tid, Machine.status == "Operational")
        .scalar()
    )

    available_employees = (
        db.query(func.count()).select_from(Employee)
        .filter(Employee.tenant_id == tid, Employee.status == "Active")
        .scalar()
    )

    all_jobs = (
        db.query(Job)
        .options(
            selectinload(Job.assignments).selectinload(JobAssignment.employee),
            selectinload(Job.assignments).selectinload(JobAssignment.machine),
        )
        .filter(Job.tenant_id == tid)
        .order_by(Job.start_date)
        .all()
    )

    jobs_by_status: dict = {}
    for job in all_jobs:
        jobs_by_status[job.status] = jobs_by_status.get(job.status, 0) + 1

    upcoming_jobs = (
        db.query(Job)
        .filter(
            Job.tenant_id == tid,
            Job.start_date >= today,
            Job.start_date <= week_end,
            Job.status.in_(["Scheduled", "Pending Assignment", "Draft"]),
        )
        .order_by(Job.start_date)
        .all()
    )

    entry_count_map = _build_entry_count_map(db, tid)

    return {
        "total_active_jobs":      total_active_jobs,
        "available_machines":     available_machines,
        "available_employees":    available_employees,
        "jobs_by_status":         jobs_by_status,
        "upcoming_jobs_this_week": [
            {
                "id":         j.id,
                "name":       j.name,
                "start_date": str(j.start_date),
                "end_date":   str(j.end_date),
                "priority":   j.priority,
                "status":     j.status,
            }
            for j in upcoming_jobs
        ],
        "jobs": [_build_job_row(db, j, tid, entry_count_map) for j in all_jobs],
    }


@router.get("/plan-limits")
def get_plan_limits(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Returns current plan usage counts and limits for the tenant.
    Called by PlanLimitGuard (frontend) at /dashboard/plan-limits.
    No /api/ prefix — registered directly on the dashboard router.
    """
    tid  = current_user.tenant_id
    plan = getattr(getattr(current_user, 'tenant', None), 'plan', None) or 'free'

    emp_count = (
        db.query(func.count()).select_from(Employee)
        .filter(Employee.tenant_id == tid)
        .scalar() or 0
    )
    mac_count = (
        db.query(func.count()).select_from(Machine)
        .filter(Machine.tenant_id == tid)
        .scalar() or 0
    )
    job_count = (
        db.query(func.count()).select_from(Job)
        .filter(Job.tenant_id == tid, Job.status.notin_(['Completed', 'Cancelled']))
        .scalar() or 0
    )

    LIMITS = {
        'free':       {'employees': 10, 'machines': 10, 'jobs': 20, 'raw_materials': 5},
        'pro':        {'employees': None, 'machines': None, 'jobs': None, 'raw_materials': None},
        'enterprise': {'employees': None, 'machines': None, 'jobs': None, 'raw_materials': None},
    }
    lim = LIMITS.get(plan, LIMITS['free'])

    def make(current, limit):
        return {
            'current':   current,
            'limit':     limit,
            'reached':   limit is not None and current >= limit,
            'unlimited': limit is None,
        }

    return {
        'plan': plan,
        'limits': {
            'employees':    make(emp_count, lim['employees']),
            'machines':     make(mac_count, lim['machines']),
            'jobs':         make(job_count, lim['jobs']),
            'raw_materials': make(0, lim['raw_materials']),
        }
    }
