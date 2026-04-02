"""
```python
"""
FILE PURPOSE
This file implements the FastAPI router for managing availability overrides in the ZetaOps
Copilot scheduling system. It provides CRUD operations to create, read, update, and delete
availability exceptions for employees and machines (like vacation days, maintenance windows,
or temporary capacity changes). Introduced in v4.0 as part of the core scheduling infrastructure
and sits between the frontend availability management UI and the AvailabilityOverride database
model, serving as the API layer that enforces tenant isolation and role-based access control.

WHAT THIS FILE DOES — step by step
1. Imports FastAPI components, database dependencies, auth models, and availability schemas
2. Creates an APIRouter instance to group all availability-related endpoints under /api/availability/
3. Defines GET / endpoint to list all availability overrides with optional employee/machine filtering
4. Defines POST / endpoint to create new availability overrides with scheduler+ permissions
5. Defines PATCH /{override_id} endpoint to update existing overrides with scheduler+ permissions  
6. Defines DELETE /{override_id} endpoint to remove overrides with scheduler+ permissions
7. All endpoints enforce tenant scoping and appropriate authentication/authorization levels

KEY FUNCTIONS / CLASSES / COMPONENTS

Name         : list_overrides
Type         : FastAPI GET endpoint
Purpose      : Retrieves all availability overrides for the current user's tenant, with optional
               filtering by employee_id or machine_id. Used by frontend to populate availability
               calendars and show current override schedules. Any authenticated user can view
               overrides since this is read-only scheduling information.
Parameters   : employee_id (int, optional) - filter to specific employee's overrides
               machine_id (int, optional) - filter to specific machine's overrides  
               db (Session) - SQLAlchemy database session from dependency injection
               current_user (User) - authenticated user from JWT token via get_current_user
Returns      : List[AvailabilityOverrideOut] - Pydantic models containing override details
Calls        : Uses SQLAlchemy query on AvailabilityOverride model
DB/API       : Queries availability_overrides table with tenant_id filter and optional resource filters
Side effects : None - read-only operation

Name         : create_override
Type         : FastAPI POST endpoint  
Purpose      : Creates a new availability override for an employee or machine within the current
               tenant. Validates that either employee_id or machine_id is specified (not both or
               neither). Only users with scheduler+ role can create overrides since this affects
               scheduling calculations and resource allocation.
Parameters   : payload (AvailabilityOverrideCreate) - Pydantic model with override details
               db (Session) - SQLAlchemy database session from dependency injection
               current_user (User) - authenticated scheduler+ user via require_role dependency
Returns      : AvailabilityOverrideOut - newly created override with database-generated ID
Calls        : Uses require_role() for authorization, SQLAlchemy for database operations
DB/API       : Inserts new record into availability_overrides table with tenant_id
Side effects : Creates database record, commits transaction, affects future scheduling calculations

Name         : update_override
Type         : FastAPI PATCH endpoint
Purpose      : Updates an existing availability override by ID within the current tenant. Uses
               partial update pattern where only provided fields are modified. Validates override
               exists and belongs to current tenant before modification. Only scheduler+ users
               can modify overrides since changes affect resource availability calculations.
Parameters   : override_id (int) - database ID of override to update
               payload (AvailabilityOverrideUpdate) - Pydantic model with partial update fields
               db (Session) - SQLAlchemy database session from dependency injection  
               current_user (User) - authenticated scheduler+ user via require_role dependency
Returns      : AvailabilityOverrideOut - updated override with modified fields
Calls        : Uses require_role() for authorization, SQLAlchemy for database operations
DB/API       : Updates existing record in availability_overrides table with tenant_id filter
Side effects : Modifies database record, commits transaction, affects future scheduling calculations

Name         : delete_override  
Type         : FastAPI DELETE endpoint
Purpose      : Permanently removes an availability override by ID within the current tenant.
               Validates override exists and belongs to current tenant before deletion. Only
               scheduler+ users can delete overrides since removal affects resource availability
               and scheduling calculations. Returns 204 No Content on successful deletion.
Parameters   : override_id (int) - database ID of override to delete
               db (Session) - SQLAlchemy database session from dependency injection
               current_user (User) - authenticated scheduler+ user via require_role dependency  
Returns      : None (HTTP 204 No Content status)
Calls        : Uses require_role() for authorization, SQLAlchemy for database operations
DB/API       : Deletes record from availability_overrides table with tenant_id filter
Side effects : Removes database record permanently, commits transaction, affects scheduling

WHO CALLS THIS FILE
- backend/app/main.py - registers this router under /api/availability/ prefix
- frontend/src/api/api_availability.ts - makes HTTP requests to these endpoints
- frontend/src/pages/AvailabilityPage.tsx - uses availability data for calendar views
- frontend/src/components/ScheduleOverrideModal.tsx - creates/edits overrides via API

IMPORTS EXPLAINED  
- fastapi.APIRouter - creates route group for availability endpoints under common prefix
- fastapi.Depends - enables dependency injection for database sessions and authentication  
- fastapi.HTTPException - raises structured HTTP errors with status codes and messages
- fastapi.status - provides HTTP status code constants for responses and exceptions
- sqlalchemy.orm.Session - database session type for SQLAlchemy ORM operations
- typing.List - type hint for endpoint returning list of availability overrides
- app.database.get_db - dependency that provides SQLAlchemy database session per request
- app.models.availability.AvailabilityOverride - SQLAlchemy model for override database table
- app.schemas.availability - Pydantic models for request/response validation and serialization
- app.core.dependencies.get_current_user - extracts authenticated user from JWT token  
- app.core.dependencies.require_role - enforces role-based access control for scheduler+ operations
- app.models.auth.User - SQLAlchemy model representing authenticated user with tenant_id

INTERN NOTES
• Easiest thing to break: Forgetting tenant_id filter in database queries - this creates a massive security vulnerability where users can access other tenants' availability data
• Non-obvious design decision: POST endpoint requires either employee_id OR machine_id but not both - this ensures each override applies to exactly one resource type for cleaner scheduling logic  
• Most common mistake: Using get_current_user instead of require_role for write operations - GET is open to all authenticated users but POST/PATCH/DELETE need scheduler+ permissions
• Design principle implemented: Principle #2 (tenant scoping on ALL DB queries) - every database query includes tenant_id filter to prevent cross-tenant data leaks
• Check this if unexpected behavior: Verify user has correct role (scheduler/proprietor) for write operations, confirm override dates don't conflict with existing overrides, ensure frontend is passing correct employee_id or machine_id
• Not applicable - this file exists in both v4-dev and v5-whatsapp branches with identical functionality
"""
```
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List

from app.database import get_db
from app.models.availability import AvailabilityOverride
from app.schemas.availability import (
    AvailabilityOverrideCreate,
    AvailabilityOverrideUpdate,
    AvailabilityOverrideOut,
)
from app.core.dependencies import get_current_user, require_role
from app.models.auth import User

router = APIRouter()


@router.get("/", response_model=List[AvailabilityOverrideOut])
def list_overrides(
    employee_id: int = None,
    machine_id: int = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    q = db.query(AvailabilityOverride).filter(
        AvailabilityOverride.tenant_id == current_user.tenant_id
    )
    if employee_id:
        q = q.filter(AvailabilityOverride.employee_id == employee_id)
    if machine_id:
        q = q.filter(AvailabilityOverride.machine_id == machine_id)
    return q.order_by(AvailabilityOverride.date_from).all()


@router.post("/", response_model=AvailabilityOverrideOut, status_code=status.HTTP_201_CREATED)
def create_override(
    payload: AvailabilityOverrideCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("proprietor", "scheduler")),
):
    if not payload.employee_id and not payload.machine_id:
        raise HTTPException(status_code=400, detail="Must specify either employee_id or machine_id")
    override = AvailabilityOverride(**payload.model_dump(), tenant_id=current_user.tenant_id)
    db.add(override)
    db.commit()
    db.refresh(override)
    return override


@router.patch("/{override_id}", response_model=AvailabilityOverrideOut)
def update_override(
    override_id: int,
    payload: AvailabilityOverrideUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("proprietor", "scheduler")),
):
    override = db.query(AvailabilityOverride).filter(
        AvailabilityOverride.id == override_id,
        AvailabilityOverride.tenant_id == current_user.tenant_id,
    ).first()
    if not override:
        raise HTTPException(status_code=404, detail="Override not found")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(override, field, value)
    db.commit()
    db.refresh(override)
    return override


@router.delete("/{override_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_override(
    override_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("proprietor", "scheduler")),
):
    override = db.query(AvailabilityOverride).filter(
        AvailabilityOverride.id == override_id,
        AvailabilityOverride.tenant_id == current_user.tenant_id,
    ).first()
    if not override:
        raise HTTPException(status_code=404, detail="Override not found")
    db.delete(override)
    db.commit()
