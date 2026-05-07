"""
models/skill.py — V1.2
Added tenant_id to Skill (V1.1).
v6.3.17: added source provenance column (migration 032). The column
matches the Employee/Machine source field — see app/models/employee.py
VALID_SOURCE_VALUES for the shared vocabulary.
"""

from sqlalchemy import Column, Integer, String, Boolean, Text, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from datetime import datetime, timezone
from app.database import Base
from app.models.employee import VALID_SOURCE_VALUES  # shared constant


class Skill(Base):
    __tablename__ = "skills"

    id          = Column(Integer, primary_key=True, index=True)
    tenant_id   = Column(Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)  # V1.1
    name        = Column(String(100), nullable=False)
    category    = Column(String(20), nullable=False)
    is_premium  = Column(Boolean, default=False, nullable=False)
    description = Column(Text, nullable=True)
    is_active   = Column(Boolean, default=True, nullable=False)

    # v6.3.17 - source field: how this record entered the system.
    # server_default='manual' set in migration 032.
    # Valid values: VALID_SOURCE_VALUES (imported from models/employee.py)
    source      = Column(String(20), nullable=False, default="manual")

    created_at  = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at  = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    employee_skills            = relationship("EmployeeSkill", back_populates="skill")
    machine_skill_requirements = relationship("MachineSkillRequirement", back_populates="skill")
    job_skill_requirements     = relationship("JobSkillRequirement", back_populates="skill")
