"""
routers/dashboard.py — V2.0

Extended dashboard endpoint returning:
  - Summary counts (active jobs, machines, employees)
  - Per-job data with:
      * tentative_cost breakdown
      * actual_cost breakdown (only for completed/stopped jobs)
      * timer state, conflict state, status_icon
  - jobs_by_status counts
  - upcoming_jobs_this_week (unchanged for summary cards)
"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from datetime import date, timedelta

from app.database import get_db
from app.models.job import Job, JobAssignment
from app.models.employee import Employee
from app.models.machine import Machine
from app.core.dependencies import get_current_user
from app.models.auth import User
from app.services.cost_service import compute_tentative_cost, compute_actual_cost
from app.services.availability_engine import check_availability

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


def _build_job_row(db: Session, job: Job, tenant_id: int) -> dict:
    """Build a single job row for the dashboard jobs list."""

    # Conflict check
    has_conflict = False
    conflict_reasons = []
    try:
        avail = check_availability(db, job.id, tenant_id)
        has_conflict = not avail.feasible
        conflict_reasons = [c.reason for c in avail.conflicts]
    except Exception:
        pass

    # Costs
    tentative = compute_tentative_cost(db, job)
    actual = compute_actual_cost(db, job)  # None if not completed

    # Assigned resources
    assignments = db.query(JobAssignment).filter(
        JobAssignment.job_id == job.id,
        JobAssignment.tenant_id == tenant_id,
    ).all()

    employees = []
    machines = []
    for a in assignments:
        if a.employee_id:
            emp = db.query(Employee).filter(Employee.id == a.employee_id).first()
            if emp:
                employees.append({"id": emp.id, "full_name": emp.full_name})
        if a.machine_id:
            mac = db.query(Machine).filter(Machine.id == a.machine_id).first()
            if mac:
                machines.append({"id": mac.id, "name": mac.name})

    return {
        "id": job.id,
        "name": job.name,
        "customer": job.customer,
        "priority": job.priority,
        "status": job.status,
        "timer_status": job.timer_status or "idle",
        "start_date": str(job.start_date) if job.start_date else None,
        "end_date": str(job.end_date) if job.end_date else None,
        "actual_start_at": job.actual_start_at.isoformat() if job.actual_start_at else None,
        "actual_end_at": job.actual_end_at.isoformat() if job.actual_end_at else None,
        "paused_seconds": job.paused_seconds or 0,
        "has_conflict": has_conflict,
        "conflict_reasons": conflict_reasons,
        "status_icon": _derive_status_icon(job, has_conflict),
        "assigned_employees": employees,
        "assigned_machines": machines,
        # Cost grids
        "tentative_cost": tentative["total_cost"],
        "tentative_profit": tentative["profit"],
        "tentative_breakdown": tentative,
        # actual_cost / actual_profit only populated once job is completed or stopped
        "actual_cost": actual["total_cost"] if actual else None,
        "actual_profit": actual["profit"] if actual else None,
        "actual_breakdown": actual,
        "order_value": job.order_value,
    }


@router.get("/")
def get_dashboard(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    today = date.today()
    week_end = today + timedelta(days=7)
    tid = current_user.tenant_id

    # Summary counts
    total_active_jobs = db.query(Job).filter(
        Job.tenant_id == tid,
        Job.status.in_(["Scheduled", "In Progress", "Draft"]),
    ).count()

    available_machines = db.query(Machine).filter(
        Machine.tenant_id == tid,
        Machine.status == "Operational",
    ).count()

    available_employees = db.query(Employee).filter(
        Employee.tenant_id == tid,
        Employee.status == "Active",
    ).count()

    # All jobs for this tenant (for the main jobs board)
    all_jobs = (
        db.query(Job)
        .filter(Job.tenant_id == tid)
        .order_by(Job.start_date)
        .all()
    )

    jobs_by_status: dict = {}
    for job in all_jobs:
        jobs_by_status[job.status] = jobs_by_status.get(job.status, 0) + 1

    # Upcoming jobs this week (for summary widget)
    upcoming_jobs = db.query(Job).filter(
        Job.tenant_id == tid,
        Job.start_date >= today,
        Job.start_date <= week_end,
        Job.status.in_(["Scheduled", "Pending Assignment", "Draft"]),
    ).order_by(Job.start_date).all()

    return {
        "total_active_jobs": total_active_jobs,
        "available_machines": available_machines,
        "available_employees": available_employees,
        "jobs_by_status": jobs_by_status,
        "upcoming_jobs_this_week": [
            {
                "id": j.id,
                "name": j.name,
                "start_date": str(j.start_date),
                "end_date": str(j.end_date),
                "priority": j.priority,
                "status": j.status,
            }
            for j in upcoming_jobs
        ],
        # Full job rows for the dashboard jobs board
        "jobs": [_build_job_row(db, j, tid) for j in all_jobs],
    }
