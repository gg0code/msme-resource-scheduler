"""
```python
"""
backend/app/models/job.py — Core Job Data Models

FILE PURPOSE
This file defines the primary SQLAlchemy ORM models for jobs in the ZetaOps Copilot
scheduling system. It contains the Job model (the main work unit that gets scheduled),
JobSkillRequirement (defines what skills a job needs), and JobAssignment (tracks which
employees and machines are allocated to jobs). This file was part of the original v1.0
architecture and has been enhanced through multiple versions, most recently with J1.2
delivery and payment tracking fields. These models sit at the heart of the scheduling
engine and are used by every part of the system that deals with work orders.

WHAT THIS FILE DOES — step by step
1. Imports SQLAlchemy column types, relationship functions, and the Base class from our database module
2. Imports datetime utilities for timezone-aware timestamp handling
3. Defines the Job class with all core job fields including basic info, scheduling control, timing, and financial tracking
4. Sets up database relationships from Job to JobSkillRequirement and JobAssignment models
5. Defines JobSkillRequirement class to specify what skills and skill levels a job needs
6. Defines JobAssignment class to track employee and machine allocations with percentage-based resource allocation
7. Establishes foreign key relationships and cascade deletion rules to maintain data integrity

KEY FUNCTIONS / CLASSES / COMPONENTS

Job
  Type         : SQLAlchemy ORM Model Class
  Purpose      : Represents a work order or job that needs to be scheduled and completed by the manufacturing business. Contains all job metadata, scheduling preferences, timing information, financial data, and delivery requirements. This is the central entity that the scheduling engine operates on.
  Parameters   : N/A (ORM model, instantiated with keyword arguments for field values)
  Returns      : N/A (ORM model instance)
  Calls        : None directly (SQLAlchemy handles database operations)
  DB/API       : Mapped to "jobs" table in PostgreSQL, includes foreign key to tenants table
  Side effects : Database writes when instances are committed through SQLAlchemy session

JobSkillRequirement  
  Type         : SQLAlchemy ORM Model Class
  Purpose      : Defines skill prerequisites for a job, specifying what skills are needed, minimum competency levels, and how many employees with those skills are required. Used by the scheduling engine to identify skill gaps and ensure proper resource allocation.
  Parameters   : N/A (ORM model, instantiated with keyword arguments for field values)
  Returns      : N/A (ORM model instance)  
  Calls        : None directly (SQLAlchemy handles database operations)
  DB/API       : Mapped to "job_skill_requirements" table, includes foreign keys to jobs, skills, and tenants tables
  Side effects : Database writes when instances are committed, cascading deletes when parent job is deleted

JobAssignment
  Type         : SQLAlchemy ORM Model Class
  Purpose      : Tracks the allocation of specific employees and machines to jobs, including what percentage of their time is allocated. Created by the scheduling engine and used to enforce resource conflicts and availability calculations.
  Parameters   : N/A (ORM model, instantiated with keyword arguments for field values)
  Returns      : N/A (ORM model instance)
  Calls        : None directly (SQLAlchemy handles database operations) 
  DB/API       : Mapped to "job_assignments" table, includes foreign keys to jobs, employees, machines, and tenants tables
  Side effects : Database writes when instances are committed, handles SET NULL on employee/machine deletion

WHO CALLS THIS FILE
- backend/app/crud/job.py (imports Job, JobSkillRequirement, JobAssignment for database queries)
- backend/app/routers/scheduler_router.py (imports Job model for loading jobs to schedule)
- backend/app/services/availability_engine.py (imports JobAssignment to check resource conflicts)
- backend/app/scheduler/engine.py (imports Job and related models for scheduling algorithm)
- backend/app/routers/job_router.py (imports all models for CRUD operations)
- backend/alembic/versions/*.py (migration files reference these table names)

IMPORTS EXPLAINED
- sqlalchemy Column, Integer, String, Float, Date, DateTime, ForeignKey, Text, JSON, Boolean: SQLAlchemy column type definitions needed to define database table structure and field constraints
- sqlalchemy.orm relationship: Defines relationships between models so SQLAlchemy can handle joins and cascade operations automatically  
- datetime datetime, timezone: Used for timezone-aware timestamp defaults in created_at and updated_at fields
- app.database Base: The SQLAlchemy declarative base class that all ORM models must inherit from to be recognized by our database configuration

INTERN NOTES
- Easiest thing to break: Forgetting tenant_id on new fields or relationships - this will create cross-tenant data leaks and violates design principle #2
- Non-obvious design decision: timer_status and timing fields are on Job instead of JobStep because legacy v1-v3 had job-level timers, and we maintain backward compatibility while new workflows use step-level timing
- Most common mistake: Using the wrong cascade settings on relationships - "all, delete-orphan" vs "SET NULL" determines whether child records are deleted or just unlinked when parent is removed
- Design principle implemented: #2 (tenant scoping) - every model has tenant_id foreign key with proper indexes and cascade deletion from tenant
- What to check if behaving unexpectedly: Verify all database queries in crud/ files include tenant_id filter, check that foreign key constraints match your expectations, and ensure migration files properly handle schema changes
- V5 merger consideration: N/A - this is a core v4-dev model file that v5-whatsapp inherits unchanged, though new WhatsApp-related models may reference Job via foreign keys
"""
```
"""

from sqlalchemy import Column, Integer, String, Float, Date, DateTime, ForeignKey, Text, JSON, Boolean
from sqlalchemy.orm import relationship
from datetime import datetime, timezone
from app.database import Base


class Job(Base):
    __tablename__ = "jobs"

    id          = Column(Integer, primary_key=True, index=True)
    tenant_id   = Column(Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
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
    timer_log       = Column(JSON, nullable=True)

    # ── J1.1 Scheduling fields ──────────────────────────────────────────────
    # start_mode: 'right_away' | 'pick_a_date' | 'flexible'
    # right_away  → start_date locked to today, job is auto-locked
    # pick_a_date → start_date user-chosen, job is auto-locked
    # flexible    → scheduler may place job between earliest_date and latest_date
    start_mode    = Column(String(20), nullable=False, default="pick_a_date")
    is_locked     = Column(Boolean, nullable=False, default=False)
    has_conflict  = Column(Boolean, nullable=False, default=False)
    earliest_date = Column(Date, nullable=True)
    latest_date   = Column(Date, nullable=True)

    # ── v3.9.6 Material Estimation prerequisites ────────────────────────────
    job_type  = Column(String(100), nullable=True)   # e.g. "Corrugated Box", "Label"
    quantity  = Column(Float, nullable=True)         # units to produce

    # ── J1.2 Delivery, Invoice & Actuals ────────────────────────────────────
    delivery_date  = Column(Date, nullable=True)         # customer delivery deadline
    invoice_number = Column(String(50), nullable=True)
    invoice_date   = Column(Date, nullable=True)
    payment_status = Column(String(20), nullable=True, default='Unpaid')  # Unpaid|Partial|Paid
    payment_amount = Column(Float, nullable=True)
    payment_date   = Column(Date, nullable=True)
    actual_hours   = Column(Float, nullable=True)        # stored on job end

    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    skill_requirements = relationship("JobSkillRequirement", back_populates="job", cascade="all, delete-orphan", lazy="select")
    assignments        = relationship("JobAssignment", back_populates="job", cascade="all, delete-orphan", lazy="select")


class JobSkillRequirement(Base):
    __tablename__ = "job_skill_requirements"

    id                 = Column(Integer, primary_key=True, index=True)
    tenant_id          = Column(Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    job_id             = Column(Integer, ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False)
    skill_id           = Column(Integer, ForeignKey("skills.id", ondelete="CASCADE"), nullable=False)
    min_skill_level    = Column(String(20), nullable=False, default="Generic")
    employees_required = Column(Integer, nullable=False, default=1)

    job   = relationship("Job", back_populates="skill_requirements")
    skill = relationship("Skill", back_populates="job_skill_requirements")


class JobAssignment(Base):
    __tablename__ = "job_assignments"

    id          = Column(Integer, primary_key=True, index=True)
    tenant_id   = Column(Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    job_id      = Column(Integer, ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False)
    employee_id = Column(Integer, ForeignKey("employees.id", ondelete="SET NULL"), nullable=True)
    machine_id  = Column(Integer, ForeignKey("machines.id", ondelete="SET NULL"), nullable=True)
    assigned_at    = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    allocation_pct = Column(Integer, nullable=True, default=100)  # % of time this resource is allocated

    job      = relationship("Job", back_populates="assignments", lazy="select")
    employee = relationship("Employee", back_populates="assignments", lazy="select")
    machine  = relationship("Machine", back_populates="assignments", lazy="select")
