"""
```python
"""
backend/app/models/employee.py — Employee and EmployeeSkill SQLAlchemy ORM Models

FILE PURPOSE
This file defines the SQLAlchemy ORM models for employees and their skills within the ZetaOps Copilot 
workforce scheduling system. It was introduced in the original v4.0 release and updated to v1.1 to add 
tenant_id fields for multi-tenant security. These models sit at the core of the scheduling engine, 
representing the human workforce that gets assigned to manufacturing jobs, and are used by both the 
scheduler engine and availability checking services.

WHAT THIS FILE DOES — step by step
1. Imports SQLAlchemy column types, relationship functions, datetime utilities, and the Base class from app.database
2. Defines the Employee class inheriting from Base, representing individual workers in the system
3. Sets up the employees table schema with 15 columns covering personal info, employment details, and scheduling metadata
4. Establishes SQLAlchemy relationships to EmployeeSkill, AvailabilityOverride, and JobAssignment models
5. Defines the EmployeeSkill class as a junction table linking employees to their manufacturing skills
6. Sets up the employee_skills table schema with foreign keys to employees, skills, and tenants
7. Establishes bidirectional relationships between Employee and EmployeeSkill models

KEY FUNCTIONS / CLASSES / COMPONENTS

Employee
Name         : Employee
Type         : SQLAlchemy ORM Model Class
Purpose      : Represents a worker/employee in the manufacturing workforce. Stores personal information, 
               employment details, base availability percentage, and hourly rates. The scheduler engine 
               uses this model to determine who can be assigned to jobs based on skills and availability.
Parameters   : None (ORM model, instantiated with keyword arguments for column values)
Returns      : Employee instance when created via SQLAlchemy session
Calls        : None (data model only)
DB/API       : Maps to 'employees' database table with CASCADE delete from tenant
Side effects : None (read-only model definition)

EmployeeSkill
Name         : EmployeeSkill
Type         : SQLAlchemy ORM Model Class  
Purpose      : Junction table linking employees to their manufacturing skills (welding, printing, etc.) 
               with proficiency levels. The scheduler uses this to match employee capabilities to job 
               step requirements, surfacing skill gaps as amber warnings when employees lack required skills.
Parameters   : None (ORM model, instantiated with keyword arguments for column values)
Returns      : EmployeeSkill instance when created via SQLAlchemy session
Calls        : None (data model only)
DB/API       : Maps to 'employee_skills' database table with CASCADE delete from tenant, employee, and skill
Side effects : None (read-only model definition)

WHO CALLS THIS FILE
- backend/app/crud/employee_crud.py — performs database queries on Employee and EmployeeSkill models
- backend/app/routers/employee_router.py — imports Employee model for FastAPI endpoint type hints
- backend/app/services/availability_engine.py — queries Employee model to check workforce availability
- backend/app/scheduler/engine.py — reads Employee and EmployeeSkill data for job assignment calculations
- backend/app/routers/scheduler_router.py — loads Employee data before calling the scheduling engine
- backend/alembic/versions/*.py — migration files reference these models for schema changes

IMPORTS EXPLAINED
- sqlalchemy Column, Integer, String, Float, Boolean, Date, DateTime, ForeignKey, Text — SQLAlchemy column type definitions needed to define the database schema for employee and skill tables
- sqlalchemy.orm relationship — defines bidirectional relationships between Employee/EmployeeSkill and related models like JobAssignment and AvailabilityOverride  
- datetime datetime, timezone — Python datetime utilities used in default values for created_at and updated_at timestamp columns
- app.database Base — the SQLAlchemy declarative base class that all ORM models must inherit from to be recognized by the database session

INTERN NOTES
- Easiest thing to break: Forgetting tenant_id in queries — every Employee/EmployeeSkill query MUST filter by tenant_id or you'll leak data between customers, violating design principle #2
- Non-obvious design decision: base_availability_pct defaults to 100.0 instead of null because the scheduler engine expects a numeric value and treats null as zero availability, breaking assignments
- Most common mistake: Modifying skill_level values without checking the frontend — the React UI has hardcoded dropdowns expecting "Generic", "Basic", "Intermediate", "Advanced" 
- Design principle implemented: #2 (tenant scoping) — both models have tenant_id with CASCADE delete and indexed foreign keys for security and performance
- What to check if behaving unexpectedly: Verify the skills relationship is loading correctly with lazy="select" — if you see N+1 queries, the relationship might need eager loading in specific CRUD operations
- v4-dev specific: This is production-stable code — any schema changes require Alembic migrations and must be tested against existing tenant data before deploying
"""
```
"""

from sqlalchemy import Column, Integer, String, Float, Boolean, Date, DateTime, ForeignKey, Text
from sqlalchemy.orm import relationship
from datetime import datetime, timezone
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
    created_at            = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at            = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    skills                 = relationship("EmployeeSkill", back_populates="employee", cascade="all, delete-orphan", lazy="select")
    availability_overrides = relationship(
        "AvailabilityOverride", back_populates="employee",
        foreign_keys="AvailabilityOverride.employee_id", cascade="all, delete-orphan",
    )
    assignments = relationship("JobAssignment", back_populates="employee", lazy="select")


class EmployeeSkill(Base):
    __tablename__ = "employee_skills"

    id          = Column(Integer, primary_key=True, index=True)
    tenant_id   = Column(Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)  # V1.1
    employee_id = Column(Integer, ForeignKey("employees.id", ondelete="CASCADE"), nullable=False)
    skill_id    = Column(Integer, ForeignKey("skills.id", ondelete="CASCADE"), nullable=False)
    skill_level = Column(String(20), nullable=False, default="Generic")

    employee = relationship("Employee", back_populates="skills")
    skill    = relationship("Skill", back_populates="employee_skills")
