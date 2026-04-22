# models/employee.py - Version 1.2
# Branch: both
#
# FILE PURPOSE
# SQLAlchemy ORM model for employees and their skills.
#
# WHO CALLS THIS FILE
#   app/routers/employees.py        - CRUD operations
#   app/routers/assignments.py      - JobAssignment relationship
#   app/services/whatsapp_intent.py - employee name lookup for absent intent
#   app/services/whatsapp_alerts.py - employee headcount for morning briefing
#   alembic/versions/               - schema migrations
#
# WHAT THIS FILE CALLS
#   app/database.py - Base
#
# KEY DESIGN DECISIONS
#   - source field (v5.16): tracks how the record entered the system.
#     Values: 'manual' (Day 1 table UI), 'whatsapp' (captured via conversation),
#     'erp_sync' (v7.0 ERP connector). NEVER remove this column - it is the
#     structural decision that keeps v7.0 ERP connector a sprint not a rewrite.
#   - worker_type field (v5.16): 'permanent' | 'contractor'. Used by v7.2
#     Contractor Labour Layer for availability pool queries.
#   - datetime.utcnow() is deprecated in Python 3.12+ but changing it requires
#     a dedicated migration. Deferred to a cleanup migration.

from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, Date, Float, ForeignKey, Integer, String
from sqlalchemy.orm import relationship

from app.database import Base

# ---------------------------------------------------------------------------
# VALID VALUES for constrained string columns
# Imported by schemas to keep validation in sync with the model.
# ---------------------------------------------------------------------------
VALID_SOURCE_VALUES:      tuple[str, ...] = ("manual", "whatsapp", "erp_sync")
VALID_WORKER_TYPE_VALUES: tuple[str, ...] = ("permanent", "contractor")


class Employee(Base):
    """
    Represents a worker in a tenant's factory.

    Called by:   app/routers/employees.py for all CRUD operations.
    Calls:       EmployeeSkill, AvailabilityOverride, JobAssignment relationships.
    Side effects: None - ORM model only.
    """

    __tablename__ = "employees"

    id                    = Column(Integer, primary_key=True, index=True)
    tenant_id             = Column(Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    full_name             = Column(String(150), nullable=False)
    gender                = Column(String(20), nullable=True)
    date_of_birth         = Column(Date, nullable=True)
    contact_number        = Column(String(20), nullable=True)
    department            = Column(String(100), nullable=True)
    employment_type       = Column(String(20), nullable=False, default="Full-time")
    base_availability_pct = Column(Float, nullable=False, default=100.0)
    join_date             = Column(Date, nullable=True)
    status                = Column(String(20), nullable=False, default="Active")
    hourly_rate           = Column(Float, nullable=True)
    overtime_rate         = Column(Float, nullable=True)

    # v5.16 - source field: how this record entered the system
    # server_default='manual' set in migration 023
    # Valid values: VALID_SOURCE_VALUES
    source                = Column(String(20), nullable=False, default="manual")

    # v5.16 - worker_type: permanent (monthly) or contractor (daily rate)
    # server_default='permanent' set in migration 023
    # Valid values: VALID_WORKER_TYPE_VALUES
    worker_type           = Column(String(20), nullable=False, default="permanent")

    created_at            = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at            = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    skills                 = relationship("EmployeeSkill", back_populates="employee", cascade="all, delete-orphan")
    availability_overrides = relationship(
        "AvailabilityOverride", back_populates="employee",
        foreign_keys="AvailabilityOverride.employee_id", cascade="all, delete-orphan",
    )
    assignments = relationship("JobAssignment", back_populates="employee")


class EmployeeSkill(Base):
    """
    Many-to-many link between Employee and Skill with a skill_level attribute.

    Called by:   app/routers/employees.py for skill assignment.
    Side effects: None - ORM model only.
    """

    __tablename__ = "employee_skills"

    id          = Column(Integer, primary_key=True, index=True)
    tenant_id   = Column(Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    employee_id = Column(Integer, ForeignKey("employees.id", ondelete="CASCADE"), nullable=False)
    skill_id    = Column(Integer, ForeignKey("skills.id", ondelete="CASCADE"), nullable=False)
    skill_level = Column(String(20), nullable=False, default="Generic")

    employee = relationship("Employee", back_populates="skills")
    skill    = relationship("Skill", back_populates="employee_skills")
