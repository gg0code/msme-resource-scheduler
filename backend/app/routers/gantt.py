"""
```python
"""
FILE PURPOSE
This file provides a read-only FastAPI router that returns Gantt chart visualization data for 
jobs within a tenant's organization. Introduced in V3.7 on the v4-dev branch, it sits in the 
presentation layer of the architecture, fetching job data from the database and enriching it 
with conflict detection, cost calculations, and resource assignments to feed frontend Gantt 
chart components.

WHAT THIS FILE DOES — step by step
1. Defines a FastAPI router with prefix /api/gantt (registered in main.py)
2. Creates a GanttJob Pydantic model for structured API responses
3. Implements _derive_status_icon() helper function to compute visual status indicators
4. Exposes GET /api/gantt/ endpoint that requires authentication and feature flag
5. Queries all jobs for the current user's tenant with eager-loaded assignments
6. For each job, extracts assigned employee and machine names from JobAssignment relationships
7. Runs conflict detection via availability_engine to identify scheduling issues
8. Computes tentative costs and profit margins using cost_service
9. Maps each job to GanttJob response model with enriched data
10. Returns list of GanttJob objects ordered by start_date for frontend consumption

KEY FUNCTIONS / CLASSES / COMPONENTS

Name         : GanttJob
Type         : Pydantic BaseModel class
Purpose      : Defines the response schema for job data returned to frontend Gantt components. 
               Contains all job fields plus computed enrichments like conflict status, assigned 
               resource names, visual status icons, and cost calculations.
Parameters   : id (int), name (str), customer (Optional[str]), start_date (Optional[date]), 
               end_date (Optional[date]), priority (Optional[str]), status (Optional[str]), 
               timer_status (Optional[str]), assigned_employees (List[str]), 
               assigned_machines (List[str]), has_conflict (bool), conflict_reasons (List[str]), 
               status_icon (str), tentative_cost (Optional[float]), tentative_profit (Optional[float])
Returns      : Not applicable (data model class)
Calls        : None (Pydantic model)
DB/API       : None
Side effects : None

Name         : _derive_status_icon
Type         : Private helper function
Purpose      : Converts raw job status and timer_status fields into standardized visual 
               indicator strings for frontend display. Maps business logic states to UI 
               icon types with conflict detection override.
Parameters   : job (Job) - SQLAlchemy Job model instance, has_conflict (bool) - whether 
               availability_engine detected scheduling conflicts
Returns      : String literal: 'ready' | 'conflict' | 'in_progress' | 'completed' | 'stopped'
               representing the visual state for UI rendering
Calls        : None (pure function)
DB/API       : None
Side effects : None

Name         : get_gantt_data
Type         : FastAPI endpoint (GET /api/gantt/)
Purpose      : Main endpoint that fetches all jobs for the authenticated user's tenant and 
               enriches them with assignment details, conflict detection, cost calculations, 
               and visual status indicators. Protected by authentication and gantt feature flag.
Parameters   : db (Session) - SQLAlchemy database session via dependency injection, 
               current_user (User) - authenticated user from JWT token via dependency injection
Returns      : List[GanttJob] - JSON array of enriched job objects with all data needed 
               for frontend Gantt chart rendering, or feature flag guard response if disabled
Calls        : require_feature(), check_availability(), compute_tentative_cost(), _derive_status_icon()
DB/API       : Queries Job table with eager-loaded JobAssignment, Employee, and Machine relationships 
               filtered by tenant_id and ordered by start_date
Side effects : None (read-only endpoint)

WHO CALLS THIS FILE
- frontend/src/api/api_gantt.ts - Axios wrapper functions for frontend API calls
- frontend/src/pages/GanttPage.tsx - React component that displays the Gantt chart view
- backend/app/main.py - Registers this router with /api/gantt prefix during application startup

IMPORTS EXPLAINED
- fastapi.APIRouter, Depends - FastAPI routing and dependency injection framework
- sqlalchemy.orm.Session, selectinload - Database session management and eager loading for ORM queries
- pydantic.BaseModel - Data validation and serialization framework for API response models
- typing.List, Optional - Type hints for function signatures and model fields
- datetime.date - Date type for job start/end date fields
- app.database.get_db - Database session dependency for SQLAlchemy connection
- app.core.dependencies.get_current_user - JWT authentication dependency that extracts user from token
- app.models.auth.User - SQLAlchemy User model for type hints and tenant_id access
- app.models.job.Job, JobAssignment - Core job and assignment models for database queries
- app.models.employee.Employee, Machine - Resource models for assignment relationship loading
- app.services.availability_engine.check_availability - Conflict detection service for scheduling validation
- app.services.cost_service.compute_tentative_cost, compute_actual_cost - Cost calculation utilities
- app.utils.feature_guard.require_feature - Feature flag validation utility

INTERN NOTES
• Easiest thing to break: Removing tenant_id filter from job query - creates major security vulnerability allowing cross-tenant data access
• Non-obvious design decision: Uses selectinload() for eager loading instead of joinedload() because assignments is a one-to-many relationship that could create cartesian product issues
• Most common mistake: Forgetting that conflict detection can throw exceptions and should be wrapped in try/catch, or assuming has_conflict=True always means conflict_reasons has items
• Design principles implemented: #2 (tenant scoping on ALL DB queries), #7 (reads from Job/JobStep tables not legacy), #8 (feature flags gate optional features)  
• What to check if unexpected behavior: Verify gantt feature flag is enabled, check that jobs have proper start_date for ordering, ensure availability_engine dependencies are working
• Not applicable to v5-whatsapp: This file exists only in v4-dev branch and has no WhatsApp-specific functionality to consider during merges
"""
```
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
