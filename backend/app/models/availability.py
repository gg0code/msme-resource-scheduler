"""
```python
"""
backend/app/models/availability.py — V1.1

FILE PURPOSE
This file defines the SQLAlchemy ORM model for availability overrides in the ZetaOps Copilot
scheduling system. It exists to handle temporary changes to employee and machine availability
that deviate from their base availability percentages. This model was introduced in the early
versions of the system and enhanced to V1.1 to add tenant_id for proper multi-tenancy support.
It sits in the data layer of the architecture, providing the database schema definition for
availability exceptions that the scheduling engine must consider when allocating resources.

WHAT THIS FILE DOES — step by step
1. Imports SQLAlchemy column types and relationship functions for ORM model definition
2. Imports datetime utilities for timezone-aware timestamp creation
3. Imports the Base class from the database module to inherit SQLAlchemy declarative base
4. Defines the AvailabilityOverride class that inherits from Base
5. Maps the class to the "availability_overrides" database table
6. Defines all database columns with proper types, constraints, and foreign key relationships
7. Sets up SQLAlchemy relationships to Employee and Machine models for easy data traversal
8. Provides automatic timestamp creation for tracking when overrides were created

KEY FUNCTIONS / CLASSES / COMPONENTS

Name         : AvailabilityOverride
Type         : SQLAlchemy ORM model class
Purpose      : Represents temporary availability changes for employees or machines during specific 
               date ranges. This allows the system to handle scenarios like employee vacations, 
               machine maintenance downtime, reduced capacity periods, or temporary unavailability.
               The model supports both complete unavailability (0%) and partial availability overrides.
Parameters   : None (this is a data model class, not a callable function)
Returns      : N/A (ORM model instances are created by SQLAlchemy)
Calls        : None directly (SQLAlchemy handles all database operations)
DB/API       : This model maps to the availability_overrides table in PostgreSQL
Side effects : When instances are created/modified, they automatically get timestamps and 
               are persisted to the database when the session is committed

WHO CALLS THIS FILE
- backend/app/services/availability_engine.py (imports this model to query availability overrides)
- backend/app/crud/availability.py (if it exists, would use this model for database operations)
- backend/app/routers/availability_router.py (if it exists, would use this for API endpoints)
- backend/alembic/versions/*.py (migration files reference this model for schema changes)
- Any other service or router that needs to check or modify resource availability

IMPORTS EXPLAINED
- sqlalchemy.Column, Integer, Float, Date, DateTime, ForeignKey, Text: SQLAlchemy column types 
  and constraints needed to define the database table structure with proper data types
- sqlalchemy.orm.relationship: Creates navigable relationships between this model and related 
  Employee/Machine models for easier data access without manual joins
- datetime.datetime, timezone: Provides timezone-aware datetime creation for the created_at 
  field to ensure consistent timestamps across different server timezones
- app.database.Base: The SQLAlchemy declarative base class that all ORM models must inherit 
  from to be recognized by the database session and migration system

INTERN NOTES
- Easiest thing to break: Forgetting to set tenant_id when creating availability overrides, 
  which violates design principle #2 and creates a security vulnerability where overrides 
  could leak between tenants
- Non-obvious design decision: Both employee_id and machine_id are nullable because an override 
  applies to exactly one resource type, never both - this allows the same table to handle 
  availability for different resource types efficiently
- Most common mistake: Setting date ranges incorrectly where date_to is before date_from, or 
  setting availability_pct outside the 0.0-100.0 range without proper validation
- Design principle implemented: #2 (Tenant scoping on ALL DB queries) - the tenant_id field 
  with CASCADE delete ensures proper data isolation and cleanup
- What to check if behaving unexpectedly: Verify the date ranges don't overlap in conflicting 
  ways, check that exactly one of employee_id or machine_id is set (not both or neither), 
  and confirm availability_pct values are reasonable percentages
- V4-dev specific: This model is stable and any changes should maintain backward compatibility 
  with existing availability override data in production databases
"""
```
"""

from sqlalchemy import Column, Integer, Float, Date, DateTime, ForeignKey, Text
from sqlalchemy.orm import relationship
from datetime import datetime, timezone
from app.database import Base


class AvailabilityOverride(Base):
    __tablename__ = "availability_overrides"

    id               = Column(Integer, primary_key=True, index=True)
    tenant_id        = Column(Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)  # V1.1
    employee_id      = Column(Integer, ForeignKey("employees.id", ondelete="CASCADE"), nullable=True)
    machine_id       = Column(Integer, ForeignKey("machines.id", ondelete="CASCADE"), nullable=True)
    date_from        = Column(Date, nullable=False)
    date_to          = Column(Date, nullable=False)
    availability_pct = Column(Float, nullable=False, default=0.0)
    reason           = Column(Text, nullable=True)
    created_at       = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    employee = relationship("Employee", back_populates="availability_overrides", foreign_keys=[employee_id])
    machine  = relationship("Machine",  back_populates="availability_overrides", foreign_keys=[machine_id])
