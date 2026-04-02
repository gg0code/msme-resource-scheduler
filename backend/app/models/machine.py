"""
models/machine.py — V1.1
Added tenant_id to Machine and MachineSkillRequirement.
"""

from sqlalchemy import Column, Integer, String, Float, Boolean, Date, DateTime, ForeignKey, Text
from sqlalchemy.orm import relationship
from datetime import datetime, timezone
from app.database import Base


class Machine(Base):
    __tablename__ = "machines"

    id                    = Column(Integer, primary_key=True, index=True)
    tenant_id             = Column(Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)  # V1.1
    name                  = Column(String(150), nullable=False)
    machine_type          = Column(String(100), nullable=True)
    base_availability_pct = Column(Float, nullable=False, default=100.0)
    location_bay          = Column(String(50), nullable=True)
    status                = Column(String(30), nullable=False, default="Operational")
    hourly_rate           = Column(Float, nullable=True)
    created_at            = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at            = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    skill_requirements     = relationship("MachineSkillRequirement", back_populates="machine", cascade="all, delete-orphan")
    availability_overrides = relationship(
        "AvailabilityOverride", back_populates="machine",
        foreign_keys="AvailabilityOverride.machine_id", cascade="all, delete-orphan",
    )
    assignments = relationship("JobAssignment", back_populates="machine", lazy="select")


class MachineSkillRequirement(Base):
    __tablename__ = "machine_skill_requirements"

    id                 = Column(Integer, primary_key=True, index=True)
    tenant_id          = Column(Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)  # V1.1
    machine_id         = Column(Integer, ForeignKey("machines.id", ondelete="CASCADE"), nullable=False)
    skill_id           = Column(Integer, ForeignKey("skills.id", ondelete="CASCADE"), nullable=False)
    min_skill_level    = Column(String(20), nullable=False, default="Generic")
    employees_required = Column(Integer, nullable=False, default=1)

    machine = relationship("Machine", back_populates="skill_requirements")
    skill   = relationship("Skill", back_populates="machine_skill_requirements")
