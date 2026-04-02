"""
```python
"""
FILE PURPOSE
────────────────────────────────────────────────────────────────────────────────────
This file implements the main dashboard API endpoint for the ZetaOps Copilot manufacturing
scheduling system. It provides a comprehensive overview of the tenant's current operations
including job summaries, resource availability, upcoming work, and detailed job information
with conflict detection and cost analysis. This endpoint was introduced in v2.0 and sits
in the API layer between the React frontend dashboard and the core scheduling/availability
services. Version 2.1 fixed critical SQLAlchemy 2.0 N+1 query performance issues.

WHAT THIS FILE DOES — step by step
────────────────────────────────────────────────────────────────────────────────────
1. Defines FastAPI router with dashboard endpoint at GET /api/dashboard/
2. Provides _derive_status_icon() helper to convert job status/timer into UI icon codes
3. Provides _build_job_row() helper that constructs detailed job data including conflicts and costs
4. Executes tenant-scoped database queries for summary statistics (jobs, machines, employees)
5. Loads all tenant jobs with pre-loaded assignments/employee/machine relationships (performance optimized)
6. Calculates jobs-by-status breakdown for dashboard charts
7. Finds upcoming jobs within next 7 days for priority visibility
8. Calls _build_job_row() for each job to add conflict detection and cost calculations
9. Returns comprehensive dashboard JSON with summaries, upcoming work, and full job details

KEY FUNCTIONS / CLASSES / COMPONENTS
────────────────────────────────────────────────────────────────────────────────────
Name         : _derive_status_icon
Type         : function (private helper)
Purpose      : Converts job status and timer_status fields into standardized icon codes
               for the frontend dashboard UI. Handles completed, stopped, in_progress,
               conflict, and ready states with proper precedence rules.
Parameters   : job (Job) - SQLAlchemy Job model instance
               has_conflict (bool) - whether availability engine detected conflicts
Returns      : str - icon code ("completed", "stopped", "in_progress", "conflict", "ready")
Calls        : None - pure logic function
DB/API       : None
Side effects : None

Name         : _build_job_row
Type         : function (private helper)
Purpose      : Constructs detailed job information for dashboard display including conflict
               detection, cost analysis, and assigned resources. Uses pre-loaded relationships
               to avoid N+1 queries. This is the core data transformation for job display.
Parameters   : db (Session) - SQLAlchemy database session
               job (Job) - Job model with pre-loaded assignments/employee/machine
               tenant_id (int) - tenant ID for scoping availability checks
Returns      : dict - comprehensive job data including conflicts, costs, assignments, dates
Calls        : app.services.availability_engine.check_availability()
               app.services.cost_service.compute_tentative_cost()
               app.services.cost_service.compute_actual_cost()
DB/API       : None directly (uses pre-loaded data), but cost services may query
Side effects : None

Name         : get_dashboard
Type         : FastAPI endpoint (GET /api/dashboard/)
Purpose      : Main dashboard endpoint that provides comprehensive tenant operations overview.
               Returns summary statistics, job breakdowns, upcoming work priorities, and
               detailed job information with conflicts and costs for the React dashboard.
Parameters   : db (Session) - injected database session via FastAPI dependency
               current_user (User) - injected authenticated user via JWT dependency
Returns      : dict - dashboard data with totals, breakdowns, upcoming jobs, full job list
Calls        : _build_job_row() for each job
               Database queries for counts and job loading
DB/API       : Multiple tenant-scoped queries:
               - Count active jobs (Scheduled/In Progress/Draft)
               - Count operational machines
               - Count active employees  
               - Load all jobs with selectinload optimization
               - Load upcoming jobs (next 7 days)
Side effects : None (read-only endpoint)

WHO CALLS THIS FILE
────────────────────────────────────────────────────────────────────────────────────
- backend/app/main.py - registers this router with "/api/dashboard" prefix
- frontend/src/api/api_dashboard.ts - makes HTTP GET request to fetch dashboard data
- frontend/src/pages/Dashboard.tsx - displays the dashboard UI using this endpoint's data

IMPORTS EXPLAINED
────────────────────────────────────────────────────────────────────────────────────
- fastapi.APIRouter - creates FastAPI router instance for dashboard endpoints
- fastapi.Depends - enables dependency injection for database session and authentication
- sqlalchemy.orm.Session - database session type for SQLAlchemy queries
- sqlalchemy.orm.selectinload - eager loading strategy to prevent N+1 query problems
- sqlalchemy.func - SQL functions like count() for aggregate queries
- datetime.date, timedelta - date arithmetic for "upcoming this week" filtering
- app.database.get_db - dependency that provides database session to endpoints
- app.models.job.Job, JobAssignment - SQLAlchemy models for job and assignment data
- app.models.employee.Employee - SQLAlchemy model for employee data
- app.models.machine.Machine - SQLAlchemy model for machine data
- app.core.dependencies.get_current_user - authentication dependency that extracts JWT user
- app.models.auth.User - SQLAlchemy model for authenticated user data
- app.services.cost_service functions - calculate tentative and actual job costs
- app.services.availability_engine.check_availability - detects scheduling conflicts

INTERN NOTES
────────────────────────────────────────────────────────────────────────────────────
• Easiest thing to break: Removing selectinload() will cause N+1 query explosion and
  SQLAlchemy 2.0 "anon_1 subquery" errors when _build_job_row accesses job.assignments
• Non-obvious design decision: We load ALL jobs then filter in memory rather than separate
  queries because the dashboard needs both summary stats and detailed job data anyway
• Most common mistake: Forgetting tenant_id filter on database queries creates security
  vulnerability allowing cross-tenant data access (violates design principle #2)
• Design principle implemented: #2 (tenant scoping on ALL DB queries) and #1 (engine
  computes, AI only narrates - this provides computed data for AI service consumption)  
• What to check if unexpected behavior: Verify selectinload relationships are working,
  check availability_engine and cost_service for exceptions, confirm tenant_id filtering
• Not applicable to v5-whatsapp: This is core v4-dev functionality used by both branches
"""
```
"""

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
    """Build a single job row — uses pre-loaded job.assignments (no extra queries)."""

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
    actual    = compute_actual_cost(db, job)

    # ── Use pre-loaded assignments — no extra DB queries ──────────────────────
    employees = []
    machines  = []
    for a in job.assignments:          # already loaded via selectinload
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
        # Cost grids
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

    # Summary counts — simple scalar queries, no relationship loading needed
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

    # ── All jobs — load assignments + employee + machine in 3 queries total ───
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

    # Upcoming jobs this week
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
        "jobs": [_build_job_row(db, j, tid) for j in all_jobs],
    }
