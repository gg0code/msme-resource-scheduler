# app/routers/gantt.py - Version 3.1
# Branch: both
#
# FILE PURPOSE
# Gantt/Timeline API - returns job data formatted for the visual timeline.
# Conflict detection uses schedule_entries (same as Jobs page) not the
# availability engine, so all pages show consistent conflict state.
#
# KEY DESIGN DECISIONS
# - _build_entry_count_map: loads ALL entry counts in one query (O(1) not O(N))
# - _has_scheduling_conflict: pure function, no DB calls, uses pre-loaded map
# - Conflict = scheduler could not fill all expected daily slots for a job
#
# WHO CALLS THIS FILE
# - GET /api/gantt/ - GanttPage.tsx (useQuery key: 'sched-jobs')
#   Invalidated by useScheduler after each run so bars auto-update

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session, selectinload
from pydantic import BaseModel
from typing import List, Optional
from datetime import date

from app.database import get_db
from app.core.dependencies import get_current_user
from app.models.auth import User
from app.models.job import Job, JobAssignment
from app.models.employee import Employee
from app.models.machine import Machine
from app.services.cost_service import compute_tentative_cost, compute_actual_cost
from app.utils.feature_guard import require_feature

def _build_entry_count_map(db, tenant_id: int) -> dict:
    """Load schedule entry counts for ALL jobs in one query - O(1) not O(N).
    Returns {job_id: entry_count}. Call once per request."""
    from app.routers.scheduler_router import ScheduleEntryModel
    from sqlalchemy import select as _sel_cnt, func as _func
    rows = db.execute(
        _sel_cnt(ScheduleEntryModel.job_id, _func.count().label("cnt"))
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


router = APIRouter()


class GanttJob(BaseModel):
    id: int
    name: str
    customer: Optional[str] = None
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    priority: Optional[str] = None
    status: Optional[str] = None
    timer_status: Optional[str] = None
    assigned_employees: List[str]
    assigned_machines: List[str]
    has_conflict: bool
    conflict_reasons: List[str]
    # 'ready' | 'conflict' | 'in_progress' | 'completed' | 'stopped'
    status_icon: str
    tentative_cost: Optional[float] = None
    tentative_profit: Optional[float] = None
    # Scheduled date slots from schedule_entries.
    # Each string is an ISO date (YYYY-MM-DD) on which this job has a
    # confirmed schedule entry. Used by GanttPage to render solid bars
    # for scheduled days and a dashed gap box for unscheduled gap days.
    # Empty list = not yet scheduled (show solid bar from start to end).
    scheduled_dates: List[str] = []

    class Config:
        from_attributes = True


def _derive_status_icon(job: Job, has_conflict: bool) -> str:
    """
    Derive the display icon type for the job.
      ready       → green dot (blinking if can start)
      conflict    → red dot
      in_progress → green arrow right
      completed   → blue dot
      stopped     → black dot
    """
    s = (job.status or "").lower()
    t = (job.timer_status or "idle").lower()

    if s == "completed":
        return "completed"
    if s == "stopped":
        return "stopped"
    if t == "running" or s == "in progress":
        return "in_progress"
    # idle / draft / scheduled
    if has_conflict:
        return "conflict"
    return "ready"


@router.get("/")
def get_gantt_data(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # V3.7 - feature flag guard
    guard = require_feature("gantt")
    if guard:
        return guard

    tenant_id = current_user.tenant_id

    jobs = (
        db.query(Job)
        .options(
            selectinload(Job.assignments).selectinload(JobAssignment.employee),
            selectinload(Job.assignments).selectinload(JobAssignment.machine),
        )
        .filter(Job.tenant_id == tenant_id)
        .order_by(Job.start_date)
        .all()
    )

    entry_count_map = _build_entry_count_map(db, tenant_id)

    # Load scheduled dates per job in one query.
    # Returns {job_id: sorted list of ISO date strings}.
    # ScheduleEntryModel imported inside _build_entry_count_map; import here too
    # so this function is self-contained and not order-dependent.
    from app.routers.scheduler_router import ScheduleEntryModel
    from sqlalchemy import select as _sel_dates
    raw_entries = db.execute(
        _sel_dates(ScheduleEntryModel.job_id, ScheduleEntryModel.scheduled_start)
        .where(ScheduleEntryModel.tenant_id == tenant_id)
        .order_by(ScheduleEntryModel.job_id, ScheduleEntryModel.scheduled_start)
    ).all()
    scheduled_dates_map: dict[int, list[str]] = {}
    seen_dates: set[tuple] = set()  # deduplicate (job_id, date) pairs
    for row in raw_entries:
        d = row[1].date().isoformat() if row[1] else None
        if d and (row[0], d) not in seen_dates:
            seen_dates.add((row[0], d))
            scheduled_dates_map.setdefault(row[0], []).append(d)

    result = []
    for job in jobs:
        employee_names = []
        machine_names = []
        for a in job.assignments:
            if a.employee_id and a.employee:
                employee_names.append(a.employee.full_name)
            if a.machine_id and a.machine:
                machine_names.append(a.machine.name)

        # Conflict detection
        has_conflict, conflict_reasons = _has_scheduling_conflict(job, entry_count_map)

        # Costs
        t_cost = compute_tentative_cost(db, job)

        result.append(
            GanttJob(
                id=job.id,
                name=job.name,
                customer=job.customer,
                start_date=job.start_date,
                end_date=job.end_date,
                priority=job.priority,
                status=job.status,
                timer_status=job.timer_status,
                assigned_employees=list(set(employee_names)),
                assigned_machines=list(set(machine_names)),
                has_conflict=has_conflict,
                conflict_reasons=conflict_reasons,
                status_icon=_derive_status_icon(job, has_conflict),
                tentative_cost=t_cost["total_cost"],
                tentative_profit=t_cost["profit"],
                scheduled_dates=scheduled_dates_map.get(job.id, []),
            )
        )

    return result
