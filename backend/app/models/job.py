# app/models/job.py - Version 1.3
# Branch: both
#
# FILE PURPOSE
# SQLAlchemy ORM models for jobs, job steps, and job assignments.
# Layer: model
#
# WHAT THIS FILE DOES
# 1. Defines Job - the core production order entity with timer, lock, and cost fields
# 2. Defines JobSkillRequirement - skill requirements attached to a job
# 3. Defines JobAssignment - maps employees and machines to jobs
#
# KEY MODELS
# - Job              : table jobs - one per production order
# - JobSkillRequirement : table job_skill_requirements - skill gates per job
# - JobAssignment    : table job_assignments - resource allocation rows
#
# WHO CALLS THIS FILE
# - app/routers/jobs.py, dashboard.py, assignments.py, scheduler_router.py
# - app/services/cost_service.py, availability_engine.py
#
# INTERN NOTES
# - All models have tenant_id - every query must filter by tenant_id
# - is_locked=True means scheduler preserves this job's slot and skips re-scheduling
# - allocation_pct on JobAssignment is nullable - NULL means 100% (full allocation)
# - updated_at uses lambda: datetime.now(timezone.utc) not datetime.utcnow (py3.12+)

"""
models/job.py — V1.1
Added tenant_id to Job, JobSkillRequirement, JobAssignment.
"""

from sqlalchemy import Boolean, Column, Integer, String, Float, Date, DateTime, ForeignKey, Text, JSON
from sqlalchemy.orm import relationship
from datetime import datetime, timezone
from app.database import Base


class Job(Base):
    __tablename__ = "jobs"

    id          = Column(Integer, primary_key=True, index=True)
    tenant_id   = Column(Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)  # V1.1
    name        = Column(String(200), nullable=False)
    customer    = Column(String(150), nullable=True)
    description = Column(Text, nullable=True)
    start_date  = Column(Date, nullable=False)
    end_date    = Column(Date, nullable=False)
    estimated_hours_per_day = Column(Float, nullable=False, default=8.0)
    tentative_profit = Column(Float, nullable=True)
    order_value      = Column(Float, nullable=True)
    misc_cost        = Column(Float, nullable=True)
    priority    = Column(String(20), nullable=False, default="Medium")
    status      = Column(String(30), nullable=False, default="Draft")
    notes       = Column(Text, nullable=True)

    raw_materials   = Column(JSON, nullable=True)
    timer_status    = Column(String(20), nullable=False, default="idle")
    actual_start_at = Column(DateTime, nullable=True)
    actual_end_at   = Column(DateTime, nullable=True)
    paused_seconds  = Column(Integer, nullable=False, default=0)
    is_locked            = Column(Boolean, nullable=False, default=False)  # v4.0.9 - locked jobs keep their schedule slot, scheduler skips them

    # Rescheduled date tracking - added v4.0.9
    # original_start_date and original_end_date are set by the scheduler the
    # first time it moves a job's dates from the user's requested dates.
    # A non-null value means "scheduler moved this job - user should review".
    # Cleared to NULL whenever the user edits any aspect of the job, signalling
    # the job is back to user-specified dates and is a fresh scheduling candidate.
    original_start_date  = Column(Date, nullable=True)
    original_end_date    = Column(Date, nullable=True)
    timer_log       = Column(JSON, nullable=True)

    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    skill_requirements = relationship("JobSkillRequirement", back_populates="job", cascade="all, delete-orphan")
    assignments        = relationship("JobAssignment", back_populates="job", cascade="all, delete-orphan")


class JobSkillRequirement(Base):
    __tablename__ = "job_skill_requirements"

    id                 = Column(Integer, primary_key=True, index=True)
    tenant_id          = Column(Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)  # V1.1
    job_id             = Column(Integer, ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False)
    skill_id           = Column(Integer, ForeignKey("skills.id", ondelete="CASCADE"), nullable=False)
    min_skill_level    = Column(String(20), nullable=False, default="Generic")
    employees_required = Column(Integer, nullable=False, default=1)

    job   = relationship("Job", back_populates="skill_requirements")
    skill = relationship("Skill", back_populates="job_skill_requirements")


class JobAssignment(Base):
    __tablename__ = "job_assignments"

    id          = Column(Integer, primary_key=True, index=True)
    tenant_id   = Column(Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)  # V1.1
    job_id      = Column(Integer, ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False)
    employee_id = Column(Integer, ForeignKey("employees.id", ondelete="SET NULL"), nullable=True)
    machine_id  = Column(Integer, ForeignKey("machines.id", ondelete="SET NULL"), nullable=True)
    assigned_at    = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    allocation_pct = Column(Float, nullable=True)  # v1.2 - % of resource time allocated to this job, NULL=100%

    job      = relationship("Job", back_populates="assignments")
    employee = relationship("Employee", back_populates="assignments")
    machine  = relationship("Machine", back_populates="assignments")
