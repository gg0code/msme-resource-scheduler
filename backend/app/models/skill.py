"""
```python
"""
backend/app/models/skill.py

FILE PURPOSE
This file defines the Skill SQLAlchemy ORM model that represents individual skills
in the ZetaOps manufacturing workforce scheduling system. Skills are tenant-scoped
capabilities (like "Welding", "Machine Operation", "Quality Control") that employees
can possess and that jobs/machines can require. This model was introduced in v4-dev
and sits in the data layer, providing the foundation for skill-based scheduling
where the engine matches employee capabilities to job requirements.

WHAT THIS FILE DOES — step by step
1. Imports SQLAlchemy components for database table definition and relationships
2. Imports datetime utilities for timestamp management with UTC timezone
3. Imports the Base class from app.database for ORM inheritance
4. Defines the Skill class that inherits from SQLAlchemy Base
5. Sets the database table name as "skills"
6. Defines all column fields including tenant scoping, categorization, and metadata
7. Establishes foreign key relationship to tenants table with CASCADE delete
8. Creates SQLAlchemy relationships to three junction tables for skill associations
9. Sets up automatic timestamp tracking for creation and updates

KEY FUNCTIONS / CLASSES / COMPONENTS

Name         : Skill
Type         : SQLAlchemy ORM model class
Purpose      : Represents a single skill/capability in the system that can be assigned 
               to employees, required by jobs, or required by machines. Supports 
               categorization, premium features, and tenant isolation for multi-tenant 
               scheduling operations.
Parameters   : None (ORM model, not callable)
Returns      : ORM instances when queried through SQLAlchemy session
Calls        : No direct calls (declarative model)
DB/API       : Maps to "skills" database table, references "tenants" table via foreign key
Side effects : Database operations when instances are created/modified through SQLAlchemy

WHO CALLS THIS FILE
- backend/app/crud/skill.py (CRUD operations for skill management)
- backend/app/routers/skill_router.py (API endpoints for skill operations)
- backend/app/models/employee_skill.py (many-to-many employee-skill relationships)
- backend/app/models/machine_skill_requirement.py (machine skill prerequisites)
- backend/app/models/job_skill_requirement.py (job skill prerequisites)
- backend/app/scheduler/engine.py (skill matching during scheduling computation)
- backend/app/services/availability_engine.py (skill-based availability checks)
- backend/alembic/versions/*.py (database migration scripts)

IMPORTS EXPLAINED
- sqlalchemy.Column, Integer, String, Boolean, Text, DateTime, ForeignKey: Core SQLAlchemy types for defining database table columns with appropriate data types and constraints
- sqlalchemy.orm.relationship: Creates bidirectional relationships between this Skill model and related models through foreign keys
- datetime.datetime, timezone: Python standard library for handling UTC timestamps in created_at and updated_at fields
- app.database.Base: The declarative base class that all ORM models inherit from, configured with database connection settings

INTERN NOTES
- Easiest thing to break: Forgetting tenant_id in queries will cause cross-tenant data leakage and major security issues
- Non-obvious design decision: is_generic_role flag exists to distinguish between specific technical skills ("TIG Welding") and broad role categories ("Supervisor") for different scheduling logic
- Most common mistake: Not checking is_active flag when querying skills, which can assign deleted/inactive skills to jobs or employees
- Design principle implemented: #2 (Tenant scoping on ALL DB queries) - tenant_id foreign key with CASCADE delete ensures proper isolation
- What to check if behaving unexpectedly: Verify all CRUD operations filter by tenant_id, check that relationships properly cascade, and ensure UTC timezone is preserved in timestamps
- Not applicable (this is v4-dev stable code, not v5-whatsapp specific)
"""
```
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
