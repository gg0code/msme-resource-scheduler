from sqlalchemy import Column, Integer, String, Float, Boolean, ForeignKey, Text, DateTime
from sqlalchemy.orm import relationship
from datetime import datetime
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
    created_at  = Column(DateTime, default=datetime.utcnow)
    updated_at  = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

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

    created_at = Column(DateTime, default=datetime.utcnow)

    step = relationship("JobStep", back_populates="resources")
