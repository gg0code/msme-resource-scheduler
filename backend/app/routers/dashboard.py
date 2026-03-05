"""
routers/dashboard.py — V1.1
Added: JWT auth, tenant_id scoping
  GET — any authenticated user
"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from datetime import date, timedelta

from app.database import get_db
from app.models.job import Job
from app.models.employee import Employee
from app.models.machine import Machine
from app.core.dependencies import get_current_user
from app.models.auth import User

router = APIRouter()


@router.get("/")
def get_dashboard(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    today = date.today()
    week_end = today + timedelta(days=7)
    tid = current_user.tenant_id

    total_active_jobs = db.query(Job).filter(
        Job.tenant_id == tid,
        Job.status.in_(["Scheduled", "In Progress"]),
    ).count()

    status_counts = {}
    for job in db.query(Job).filter(Job.tenant_id == tid).all():
        status_counts[job.status] = status_counts.get(job.status, 0) + 1

    available_machines = db.query(Machine).filter(
        Machine.tenant_id == tid,
        Machine.status == "Operational",
    ).count()

    available_employees = db.query(Employee).filter(
        Employee.tenant_id == tid,
        Employee.status == "Active",
    ).count()

    upcoming_jobs = db.query(Job).filter(
        Job.tenant_id == tid,
        Job.start_date >= today,
        Job.start_date <= week_end,
        Job.status.in_(["Scheduled", "Pending Assignment"]),
    ).order_by(Job.start_date).all()

    return {
        "total_active_jobs": total_active_jobs,
        "available_machines": available_machines,
        "available_employees": available_employees,
        "jobs_by_status": status_counts,
        "upcoming_jobs_this_week": [
            {
                "id": j.id, "name": j.name,
                "start_date": str(j.start_date), "end_date": str(j.end_date),
                "priority": j.priority, "status": j.status,
                "tentative_profit": j.tentative_profit,
            }
            for j in upcoming_jobs
        ],
    }
