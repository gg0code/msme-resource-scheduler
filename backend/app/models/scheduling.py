"""
```python
"""
FILE PURPOSE
This file defines SQLAlchemy ORM models for the step-based scheduling system in ZetaOps Copilot.
It was introduced in v4-dev as part of the new scheduling engine architecture and contains the core
database schema for jobs, steps, and resources used by the scheduler engine. These models are
prefixed with "sched_" to avoid collision with the legacy Job/Machine tables and represent the
foundation of the pure-Python scheduling algorithm that computes optimal resource allocation.

WHAT THIS FILE DOES — step by step
1. Imports SQLAlchemy column types, relationship functions, and the Base class from app.database
2. Defines six string enums for resource types, job priorities, shifts, job status, step types, and step status
3. Creates SchedResource model representing machines and helpers with shift times and tenant scoping
4. Creates SchedJob model representing scheduling jobs with priority, deadline, profit, and status tracking
5. Creates SchedStep model representing ordered steps within jobs with duration and machine reservations
6. Creates SchedStepMachine model for many-to-many relationship between steps and machine resources
7. Creates SchedStepHelper model for many-to-many relationship between steps and helper resources
8. Establishes all SQLAlchemy relationships with proper cascade deletion and foreign key constraints
9. Adds unique constraints to ensure data integrity across tenant boundaries and step sequences

KEY FUNCTIONS / CLASSES / COMPONENTS

Name         : ResourceType
Type         : string enum
Purpose      : Defines the two types of resources available in the scheduling system - machines and helpers.
              This enum is used to differentiate between equipment (machines) and human resources (helpers)
              when the scheduling engine allocates resources to job steps.
Parameters   : machine (equipment/machinery), helper (human workers)
Returns      : String enum values for database storage
Calls        : None (enum definition)
DB/API       : Used as column type in SchedResource.type field
Side effects : None

Name         : SchedJobPriority  
Type         : string enum
Purpose      : Defines priority levels for scheduling jobs to help the greedy priority scheduler determine
              execution order. Critical jobs get scheduled first, followed by urgent, then low priority jobs.
Parameters   : critical (highest priority), urgent (medium priority), low (lowest priority)
Returns      : String enum values for database storage
Calls        : None (enum definition)
DB/API       : Used as column type in SchedJob.priority field
Side effects : None

Name         : SchedJobShift
Type         : string enum  
Purpose      : Defines work shifts that jobs can be assigned to, allowing the scheduler to respect shift
              boundaries when allocating resources and determining job timing constraints.
Parameters   : morning (first shift), evening (second shift)
Returns      : String enum values for database storage
Calls        : None (enum definition)
DB/API       : Used as column type in SchedJob.shift field
Side effects : None

Name         : SchedJobStatus
Type         : string enum
Purpose      : Tracks the lifecycle state of scheduling jobs from creation through completion. Used by
              the scheduler engine to filter jobs and by the UI to display current job states.
Parameters   : pending (not yet scheduled), scheduled (assigned resources), in_progress (actively running), complete (finished)
Returns      : String enum values for database storage  
Calls        : None (enum definition)
DB/API       : Used as column type in SchedJob.status field
Side effects : None

Name         : StepType
Type         : string enum
Purpose      : Distinguishes between regular production steps and setup steps within jobs. Setup steps
              may have different scheduling rules or resource requirements than regular production steps.
Parameters   : regular (normal production step), setup (preparation/configuration step)
Returns      : String enum values for database storage
Calls        : None (enum definition)
DB/API       : Used as column type in SchedStep.step_type field  
Side effects : None

Name         : StepStatus
Type         : string enum
Purpose      : Tracks the execution state of individual job steps through their lifecycle. Used by the
              scheduler to determine step readiness and by the auto_advance background task for progression.
Parameters   : pending (waiting), ready (can start), in_progress (executing), complete (finished)
Returns      : String enum values for database storage
Calls        : None (enum definition) 
DB/API       : Used as column type in SchedStep.status field
Side effects : None

Name         : SchedResource
Type         : SQLAlchemy ORM class
Purpose      : Represents schedulable resources (machines and helpers) with their availability windows.
              Each resource has shift times that constrain when it can be allocated to job steps. The
              scheduler engine reads these models to determine resource availability and conflicts.
Parameters   : tenant_id (int, foreign key), name (string), type (ResourceType enum), shift_start (time), shift_end (time)
Returns      : Database model instance with relationships to step assignments
Calls        : None (model definition)
DB/API       : Creates sched_resources table with unique constraint on tenant_id+name
Side effects : Cascades delete to related SchedStepMachine and SchedStepHelper records

Name         : SchedJob  
Type         : SQLAlchemy ORM class
Purpose      : Represents scheduling jobs that contain ordered steps and have business constraints like
              deadlines and profit targets. The scheduler engine uses priority and deadline fields to
              determine optimal job sequencing while respecting lock_status for manual overrides.
Parameters   : tenant_id (int), name (string), priority (enum), expected_profit (float), deadline (datetime), shift (enum), lock_status (bool), status (enum)
Returns      : Database model instance with relationship to child steps
Calls        : None (model definition)
DB/API       : Creates sched_jobs table with automatic timestamps and status tracking
Side effects : Cascades delete to all related SchedStep records when job is deleted

Name         : SchedStep
Type         : SQLAlchemy ORM class  
Purpose      : Represents individual ordered steps within scheduling jobs, each with resource requirements
              and duration constraints. Steps can reserve specific machines and link to multiple resources
              through M2M relationships. The scheduler reads duration_minutes for time calculations.
Parameters   : job_id (int, foreign key), sequence_order (int), step_type (enum), duration_minutes (int), status (enum), reserve_machine_id (int, optional foreign key)
Returns      : Database model instance with relationships to job, resources, and machine/helper links
Calls        : None (model definition)
DB/API       : Creates sched_steps table with unique constraint on job_id+sequence_order  
Side effects : Cascades delete to SchedStepMachine and SchedStepHelper M2M records

Name         : SchedStepMachine
Type         : SQLAlchemy ORM class
Purpose      : Many-to-many relationship table linking job steps to machine resources. Allows steps to
              specify multiple compatible machines while the scheduler engine picks the optimal allocation
              based on availability and conflicts across the entire schedule.
Parameters   : step_id (int, foreign key), resource_id (int, foreign key)
Returns      : Database model instance representing step-machine relationship
Calls        : None (model definition)
DB/API       : Creates sched_step_machines table with unique constraint preventing duplicate links
Side effects : None (pure relationship table)

Name         : SchedStepHelper
Type         : SQLAlchemy ORM class
Purpose      : Many-to-many relationship table linking job steps to helper/worker resources. Similar to
              SchedStepMachine but for human resources, allowing the scheduler to allocate available
              workers to steps that require manual labor or supervision.
Parameters   : step_id (int, foreign key), resource_id (int, foreign key)  
Returns
"""

import enum
from datetime import datetime, time, timezone

from sqlalchemy import (
    Boolean, Column, DateTime, Enum as SAEnum,
    Float, ForeignKey, Integer, String, Time, UniqueConstraint,
)
from sqlalchemy.orm import relationship

from app.database import Base


# ─── Enums ────────────────────────────────────────────────────────────────────

class ResourceType(str, enum.Enum):
    machine = "machine"
    helper  = "helper"


class SchedJobPriority(str, enum.Enum):
    critical = "critical"
    urgent   = "urgent"
    low      = "low"


class SchedJobShift(str, enum.Enum):
    morning = "morning"
    evening = "evening"


class SchedJobStatus(str, enum.Enum):
    pending     = "pending"
    scheduled   = "scheduled"
    in_progress = "in_progress"
    complete    = "complete"


class StepType(str, enum.Enum):
    regular = "regular"
    setup   = "setup"


class StepStatus(str, enum.Enum):
    pending     = "pending"
    ready       = "ready"
    in_progress = "in_progress"
    complete    = "complete"


# ─── Resource ─────────────────────────────────────────────────────────────────

class SchedResource(Base):
    __tablename__ = "sched_resources"

    id          = Column(Integer, primary_key=True, index=True)
    tenant_id   = Column(Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    name        = Column(String(150), nullable=False)
    type        = Column(SAEnum(ResourceType, name="resource_type_enum"), nullable=False)
    shift_start = Column(Time, nullable=False, default=time(8, 0))
    shift_end   = Column(Time, nullable=False, default=time(16, 0))
    created_at  = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    # Relationships
    machine_steps = relationship("SchedStepMachine", back_populates="resource", cascade="all, delete-orphan")
    helper_steps  = relationship("SchedStepHelper",  back_populates="resource", cascade="all, delete-orphan")
    reserved_steps = relationship(
        "SchedStep",
        foreign_keys="SchedStep.reserve_machine_id",
        back_populates="reserve_machine",
    )

    __table_args__ = (
        UniqueConstraint("tenant_id", "name", name="uq_sched_resource_tenant_name"),
    )


# ─── Job ──────────────────────────────────────────────────────────────────────

class SchedJob(Base):
    __tablename__ = "sched_jobs"

    id               = Column(Integer, primary_key=True, index=True)
    tenant_id        = Column(Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    name             = Column(String(200), nullable=False)
    priority         = Column(SAEnum(SchedJobPriority, name="sched_job_priority_enum"), nullable=False, default=SchedJobPriority.low)
    expected_profit  = Column(Float, nullable=True)
    deadline         = Column(DateTime, nullable=False)
    shift            = Column(SAEnum(SchedJobShift, name="sched_job_shift_enum"), nullable=False, default=SchedJobShift.morning)
    lock_status      = Column(Boolean, nullable=False, default=False)
    status           = Column(SAEnum(SchedJobStatus, name="sched_job_status_enum"), nullable=False, default=SchedJobStatus.pending)
    created_at       = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at       = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    steps = relationship(
        "SchedStep",
        back_populates="job",
        cascade="all, delete-orphan",
        order_by="SchedStep.sequence_order",
        lazy="select",
    )


# ─── Step ─────────────────────────────────────────────────────────────────────

class SchedStep(Base):
    __tablename__ = "sched_steps"
    __table_args__ = (
        UniqueConstraint("job_id", "sequence_order", name="uq_sched_step_job_seq"),
    )

    id               = Column(Integer, primary_key=True, index=True)
    job_id           = Column(Integer, ForeignKey("sched_jobs.id", ondelete="CASCADE"), nullable=False, index=True)
    sequence_order   = Column(Integer, nullable=False)
    step_type        = Column(SAEnum(StepType, name="step_type_enum"), nullable=False, default=StepType.regular)
    duration_minutes = Column(Integer, nullable=False)
    status           = Column(SAEnum(StepStatus, name="step_status_enum"), nullable=False, default=StepStatus.pending)
    reserve_machine_id = Column(
        Integer,
        ForeignKey("sched_resources.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    job             = relationship("SchedJob", back_populates="steps")
    reserve_machine = relationship(
        "SchedResource",
        foreign_keys=[reserve_machine_id],
        back_populates="reserved_steps",
    )
    machine_links = relationship("SchedStepMachine", back_populates="step", cascade="all, delete-orphan", lazy="select")
    helper_links  = relationship("SchedStepHelper",  back_populates="step", cascade="all, delete-orphan", lazy="select")


# ─── Step ↔ Machine (M2M) ─────────────────────────────────────────────────────

class SchedStepMachine(Base):
    __tablename__ = "sched_step_machines"
    __table_args__ = (
        UniqueConstraint("step_id", "resource_id", name="uq_step_machine"),
    )

    id          = Column(Integer, primary_key=True, index=True)
    step_id     = Column(Integer, ForeignKey("sched_steps.id", ondelete="CASCADE"), nullable=False)
    resource_id = Column(Integer, ForeignKey("sched_resources.id", ondelete="CASCADE"), nullable=False)

    step     = relationship("SchedStep",    back_populates="machine_links")
    resource = relationship("SchedResource", back_populates="machine_steps")


# ─── Step ↔ Helper (M2M) ──────────────────────────────────────────────────────

class SchedStepHelper(Base):
    __tablename__ = "sched_step_helpers"
    __table_args__ = (
        UniqueConstraint("step_id", "resource_id", name="uq_step_helper"),
    )

    id          = Column(Integer, primary_key=True, index=True)
    step_id     = Column(Integer, ForeignKey("sched_steps.id", ondelete="CASCADE"), nullable=False)
    resource_id = Column(Integer, ForeignKey("sched_resources.id", ondelete="CASCADE"), nullable=False)

    step     = relationship("SchedStep",    back_populates="helper_links")
    resource = relationship("SchedResource", back_populates="helper_steps")
