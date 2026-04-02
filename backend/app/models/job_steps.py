"""
```python
"""
FILE PURPOSE
This file defines the SQLAlchemy ORM models for job steps and their associated resources in the ZetaOps Copilot scheduling system. Job steps represent individual phases or operations within a manufacturing job (like "Setup", "Print", "Cut", "Package"), allowing jobs to be broken down into smaller, trackable units of work. This file was introduced in the original v4 architecture and updated in "Block 2" to add the started_at timestamp column for better step execution tracking. These models sit in the data layer and are used by the scheduler engine, availability service, and various routers to manage step-by-step job execution.

WHAT THIS FILE DOES — step by step
1. Imports SQLAlchemy column types, relationship functions, and datetime utilities for timestamp handling
2. Imports the Base class from app.database to create proper ORM table mappings
3. Defines the JobStep class representing individual steps within a job, with fields for sequencing, timing, status tracking, and resource usage preferences
4. Sets up foreign key relationships to jobs and tenants tables with CASCADE delete behavior
5. Includes timestamp fields (started_at, created_at, updated_at) for tracking step lifecycle events
6. Defines the StepResource class for associating specific resources (machines, employees, materials) with individual job steps
7. Establishes bidirectional relationships between JobStep and StepResource using SQLAlchemy's relationship() function

KEY FUNCTIONS / CLASSES / COMPONENTS

Name         : JobStep
Type         : SQLAlchemy ORM class
Purpose      : Represents a single step or phase within a manufacturing job, such as "Setup Machine", "Run Production", or "Quality Check". Each step has its own duration, status, and can optionally have its own resource requirements separate from the parent job. Steps are executed in sequence_no order and can be tracked individually for progress monitoring and time recording.
Parameters   : N/A (ORM model)
Returns      : N/A (ORM model)
Calls        : None (data model only)
DB/API       : Maps to job_steps table in PostgreSQL
Side effects : When created/updated, automatically sets created_at/updated_at timestamps; when deleted, cascades to delete associated StepResource records

Name         : JobStep.id
Type         : SQLAlchemy Column (Integer, Primary Key)
Purpose      : Unique identifier for each job step across the entire system
Parameters   : N/A (column definition)
Returns      : N/A (column definition)
Calls        : None
DB/API       : Primary key with database index for fast lookups
Side effects : None

Name         : JobStep.job_id
Type         : SQLAlchemy Column (Integer, Foreign Key)
Purpose      : Links this step to its parent job in the jobs table. Uses CASCADE delete so when a job is deleted, all its steps are automatically removed.
Parameters   : N/A (column definition)
Returns      : N/A (column definition)
Calls        : None
DB/API       : Foreign key to jobs.id with CASCADE delete and database index
Side effects : Deletion of parent job will delete this step

Name         : JobStep.tenant_id
Type         : SQLAlchemy Column (Integer, Foreign Key)
Purpose      : Implements tenant isolation security (Design Principle #2). Every job step belongs to exactly one tenant, preventing cross-tenant data access.
Parameters   : N/A (column definition)
Returns      : N/A (column definition)
Calls        : None
DB/API       : Foreign key to tenants.id with CASCADE delete and database index
Side effects : Must be included in all queries to maintain tenant security

Name         : JobStep.sequence_no
Type         : SQLAlchemy Column (Integer)
Purpose      : Defines the execution order of steps within a job. Step 1 runs before step 2, etc. The scheduler uses this to determine which steps can be started based on completion of prerequisite steps.
Parameters   : N/A (column definition)
Returns      : N/A (column definition)
Calls        : None
DB/API       : Integer field, not nullable
Side effects : None

Name         : JobStep.name
Type         : SQLAlchemy Column (String, 200 chars)
Purpose      : Human-readable name for the step like "Setup Press", "Print Run", "Quality Check". Displayed in the UI and used in AI narration.
Parameters   : N/A (column definition)
Returns      : N/A (column definition)
Calls        : None
DB/API       : String field with 200 character limit
Side effects : None

Name         : JobStep.step_type
Type         : SQLAlchemy Column (String, 20 chars)
Purpose      : Categorizes the type of work being performed (e.g., "production", "setup", "quality", "maintenance"). Defaults to "production" for standard manufacturing steps.
Parameters   : N/A (column definition)
Returns      : N/A (column definition)
Calls        : None
DB/API       : String field with default value "production"
Side effects : None

Name         : JobStep.duration_minutes
Type         : SQLAlchemy Column (Integer)
Purpose      : Estimated time in minutes for this step to complete. Used by the scheduler engine for resource allocation and timeline planning. Defaults to 60 minutes if not specified.
Parameters   : N/A (column definition)
Returns      : N/A (column definition)
Calls        : None
DB/API       : Integer field with default value 60
Side effects : None

Name         : JobStep.status
Type         : SQLAlchemy Column (String, 20 chars)
Purpose      : Tracks the current state of step execution. Typical values include "locked" (cannot start yet), "ready" (prerequisites met), "in_progress" (currently executing), "completed", "on_hold". Defaults to "locked".
Parameters   : N/A (column definition)
Returns      : N/A (column definition)
Calls        : None
DB/API       : String field with default value "locked"
Side effects : When status changes to "in_progress", started_at timestamp should be set

Name         : JobStep.notes
Type         : SQLAlchemy Column (Text)
Purpose      : Optional free-form text field for additional instructions, comments, or observations about this step. Can be updated by workers during execution.
Parameters   : N/A (column definition)
Returns      : N/A (column definition)
Calls        : None
DB/API       : Text field, nullable
Side effects : None

Name         : JobStep.use_job_resources
Type         : SQLAlchemy Column (Boolean)
Purpose      : Flag indicating whether this step should inherit resource assignments from its parent job (True) or use its own step-specific resources from the StepResource table (False). Defaults to True for simpler job management.
Parameters   : N/A (column definition)
Returns      : N/A (column definition)
Calls        : None
DB/API       : Boolean field with default value True
Side effects : Affects which resources the scheduler uses for this step

Name         : JobStep.started_at
Type         : SQLAlchemy Column (DateTime)
Purpose      : Timestamp recording when this step began execution (when status changed to "in_progress"). Added in Block 2 update for better time tracking and performance analysis. Nullable because steps start as "locked".
Parameters   : N/A (column definition)
Returns      : N/A (column definition)
Calls        : None
DB/API       : DateTime field, nullable
Side effects : Should be set automatically when status transitions to "in_progress"

Name         : JobStep.created_at
Type         : SQLAlchemy Column (DateTime)
Purpose      : Timestamp when this step record was first created in the database. Uses UTC timezone for consistency across deployments.
"""

from sqlalchemy import Column, Integer, String, Float, Boolean, ForeignKey, Text, DateTime
from sqlalchemy.orm import relationship
from datetime import datetime, timezone
from app.database import Base


class JobStep(Base):
    __tablename__ = "job_steps"

    id               = Column(Integer, primary_key=True, index=True)
    job_id           = Column(Integer, ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False, index=True)
    tenant_id        = Column(Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    sequence_no      = Column(Integer, nullable=False)
    name             = Column(String(200), nullable=False)
    step_type        = Column(String(20), nullable=False, default="production")
    duration_minutes = Column(Integer, nullable=False, default=60)
    status           = Column(String(20), nullable=False, default="locked")
    notes            = Column(Text, nullable=True)
    use_job_resources = Column(Boolean, nullable=False, default=True)

    started_at  = Column(DateTime, nullable=True)   # set when in_progress (Block 2)
    created_at  = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at  = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    resources = relationship("StepResource", back_populates="step", cascade="all, delete-orphan", lazy="select")


class StepResource(Base):
    __tablename__ = "step_resources"

    id            = Column(Integer, primary_key=True, index=True)
    step_id       = Column(Integer, ForeignKey("job_steps.id", ondelete="CASCADE"), nullable=False, index=True)
    tenant_id     = Column(Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    resource_type = Column(String(20), nullable=False)
    resource_id   = Column(Integer, nullable=True)
    quantity      = Column(Float, nullable=True)
    unit_cost     = Column(Float, nullable=True)
    notes         = Column(Text, nullable=True)

    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    step = relationship("JobStep", back_populates="resources")
