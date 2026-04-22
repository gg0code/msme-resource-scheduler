# models/machine.py - Version 1.2
# Branch: both
#
# FILE PURPOSE
# SQLAlchemy ORM model for machines and their skill requirements.
#
# WHO CALLS THIS FILE
#   app/routers/machines.py         - CRUD operations
#   app/routers/assignments.py      - JobAssignment relationship
#   app/services/whatsapp_alerts.py - machine count for morning briefing
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
#   - datetime.utcnow() is deprecated in Python 3.12+ but changing it requires
#     a dedicated migration. Deferred to a cleanup migration.

from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, Float, ForeignKey, Integer, String
from sqlalchemy.orm import relationship

from app.database import Base
from app.models.employee import VALID_SOURCE_VALUES  # shared constant

# Re-export so callers can import from either model file
__all__ = ["Machine", "MachineSkillRequirement", "VALID_SOURCE_VALUES"]


class Machine(Base):
    """
    Represents a machine or work centre in a tenant's factory.

    Called by:   app/routers/machines.py for all CRUD operations.
    Calls:       MachineSkillRequirement, AvailabilityOverride,
                 JobAssignment relationships.
    Side effects: None - ORM model only.
    """

    __tablename__ = "machines"

    id                    = Column(Integer, primary_key=True, index=True)
    tenant_id             = Column(Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    name                  = Column(String(150), nullable=False)
    machine_type          = Column(String(100), nullable=True)
    base_availability_pct = Column(Float, nullable=False, default=100.0)
    location_bay          = Column(String(50), nullable=True)
    status                = Column(String(30), nullable=False, default="Operational")
    hourly_rate           = Column(Float, nullable=True)

    # v5.16 - source field: how this record entered the system
    # server_default='manual' set in migration 023
    # Valid values: VALID_SOURCE_VALUES (imported from models/employee.py)
    source                = Column(String(20), nullable=False, default="manual")

    created_at            = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at            = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    skill_requirements     = relationship("MachineSkillRequirement", back_populates="machine", cascade="all, delete-orphan")
    availability_overrides = relationship(
        "AvailabilityOverride", back_populates="machine",
        foreign_keys="AvailabilityOverride.machine_id", cascade="all, delete-orphan",
    )
    assignments = relationship("JobAssignment", back_populates="machine")


class MachineSkillRequirement(Base):
    """
    Skill requirements for operating a machine.

    Called by:   app/routers/machines.py for skill requirement CRUD.
    Side effects: None - ORM model only.
    """

    __tablename__ = "machine_skill_requirements"

    id                 = Column(Integer, primary_key=True, index=True)
    tenant_id          = Column(Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    machine_id         = Column(Integer, ForeignKey("machines.id", ondelete="CASCADE"), nullable=False)
    skill_id           = Column(Integer, ForeignKey("skills.id", ondelete="CASCADE"), nullable=False)
    min_skill_level    = Column(String(20), nullable=False, default="Generic")
    employees_required = Column(Integer, nullable=False, default=1)

    machine = relationship("Machine", back_populates="skill_requirements")
    skill   = relationship("Skill", back_populates="machine_skill_requirements")
