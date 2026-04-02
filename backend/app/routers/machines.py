"""
```python
"""
FILE PURPOSE
This file defines FastAPI endpoints for managing machines in the ZetaOps Copilot manufacturing
scheduling system. It provides CRUD operations for machines that can be assigned to jobs in the
scheduler engine. This file was introduced in v1.1 with full JWT authentication, tenant scoping,
role-based access control, and subscription plan limits. It sits in the routing layer of the
backend architecture, handling HTTP requests and delegating to SQLAlchemy ORM models for data
persistence.

WHAT THIS FILE DOES — step by step
1. Sets up a FastAPI router instance for machine-related endpoints
2. Defines a private helper function _sync_skill_reqs to manage machine skill requirements
3. Implements GET / endpoint to list all machines for the current user's tenant with optional status filtering
4. Implements GET /{machine_id} endpoint to retrieve a specific machine by ID
5. Implements POST / endpoint to create new machines with plan limit enforcement and skill requirements
6. Implements PATCH /{machine_id} endpoint to update existing machines and their skill requirements
7. Implements DELETE /{machine_id} endpoint to delete machines (proprietor only)

KEY FUNCTIONS / CLASSES / COMPONENTS

Name         : _sync_skill_reqs
Type         : function (private helper)
Purpose      : Synchronizes machine skill requirements by deleting all existing requirements for a machine
               and recreating them from the provided list. This ensures atomic updates of skill requirements.
Parameters   : db (Session) - SQLAlchemy database session for queries
               machine (Machine) - the machine ORM instance to update requirements for
               reqs (list) - list of skill requirement objects with skill_id, min_skill_level, employees_required
               tenant_id (int) - tenant ID for security scoping of skill requirement records
Returns      : None (modifies database state through the session)
Calls        : SQLAlchemy ORM query methods, MachineSkillRequirement model constructor
DB/API       : Deletes existing MachineSkillRequirement records, inserts new ones
Side effects : Modifies database by replacing all skill requirements for the given machine

Name         : list_machines
Type         : FastAPI endpoint (GET /)
Purpose      : Retrieves all machines belonging to the current user's tenant, with optional filtering by
               machine status. Returns machines ordered alphabetically by name for consistent UI display.
Parameters   : status (str, optional) - filter machines by status field if provided
               db (Session) - injected database session dependency
               current_user (User) - injected authenticated user from JWT token
Returns      : List[MachineOut] - list of machine objects serialized to Pydantic response schema
Calls        : SQLAlchemy query methods, get_db and get_current_user dependencies
DB/API       : Queries Machine table filtered by tenant_id and optionally by status
Side effects : None (read-only operation)

Name         : get_machine
Type         : FastAPI endpoint (GET /{machine_id})
Purpose      : Retrieves a specific machine by ID, ensuring it belongs to the current user's tenant.
               Raises 404 if machine doesn't exist or doesn't belong to the user's tenant.
Parameters   : machine_id (int) - ID of the machine to retrieve from URL path
               db (Session) - injected database session dependency
               current_user (User) - injected authenticated user from JWT token
Returns      : MachineOut - single machine object serialized to Pydantic response schema
Calls        : SQLAlchemy query methods, get_db and get_current_user dependencies
DB/API       : Queries Machine table by ID and tenant_id
Side effects : Raises HTTPException with 404 status if machine not found

Name         : create_machine
Type         : FastAPI endpoint (POST /)
Purpose      : Creates a new machine for the current user's tenant, enforcing subscription plan limits
               and handling skill requirements. Only accessible to users with scheduler+ roles.
Parameters   : payload (MachineCreate) - Pydantic schema with machine data and skill requirements
               db (Session) - injected database session dependency
               current_user (User) - injected user with proprietor or scheduler role validation
Returns      : MachineOut - newly created machine object with 201 status code
Calls        : check_plan_limit dependency, _sync_skill_reqs helper, Machine model constructor
DB/API       : Inserts new Machine record and associated MachineSkillRequirement records
Side effects : Creates database records, enforces plan limits (max 5 machines on free plan)

Name         : update_machine
Type         : FastAPI endpoint (PATCH /{machine_id})
Purpose      : Updates an existing machine's fields and skill requirements using partial updates.
               Only updates fields provided in the request payload, preserving others unchanged.
Parameters   : machine_id (int) - ID of machine to update from URL path
               payload (MachineUpdate) - Pydantic schema with partial machine update data
               db (Session) - injected database session dependency
               current_user (User) - injected user with proprietor or scheduler role validation
Returns      : MachineOut - updated machine object serialized to response schema
Calls        : require_role dependency, _sync_skill_reqs helper, SQLAlchemy setattr updates
DB/API       : Updates Machine record fields, replaces MachineSkillRequirement records if provided
Side effects : Modifies existing database records, raises 404 if machine not found

Name         : delete_machine
Type         : FastAPI endpoint (DELETE /{machine_id})
Purpose      : Permanently deletes a machine and its associated records. Restricted to proprietor role
               only since machine deletion affects scheduling and could impact business operations.
Parameters   : machine_id (int) - ID of machine to delete from URL path
               db (Session) - injected database session dependency
               current_user (User) - injected user with proprietor role validation
Returns      : None (204 No Content status code)
Calls        : require_role dependency with proprietor-only access, SQLAlchemy delete methods
DB/API       : Deletes Machine record (cascading deletes handle related skill requirements)
Side effects : Permanently removes machine from database, raises 404 if machine not found

WHO CALLS THIS FILE
- backend/app/main.py - registers this router with the main FastAPI application instance
- frontend/src/api/api_machines.ts - makes HTTP requests to these endpoints from the React frontend
- backend/app/scheduler/engine.py - indirectly uses machines created through these endpoints during scheduling

IMPORTS EXPLAINED
- fastapi - Provides APIRouter, Depends, HTTPException, and status codes for REST endpoint definitions
- sqlalchemy.orm.Session - Database session type for dependency injection and ORM queries
- typing.List - Type hint for endpoint return types in function signatures
- app.database.get_db - Dependency that provides SQLAlchemy database session to endpoints
- app.models.machine - ORM models for Machine and MachineSkillRequirement database tables
- app.schemas.machine - Pydantic schemas for request/response serialization and validation
- app.core.dependencies - Authentication and authorization dependencies (get_current_user, require_role)
- app.core.plan_limits - Subscription plan enforcement dependency (check_plan_limit)
- app.models.auth.User - User ORM model type for authenticated user dependency injection

INTERN NOTES
- Easiest thing to break: Forgetting tenant_id filtering on queries - this creates security bugs where users can access other tenants' machines
- Non-obvious design decision: _sync_skill_reqs deletes and recreates all requirements instead of diffing because it's simpler and atomic
- Most common mistake: Not using exclude_unset=True in PATCH operations
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List

from app.database import get_db
from app.models.machine import Machine, MachineSkillRequirement
from app.schemas.machine import MachineCreate, MachineUpdate, MachineOut
from app.core.dependencies import get_current_user, require_role
from app.core.plan_limits import check_plan_limit
from app.models.auth import User

router = APIRouter()


def _sync_skill_reqs(db: Session, machine: Machine, reqs: list, tenant_id: int):
    db.query(MachineSkillRequirement).filter(MachineSkillRequirement.machine_id == machine.id).delete()
    for r in reqs:
        db.add(MachineSkillRequirement(
            tenant_id=tenant_id,
            machine_id=machine.id,
            skill_id=r.skill_id,
            min_skill_level=r.min_skill_level,
            employees_required=r.employees_required,
        ))


@router.get("/", response_model=List[MachineOut])
def list_machines(
    status: str = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    q = db.query(Machine).filter(Machine.tenant_id == current_user.tenant_id)
    if status:
        q = q.filter(Machine.status == status)
    return q.order_by(Machine.name).all()


@router.get("/{machine_id}", response_model=MachineOut)
def get_machine(
    machine_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    m = db.query(Machine).filter(
        Machine.id == machine_id,
        Machine.tenant_id == current_user.tenant_id,
    ).first()
    if not m:
        raise HTTPException(status_code=404, detail="Machine not found")
    return m


@router.post(
    "/",
    response_model=MachineOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(check_plan_limit("machines", Machine))],
)
def create_machine(
    payload: MachineCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("proprietor", "scheduler")),
):
    data = payload.model_dump(exclude={"skill_requirements"})
    data["tenant_id"] = current_user.tenant_id
    machine = Machine(**data)
    db.add(machine)
    db.flush()
    _sync_skill_reqs(db, machine, payload.skill_requirements, current_user.tenant_id)
    db.commit()
    db.refresh(machine)
    return machine


@router.patch("/{machine_id}", response_model=MachineOut)
def update_machine(
    machine_id: int,
    payload: MachineUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("proprietor", "scheduler")),
):
    m = db.query(Machine).filter(
        Machine.id == machine_id,
        Machine.tenant_id == current_user.tenant_id,
    ).first()
    if not m:
        raise HTTPException(status_code=404, detail="Machine not found")
    data = payload.model_dump(exclude_unset=True, exclude={"skill_requirements"})
    for field, value in data.items():
        setattr(m, field, value)
    if payload.skill_requirements is not None:
        _sync_skill_reqs(db, m, payload.skill_requirements, current_user.tenant_id)
    db.commit()
    db.refresh(m)
    return m


@router.delete("/{machine_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_machine(
    machine_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("proprietor")),
):
    m = db.query(Machine).filter(
        Machine.id == machine_id,
        Machine.tenant_id == current_user.tenant_id,
    ).first()
    if not m:
        raise HTTPException(status_code=404, detail="Machine not found")
    db.delete(m)
    db.commit()
