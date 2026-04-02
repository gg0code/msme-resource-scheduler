"""
routers/gantt.py — V3.7

GET /api/gantt/
Returns all jobs for the tenant enriched with:
  - assigned employee names and machine names
  - has_conflict (bool) + conflict_reasons (list of strings)
  - status_icon: one of 'ready' | 'conflict' | 'in_progress' | 'completed' | 'stopped'

Read-only. No writes.
Registered in main.py as /api/gantt
V3.7: feature flag guard — returns warm message if gantt flag is False
"""

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
from app.services.availability_engine import check_availability
from app.services.cost_service import compute_tentative_cost, compute_actual_cost
from app.utils.feature_guard import require_feature

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

    model_config = {"from_attributes": True}


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
    # V3.7 — feature flag guard
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
        has_conflict = False
        conflict_reasons: List[str] = []
        try:
            avail = check_availability(db, job.id, tenant_id)
            has_conflict = not avail.feasible
            conflict_reasons = [c.reason for c in avail.conflicts]
        except Exception:
            pass

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
            )
        )

    return result
