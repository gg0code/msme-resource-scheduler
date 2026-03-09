"""
services/availability_engine.py — V1.1
Added: tenant_id scoping to all queries in _is_employee_busy,
       _is_machine_busy, and check_availability to prevent
       cross-tenant data leakage.
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
    tenant_id: Optional[int] = None,   # ← ADDED
) -> bool:
    q = (
        db.query(Job)
        .join(JobAssignment, JobAssignment.job_id == Job.id)
        .filter(
            JobAssignment.employee_id == employee_id,
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
            conflicts.append(ConflictDetail(
                resource_type="employee", resource_id=req.skill_id,
                resource_name=f"Skill: {skill_name} (need {req.employees_required}, found {len(qualified)})",
                dates=[str(d) for d in days],
                reason=f"Insufficient qualified employees for '{skill_name}' at '{req.min_skill_level}' level",
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
