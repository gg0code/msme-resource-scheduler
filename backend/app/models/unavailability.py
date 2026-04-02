"""
```python
"""
FILE PURPOSE
This file defines SQLAlchemy ORM models for tracking unavailability periods of resources
in the ZetaOps Copilot scheduling system. It exists to record when employees are on leave
and when machines are down for maintenance, repairs, or other reasons that make them
unavailable for job scheduling. This file was introduced in the v4-dev branch and sits
in the data layer of the architecture, providing the database schema for unavailability
tracking that the scheduling engine uses to avoid assigning jobs to unavailable resources.

WHAT THIS FILE DOES — step by step
1. Imports SQLAlchemy column types and database utilities for defining ORM models
2. Imports the Base class from app.database to create SQLAlchemy table models
3. Defines EmployeeLeave model to track employee vacation, sick leave, and other absences
4. Defines MachineDowntime model to track machine maintenance, breakdowns, and repairs
5. Sets up proper foreign key relationships with CASCADE deletion to tenants and resources
6. Establishes database indexes on tenant_id and resource IDs for efficient querying
7. Provides created_at timestamps for audit trails of when unavailability was recorded

KEY FUNCTIONS / CLASSES / COMPONENTS

Name         : EmployeeLeave
Type         : SQLAlchemy ORM model class
Purpose      : Represents periods when an employee is unavailable for work assignments.
               This model stores leave records including vacation time, sick days, personal
               leave, or any other absence that should prevent the scheduling engine from
               assigning jobs to that employee during the specified date range.
Parameters   : No constructor parameters - uses SQLAlchemy column definitions
Returns      : Database table instance when queried
Calls        : No function calls - pure data model
DB/API       : Creates "employee_leaves" table in PostgreSQL database
Side effects : Table creation during Alembic migrations, cascading deletes when tenant/employee deleted

Name         : MachineDowntime
Type         : SQLAlchemy ORM model class
Purpose      : Represents periods when a machine is unavailable for production work.
               This model tracks maintenance windows, equipment failures, repairs, or
               planned downtime that should prevent the scheduling engine from assigning
               jobs to that machine during the specified date range.
Parameters   : No constructor parameters - uses SQLAlchemy column definitions
Returns      : Database table instance when queried
Calls        : No function calls - pure data model
DB/API       : Creates "machine_downtimes" table in PostgreSQL database
Side effects : Table creation during Alembic migrations, cascading deletes when tenant/machine deleted

WHO CALLS THIS FILE
- backend/app/crud/unavailability.py (CRUD operations for leave and downtime records)
- backend/app/services/availability_engine.py (checks unavailability when calculating resource availability)
- backend/app/routers/employees.py (employee leave management endpoints)
- backend/app/routers/machines.py (machine downtime tracking endpoints)
- backend/app/scheduler/engine.py (scheduler engine queries unavailability to avoid conflicts)
- backend/alembic/versions/*.py (database migration files that create these tables)

IMPORTS EXPLAINED
- sqlalchemy Column, Integer, String, Date, DateTime: SQLAlchemy column types for defining table schema with proper data types
- sqlalchemy ForeignKey: Creates foreign key relationships to tenants, employees, and machines tables with CASCADE deletion
- sqlalchemy Text: Text column type for longer reason descriptions (though currently using String(255))
- sqlalchemy.sql func: Provides database function access, specifically func.now() for automatic timestamp creation
- app.database Base: The declarative base class that all ORM models inherit from to become database tables

INTERN NOTES
- Easiest thing to break: Forgetting tenant_id foreign key constraint when querying - this violates design principle #2 and creates security bugs where tenants could see other tenants' unavailability data
- Non-obvious design decision: Uses Date columns instead of DateTime for start/end dates because unavailability is typically tracked in full-day increments, not specific hours, which simplifies scheduling logic
- Most common mistake: Not handling date range overlaps when creating new unavailability records - the application layer must validate that new records don't conflict with existing ones inappropriately
- Design principle implemented: Principle #2 (tenant scoping) - both models include tenant_id with proper indexing and CASCADE deletion to ensure complete tenant data isolation
- What to check if behaving unexpectedly: Verify that the availability_engine.py is properly querying these tables when calculating resource availability, and check that date ranges are inclusive/exclusive as expected by the scheduling engine
- This is v4-dev stable code: When merging v5-whatsapp changes, ensure any new WhatsApp-triggered leave requests properly validate against existing unavailability periods before creation
"""
```
"""

# app/models/unavailability.py
from sqlalchemy import Column, Integer, String, Date, DateTime, ForeignKey, Text
from sqlalchemy.sql import func
from app.database import Base

class EmployeeLeave(Base):
    __tablename__ = "employee_leaves"

    id          = Column(Integer, primary_key=True, index=True)
    tenant_id   = Column(Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    employee_id = Column(Integer, ForeignKey("employees.id", ondelete="CASCADE"), nullable=False, index=True)
    start_date  = Column(Date, nullable=False)
    end_date    = Column(Date, nullable=False)
    reason      = Column(String(255), nullable=True)
    created_at  = Column(DateTime(timezone=True), server_default=func.now())


class MachineDowntime(Base):
    __tablename__ = "machine_downtimes"

    id         = Column(Integer, primary_key=True, index=True)
    tenant_id  = Column(Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    machine_id = Column(Integer, ForeignKey("machines.id", ondelete="CASCADE"), nullable=False, index=True)
    start_date = Column(Date, nullable=False)
    end_date   = Column(Date, nullable=False)
    reason     = Column(String(255), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
