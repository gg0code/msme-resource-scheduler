"""
models/employee.py — V1.1
Added tenant_id to Employee and EmployeeSkill.
"""

from sqlalchemy import Column, Integer, String, Float, Boolean, Date, DateTime, ForeignKey, Text
from sqlalchemy.orm import relationship
from datetime import datetime
from app.database import Base


class Employee(Base):
    __tablename__ = "employees"

    id                    = Column(Integer, primary_key=True, index=True)
    tenant_id             = Column(Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)  # V1.1
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
    created_at            = Column(DateTime, default=datetime.utcnow)
    updated_at            = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    skills                 = relationship("EmployeeSkill", back_populates="employee", cascade="all, delete-orphan")
    availability_overrides = relationship(
        "AvailabilityOverride", back_populates="employee",
        foreign_keys="AvailabilityOverride.employee_id", cascade="all, delete-orphan",
    )
    assignments = relationship("JobAssignment", back_populates="employee")


class EmployeeSkill(Base):
    __tablename__ = "employee_skills"

    id          = Column(Integer, primary_key=True, index=True)
    tenant_id   = Column(Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)  # V1.1
    employee_id = Column(Integer, ForeignKey("employees.id", ondelete="CASCADE"), nullable=False)
    skill_id    = Column(Integer, ForeignKey("skills.id", ondelete="CASCADE"), nullable=False)
    skill_level = Column(String(20), nullable=False, default="Generic")

    employee = relationship("Employee", back_populates="skills")
    skill    = relationship("Skill", back_populates="employee_skills")
