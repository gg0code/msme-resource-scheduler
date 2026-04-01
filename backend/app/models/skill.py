"""
models/skill.py — V1.1
Added tenant_id to Skill.
"""

from sqlalchemy import Column, Integer, String, Boolean, Text, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from datetime import datetime, timezone
from app.database import Base


class Skill(Base):
    __tablename__ = "skills"

    id          = Column(Integer, primary_key=True, index=True)
    tenant_id   = Column(Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)  # V1.1
    name        = Column(String(100), nullable=False)
    category    = Column(String(20), nullable=False)
    is_premium       = Column(Boolean, default=False, nullable=False)
    is_generic_role  = Column(Boolean, default=False, nullable=False, server_default='false')
    description = Column(Text, nullable=True)
    is_active   = Column(Boolean, default=True, nullable=False)
    created_at  = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at  = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    employee_skills            = relationship("EmployeeSkill", back_populates="skill")
    machine_skill_requirements = relationship("MachineSkillRequirement", back_populates="skill")
    job_skill_requirements     = relationship("JobSkillRequirement", back_populates="skill")
