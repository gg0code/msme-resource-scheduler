"""
app/models/scheduling.py  — Prompt 1 (Step-based scheduling engine)

New tables (prefixed sched_* to avoid collision with existing job/machine tables):
  sched_resources   — machines and helpers
  sched_jobs        — scheduling jobs (distinct from existing Job)
  sched_steps       — ordered steps within a job
  sched_step_machines — M2M: step ↔ machine resources
  sched_step_helpers  — M2M: step ↔ helper resources
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
