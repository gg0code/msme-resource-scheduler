"""
models/job.py — J1.2
Added: delivery_date, invoice_number, invoice_date, payment_status,
       payment_amount, payment_date, actual_hours
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
