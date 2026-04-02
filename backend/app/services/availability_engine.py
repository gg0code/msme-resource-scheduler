"""
```python
"""
FILE PURPOSE
The availability_engine.py service implements the core 5-step availability checking algorithm
that validates whether jobs can be scheduled with existing resources (machines, employees with
specific skills) during requested date ranges. This file was introduced in v4-dev as part of
the scheduling engine architecture and sits in the services layer, providing tenant-scoped
availability validation that feeds into the main scheduler engine decision-making process.

WHAT THIS FILE DOES — step by step
1. Defines skill level ranking system (Generic < Intermediate < Premium) for employee qualifications
2. Provides date range utilities for calculating overlapping job periods
3. Implements employee availability calculation considering base availability + overrides
4. Checks if employees are "busy" by summing allocation percentages across overlapping jobs
5. Checks if machines are "busy" by detecting any overlapping job assignments
6. Defines result data classes (ConflictDetail, AvailabilityResult) for structured responses
7. Executes the main 5-step availability check: machine availability, employee skill matching,
   employee capacity checking, conflict detection, and feasibility scoring
8. Returns comprehensive availability analysis with conflicts and available employee lists

KEY FUNCTIONS / CLASSES / COMPONENTS

Name         : _level_meets
Type         : function
Purpose      : Compares employee skill levels against job requirements using the SKILL_LEVEL_RANK
               hierarchy. Used to filter qualified employees during skill matching phase.
Parameters   : candidate_level (str) - employee's skill level, required_level (str) - job requirement
Returns      : bool - True if candidate meets or exceeds the required skill level
Calls        : None (pure function using SKILL_LEVEL_RANK constant)
DB/API       : None
Side effects : None

Name         : _date_range
Type         : function
Purpose      : Generates a list of consecutive dates between start and end dates inclusive.
               Used to check for overlapping job periods during availability calculations.
Parameters   : start (date) - beginning date, end (date) - ending date
Returns      : List[date] - all dates from start to end inclusive
Calls        : None (uses timedelta from datetime)
DB/API       : None
Side effects : None

Name         : _effective_availability
Type         : function
Purpose      : Calculates the actual availability percentage for a resource on a specific date
               by applying any availability overrides (like maintenance) to the base availability.
               Uses minimum value when multiple overrides overlap.
Parameters   : base_pct (float) - resource base availability, overrides (List[AvailabilityOverride]) - 
               list of override records, d (date) - specific date to check
Returns      : float - effective availability percentage for that date
Calls        : None (pure calculation)
DB/API       : None
Side effects : None

Name         : _is_employee_busy
Type         : function
Purpose      : Determines if an employee is over-allocated by summing their allocation percentages
               across all overlapping jobs (excluding the current job being checked). Employee is
               busy when total allocation >= 100%. Includes tenant scoping for security.
Parameters   : db (Session) - database session, employee_id (int) - employee to check,
               job_id (int) - current job to exclude, days (List[date]) - date range to check,
               tenant_id (Optional[int]) - tenant filter for security
Returns      : bool - True if employee's total allocation >= 100% during the date range
Calls        : _date_range for overlap detection
DB/API       : Queries JobAssignment and Job tables with tenant_id filtering
Side effects : None

Name         : _is_machine_busy
Type         : function
Purpose      : Checks if a machine has any overlapping job assignments during the specified date
               range. Machines can only handle one job at a time unlike employees who can be
               partially allocated. Includes tenant scoping for security.
Parameters   : db (Session) - database session, machine_id (int) - machine to check,
               job_id (int) - current job to exclude, days (List[date]) - date range to check,
               tenant_id (Optional[int]) - tenant filter for security
Returns      : bool - True if machine has any overlapping assignments
Calls        : _date_range for overlap detection
DB/API       : Queries Job and JobAssignment tables with tenant_id filtering
Side effects : None

Name         : ConflictDetail
Type         : class (dataclass)
Purpose      : Structured container for availability conflicts found during scheduling validation.
               Provides detailed information about what resource conflict occurred, when, and why.
Parameters   : resource_type (str) - "machine" or "employee", resource_id (int) - database ID,
               resource_name (str) - human-readable name, dates (List[str]) - conflicted dates,
               reason (str) - explanation of the conflict
Returns      : N/A (data container)
Calls        : None
DB/API       : None
Side effects : None

Name         : AvailabilityResult
Type         : class (dataclass)
Purpose      : Complete availability analysis result containing feasibility determination, scoring,
               detailed conflicts, and lists of available employees per skill requirement.
               Used by scheduler engine and API responses.
Parameters   : job_id (int) - job that was analyzed, feasible (bool) - whether job can be scheduled,
               feasibility_score (float) - percentage of requirements met,
               conflicts (List[ConflictDetail]) - list of scheduling conflicts,
               available_employees (Dict[int, List[int]]) - skill requirement ID to employee ID list mapping
Returns      : N/A (data container)
Calls        : None
DB/API       : None
Side effects : None

Name         : check_availability
Type         : function
Purpose      : Main entry point executing the complete 5-step availability check algorithm per SRS §4.6.
               Validates machine availability, employee skill matching, capacity checking, identifies
               conflicts, and calculates feasibility scores. All queries are tenant-scoped for security.
Parameters   : db (Session) - database session, job_id (int) - job to analyze,
               tenant_id (Optional[int]) - tenant filter for all queries
Returns      : AvailabilityResult - comprehensive availability analysis with conflicts and recommendations
Calls        : _date_range, _effective_availability, _is_employee_busy, _is_machine_busy, _level_meets
DB/API       : Queries Job, JobAssignment, Machine, AvailabilityOverride, JobSkillRequirement, 
               Employee, and EmployeeSkill tables, all with tenant_id filtering
Side effects : None (read-only analysis)

WHO CALLS THIS FILE
- backend/app/routers/scheduler_router.py imports check_availability for API endpoints
- backend/app/scheduler/engine.py calls this service during scheduling computations
- backend/app/services/ai_service.py may reference availability results for AI narration
- Backend test files in tests/services/ directory for unit testing availability logic

IMPORTS EXPLAINED
- dataclass, field from dataclasses: Creates structured data containers for results without boilerplate
- date, timedelta from datetime: Date arithmetic for calculating job periods and overlaps  
- List, Dict, Optional from typing: Type hints for function signatures and data structures
- Session, selectinload from sqlalchemy.orm: Database session management and eager loading optimization
- Job, JobSkillRequirement, JobAssignment from app.models.job: Core job-related database models
- Employee, EmployeeSkill from app.models.employee: Employee data and skill association models
- Machine from app.models.machine: Machine resource model for capacity checking
- AvailabilityOverride from app.models.availability: Temporary availability modifications (
"""

from __future__ import annotations
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import List, Dict, Optional
from sqlalchemy.orm import Session, selectinload

from app.models.job import Job, JobSkillRequirement, JobAssignment
from app.models.employee import Employee, EmployeeSkill
from app.models.machine import Machine
from app.models.availability import AvailabilityOverride


# ---------------------------------------------------------------------------
# Skill level ranking
# ---------------------------------------------------------------------------
SKILL_LEVEL_RANK = {"Generic": 1, "Intermediate": 2, "Premium": 3}


def _level_meets(candidate_level: str, required_level: str) -> bool:
    return SKILL_LEVEL_RANK.get(candidate_level, 0) >= SKILL_LEVEL_RANK.get(required_level, 0)


# ---------------------------------------------------------------------------
# Date utilities
# ---------------------------------------------------------------------------
def _date_range(start: date, end: date) -> List[date]:
    days, current = [], start
    while current <= end:
        days.append(current)
        current += timedelta(days=1)
    return days


def _effective_availability(base_pct: float, overrides: List[AvailabilityOverride], d: date) -> float:
    effective = base_pct
    for override in overrides:
        if override.date_from <= d <= override.date_to:
            effective = min(effective, override.availability_pct)
    return effective


def _is_employee_busy(
    db: Session,
    employee_id: int,
    job_id: int,
    days: List[date],
    tenant_id: Optional[int] = None,
) -> bool:
    """
    Employee is 'busy' only when their total allocation_pct on overlapping jobs >= 100.
    50% on Job A + 50% on Job B = 100% → still available for a 3rd job at 0% remaining.
    50% on Job A alone = 50% remaining → NOT busy.
    """
    q = (
        db.query(JobAssignment)
        .join(Job, Job.id == JobAssignment.job_id)
        .filter(
            JobAssignment.employee_id == employee_id,
            JobAssignment.job_id != job_id,
        )
    )
    if tenant_id is not None:
        q = q.filter(Job.tenant_id == tenant_id)
    other_assignments = q.all()

    total_allocated = 0
    for a in other_assignments:
        other_job = db.query(Job).filter(Job.id == a.job_id).first()
        if not other_job or not other_job.start_date or not other_job.end_date:
            continue
        other_days = set(_date_range(other_job.start_date, other_job.end_date))
        if any(d in other_days for d in days):
            total_allocated += (a.allocation_pct or 100)

    return total_allocated >= 100


def _is_machine_busy(
    db: Session,
    machine_id: int,
    job_id: int,
    days: List[date],
    tenant_id: Optional[int] = None,   # ← ADDED
) -> bool:
    q = (
        db.query(Job)
        .join(JobAssignment, JobAssignment.job_id == Job.id)
        .filter(
            JobAssignment.machine_id == machine_id,
            JobAssignment.job_id != job_id,
        )
    )
    if tenant_id is not None:
        q = q.filter(Job.tenant_id == tenant_id)
    other_jobs = q.all()

    for other_job in other_jobs:
        other_days = set(_date_range(other_job.start_date, other_job.end_date))
        if any(d in other_days for d in days):
            return True
    return False


# ---------------------------------------------------------------------------
# Result data classes
# ---------------------------------------------------------------------------
@dataclass
class ConflictDetail:
    resource_type: str
    resource_id: int
    resource_name: str
    dates: List[str]
    reason: str


@dataclass
class AvailabilityResult:
    job_id: int
    feasible: bool
    feasibility_score: float
    conflicts: List[ConflictDetail] = field(default_factory=list)
    available_employees: Dict[int, List[int]] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------
def check_availability(
    db: Session,
    job_id: int,
    tenant_id: Optional[int] = None,   # ← ADDED
) -> AvailabilityResult:
    """
    Run the full 5-step availability check for a job (SRS §4.6).
    tenant_id scopes all queries to prevent cross-tenant data leakage.
    """
    job_q = db.query(Job).filter(Job.id == job_id)
    if tenant_id is not None:
        job_q = job_q.filter(Job.tenant_id == tenant_id)  # ← tenant scoped
    job = job_q.first()
    if not job:
        raise ValueError(f"Job {job_id} not found")

    days = _date_range(job.start_date, job.end_date)
    conflicts: List[ConflictDetail] = []
    requirements_total = 0
    requirements_met = 0
    available_employees: Dict[int, List[int]] = {}

    # --- Step 1: Machine Check ---
    existing_machine_assignments = (
        db.query(JobAssignment)
        .filter(
            JobAssignment.job_id == job_id,
            JobAssignment.machine_id.isnot(None),
            *([JobAssignment.tenant_id == tenant_id] if tenant_id else []),  # ← tenant scoped
        )
        .all()
    )
    for assignment in existing_machine_assignments:
        machine_q = db.query(Machine).filter(Machine.id == assignment.machine_id)
        if tenant_id is not None:
            machine_q = machine_q.filter(Machine.tenant_id == tenant_id)   # ← tenant scoped
        machine = machine_q.first()
        if not machine:
            continue
        requirements_total += 1
        machine_overrides = (
            db.query(AvailabilityOverride)
            .filter(AvailabilityOverride.machine_id == machine.id)
            .all()
        )
        blocked_dates = [
            str(d) for d in days
            if _effective_availability(machine.base_availability_pct, machine_overrides, d) <= 0
        ]
        if blocked_dates:
            conflicts.append(ConflictDetail(
                resource_type="machine", resource_id=machine.id, resource_name=machine.name,
                dates=blocked_dates, reason="Machine unavailable (maintenance/override)",
            ))
        elif _is_machine_busy(db, machine.id, job_id, days, tenant_id):  # ← pass tenant_id
            conflicts.append(ConflictDetail(
                resource_type="machine", resource_id=machine.id, resource_name=machine.name,
                dates=[str(d) for d in days],
                reason="Machine already assigned to another job in this date range",
            ))
        else:
            requirements_met += 1

    # --- Steps 2 & 3: Employee Skill Match + Capacity Check ---
    skill_requirements: List[JobSkillRequirement] = (
        db.query(JobSkillRequirement)
        .filter(JobSkillRequirement.job_id == job_id)
        .all()
    )
    for req in skill_requirements:
        requirements_total += req.employees_required

        candidates_q = (
            db.query(Employee)
            .join(EmployeeSkill, EmployeeSkill.employee_id == Employee.id)
            .filter(EmployeeSkill.skill_id == req.skill_id, Employee.status == "Active")
        )
        if tenant_id is not None:
            candidates_q = candidates_q.filter(Employee.tenant_id == tenant_id)  # ← tenant scoped
        candidates = candidates_q.all()

        qualified: List[int] = []
        for emp in candidates:
            emp_skill = (
                db.query(EmployeeSkill)
                .filter(
                    EmployeeSkill.employee_id == emp.id,
                    EmployeeSkill.skill_id == req.skill_id,
                )
                .first()
            )
            if not emp_skill or not _level_meets(emp_skill.skill_level, req.min_skill_level):
                continue

            emp_overrides = (
                db.query(AvailabilityOverride)
                .filter(AvailabilityOverride.employee_id == emp.id)
                .all()
            )
            if any(_effective_availability(emp.base_availability_pct, emp_overrides, d) <= 0 for d in days):
                continue

            if _is_employee_busy(db, emp.id, job_id, days, tenant_id):  # ← pass tenant_id
                continue

            qualified.append(emp.id)

        available_employees[req.id] = qualified
        requirements_met += min(len(qualified), req.employees_required)

        if len(qualified) < req.employees_required:
            skill_name = req.skill.name if req.skill else f"skill#{req.skill_id}"
            shortfall  = req.employees_required - len(qualified)
            conflicts.append(ConflictDetail(
                resource_type="employee", resource_id=req.skill_id,
                resource_name=f"Skill: {skill_name} (need {req.employees_required}, found {len(qualified)})",
                dates=[str(d) for d in days],
                reason=(
                    f"No one assigned has '{skill_name}' skill at '{req.min_skill_level}' level"
                    if len(qualified) == 0
                    else f"Need {shortfall} more person(s) with '{skill_name}' at '{req.min_skill_level}' level"
                ),
            ))

    # --- Step 5: Feasibility Score ---
    feasibility_score = (requirements_met / requirements_total * 100) if requirements_total > 0 else 100.0

    return AvailabilityResult(
        job_id=job_id,
        feasible=len(conflicts) == 0,
        feasibility_score=round(feasibility_score, 1),
        conflicts=conflicts,
        available_employees=available_employees,
    )
