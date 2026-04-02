"""
```python
"""
backend/app/models/machine.py

FILE PURPOSE
This file defines SQLAlchemy ORM models for machines and their skill requirements in the ZetaOps Copilot 
scheduling system. It exists to represent physical manufacturing equipment (printing presses, cutting 
machines, chemical reactors, etc.) that can be assigned to jobs. This file was introduced in the initial 
v1.0 release and updated to v1.1 to add tenant_id for multi-tenant isolation. It sits in the data layer 
of the architecture, providing the foundational database models that the scheduler engine uses to 
understand what machines are available and what skills they require to operate.

WHAT THIS FILE DOES — step by step
1. Imports SQLAlchemy components for defining database table structures and relationships
2. Imports datetime utilities for tracking creation and update timestamps
3. Imports the Base class from app.database to inherit SQLAlchemy declarative base functionality
4. Defines the Machine class representing physical manufacturing equipment with availability and location info
5. Sets up foreign key relationship to tenants table with CASCADE delete for tenant isolation
6. Defines columns for machine identification, type, availability percentage, location, and operational status
7. Establishes relationships to skill requirements, availability overrides, and job assignments
8. Defines the MachineSkillRequirement class for specifying what employee skills are needed to operate each machine
9. Creates many-to-many relationship structure between machines and skills with minimum skill level requirements
10. Sets up foreign key relationships with CASCADE delete to maintain referential integrity

KEY FUNCTIONS / CLASSES / COMPONENTS

Name         : Machine
Type         : SQLAlchemy ORM class
Purpose      : Represents a physical piece of manufacturing equipment that can be assigned to jobs. Stores 
               machine identification, type classification, base availability percentage, physical location, 
               operational status, and hourly cost rate. This is the core model the scheduler engine uses 
               to determine which machines can work on which jobs.
Parameters   : None (ORM model, instantiated with column values)
Returns      : Machine instance when created via SQLAlchemy session
Calls        : None (data model only)
DB/API       : Maps to "machines" database table with indexes on id and tenant_id
Side effects : None (passive data model)

Name         : MachineSkillRequirement
Type         : SQLAlchemy ORM class
Purpose      : Represents the skill requirements needed for employees to operate a specific machine. Links 
               machines to skills with minimum skill level and number of employees required. This allows 
               the scheduler to enforce that only qualified employees can be assigned to machine-based jobs.
Parameters   : None (ORM model, instantiated with column values)
Returns      : MachineSkillRequirement instance when created via SQLAlchemy session
Calls        : None (data model only)
DB/API       : Maps to "machine_skill_requirements" database table
Side effects : None (passive data model)

WHO CALLS THIS FILE
- backend/app/crud/machine.py - CRUD operations for machine management
- backend/app/routers/machine_router.py - FastAPI endpoints for machine API operations
- backend/app/scheduler/engine.py - Core scheduling engine reads machine data for job assignments
- backend/app/services/availability_engine.py - Checks machine availability for scheduling decisions
- backend/alembic/versions/*.py - Database migration files reference these models for schema changes

IMPORTS EXPLAINED
- sqlalchemy Column, Integer, String, Float, Boolean, Date, DateTime, ForeignKey, Text: SQLAlchemy column 
  types needed to define the database table structure and field constraints for machines and skill requirements
- sqlalchemy.orm relationship: Creates relationships between Machine and related models (skills, assignments, 
  availability overrides) for easy navigation in queries
- datetime datetime, timezone: Used for created_at and updated_at timestamp fields with UTC timezone awareness
- app.database Base: The SQLAlchemy declarative base class that all ORM models must inherit from to be 
  recognized as database tables

INTERN NOTES
- Easiest thing to break: Forgetting tenant_id when creating machines - this violates design principle #2 
  and creates a security vulnerability where machines could be accessed across tenant boundaries
- Non-obvious design decision: base_availability_pct is separate from status because a machine can be 
  "Operational" but only available 80% of the time due to maintenance schedules or shared usage
- Most common mistake: Not understanding that MachineSkillRequirement creates the bridge between machines 
  and the skills needed to operate them - deleting skill requirements breaks the scheduler's ability to 
  match qualified employees to machines
- Design principle implemented: #2 (Tenant scoping on ALL DB queries) - both models have tenant_id with 
  CASCADE delete to ensure complete tenant isolation
- What to check if behaving unexpectedly: Verify the relationships are loading correctly (skill_requirements, 
  assignments) and that availability_overrides aren't conflicting with base_availability_pct calculations
- v4-dev compatibility: This file is stable across branches - no WhatsApp-specific features, safe to merge 
  without modification
"""
```
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
