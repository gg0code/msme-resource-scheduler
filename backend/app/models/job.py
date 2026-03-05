"""
models/job.py — V1.1
Added tenant_id to Job, JobSkillRequirement, JobAssignment.
"""

from sqlalchemy import Column, Integer, String, Float, Date, DateTime, ForeignKey, Text, JSON
from sqlalchemy.orm import relationship
from datetime import datetime
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
    timer_log       = Column(JSON, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

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
    assigned_at = Column(DateTime, default=datetime.utcnow)

    job      = relationship("Job", back_populates="assignments")
    employee = relationship("Employee", back_populates="assignments")
    machine  = relationship("Machine", back_populates="assignments")
