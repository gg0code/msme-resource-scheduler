"""
```python
"""
FILE PURPOSE
This file defines FastAPI router endpoints for managing Skills in the ZetaOps Copilot
workforce scheduling system. Skills represent abilities or capabilities that employees can
have (e.g., "Welding", "Quality Control", "Machine Operation") and are used by the
scheduling engine to match employees with appropriate job steps. This router was
introduced in v4-dev and sits in the API layer of the backend architecture, providing
CRUD operations with full tenant scoping, JWT authentication, and role-based access control.

WHAT THIS FILE DOES — step by step
1. Creates a FastAPI APIRouter instance for handling all /api/skills/ endpoints
2. Defines GET /skills/ endpoint to list all skills for the current user's tenant
3. Defines GET /skills/{skill_id} endpoint to retrieve a specific skill by ID
4. Defines POST /skills/ endpoint to create new skills (proprietor only, with plan limits)
5. Defines PATCH /skills/{skill_id} endpoint to update existing skills (proprietor only)
6. Defines DELETE /skills/{skill_id} endpoint to remove skills (proprietor only)
7. Enforces tenant isolation on all database queries using current_user.tenant_id
8. Applies role-based access control requiring proprietor role for write operations

KEY FUNCTIONS / CLASSES / COMPONENTS

Name         : list_skills
Type         : FastAPI endpoint (GET)
Purpose      : Retrieves all skills belonging to the current user's tenant, with optional
               filtering to show only active skills. This endpoint is used by the frontend
               to populate skill selection dropdowns and skill management interfaces.
Parameters   : active_only (bool, optional): If True, filters results to only show skills
               where is_active=True. Defaults to False to show all skills.
               db (Session): SQLAlchemy database session injected via dependency.
               current_user (User): Authenticated user injected via get_current_user dependency.
Returns      : List[SkillOut]: Array of skill objects serialized according to SkillOut schema,
               ordered alphabetically by name for consistent UI display.
Calls        : SQLAlchemy query methods on Skill model, SkillOut schema serialization
DB/API       : Queries skills table with tenant_id filter and optional is_active filter
Side effects : None (read-only operation)

Name         : get_skill
Type         : FastAPI endpoint (GET)
Purpose      : Retrieves a single skill by its ID, ensuring the skill belongs to the current
               user's tenant. Used by frontend detail views and edit forms that need to load
               specific skill data.
Parameters   : skill_id (int): Primary key ID of the skill to retrieve from URL path.
               db (Session): SQLAlchemy database session injected via dependency.
               current_user (User): Authenticated user injected via get_current_user dependency.
Returns      : SkillOut: Single skill object serialized according to SkillOut schema, or
               raises 404 HTTPException if skill not found or doesn't belong to user's tenant.
Calls        : SQLAlchemy query methods on Skill model, SkillOut schema serialization
DB/API       : Queries skills table with both skill_id and tenant_id filters
Side effects : None (read-only operation)

Name         : create_skill
Type         : FastAPI endpoint (POST)
Purpose      : Creates a new skill within the current user's tenant, with duplicate name
               prevention and plan limit enforcement. Only proprietor users can create skills,
               and free plan tenants are limited to maximum 20 skills total.
Parameters   : payload (SkillCreate): Pydantic schema containing skill data from request body,
               typically including name, description, and is_active fields.
               db (Session): SQLAlchemy database session injected via dependency.
               current_user (User): Authenticated proprietor user injected via require_role dependency.
Returns      : SkillOut: Newly created skill object with generated ID and tenant_id populated,
               returns HTTP 201 status code to indicate successful resource creation.
Calls        : check_plan_limit dependency for quota enforcement, Skill model constructor,
               SQLAlchemy session add/commit/refresh operations, SkillOut schema serialization
DB/API       : Queries skills table to check for duplicate names, inserts new skill record
Side effects : Creates new database record in skills table, commits transaction

Name         : update_skill
Type         : FastAPI endpoint (PATCH)
Purpose      : Updates an existing skill's attributes using partial update semantics, where
               only provided fields are modified. Ensures skill belongs to current user's tenant
               and only allows proprietor users to make modifications.
Parameters   : skill_id (int): Primary key ID of skill to update from URL path.
               payload (SkillUpdate): Pydantic schema containing partial skill data, uses
               exclude_unset=True to only include fields that were actually provided.
               db (Session): SQLAlchemy database session injected via dependency.
               current_user (User): Authenticated proprietor user injected via require_role dependency.
Returns      : SkillOut: Updated skill object with all current field values after modification,
               or raises 404 HTTPException if skill not found or doesn't belong to user's tenant.
Calls        : SQLAlchemy query methods, Python setattr for dynamic field updates,
               SQLAlchemy session commit/refresh operations, SkillOut schema serialization
DB/API       : Queries skills table to find existing record, updates record fields in place
Side effects : Modifies existing database record in skills table, commits transaction

Name         : delete_skill
Type         : FastAPI endpoint (DELETE)
Purpose      : Permanently removes a skill from the database, ensuring it belongs to the current
               user's tenant. Only proprietor users can delete skills, and deletion is immediate
               without soft-delete functionality.
Parameters   : skill_id (int): Primary key ID of skill to delete from URL path.
               db (Session): SQLAlchemy database session injected via dependency.
               current_user (User): Authenticated proprietor user injected via require_role dependency.
Returns      : HTTP 204 No Content status (no response body), or raises 404 HTTPException
               if skill not found or doesn't belong to user's tenant.
Calls        : SQLAlchemy query methods, SQLAlchemy session delete/commit operations
DB/API       : Queries skills table to find existing record, deletes record from database
Side effects : Permanently removes database record from skills table, commits transaction

WHO CALLS THIS FILE
- backend/app/main.py imports and registers this router with the main FastAPI application
- Frontend API client files (likely frontend/src/api/api_skills.ts) make HTTP requests to these endpoints
- The scheduling engine may indirectly depend on skills data through employee-skill associations

IMPORTS EXPLAINED
- fastapi.APIRouter: Creates the router instance that groups related endpoints together
- fastapi.Depends: Enables dependency injection for database sessions, authentication, and authorization
- fastapi.HTTPException: Used to raise HTTP error responses with specific status codes and messages
- fastapi.status: Provides constants for HTTP status codes (HTTP_201_CREATED, HTTP_204_NO_CONTENT)
- sqlalchemy.orm.Session: Database session type for type hints and dependency injection
- typing.List: Type hint for the list_skills endpoint return value
- app.database.get_db: Dependency that provides SQLAlchemy database session instances
- app.models.skill.Skill: SQLAlchemy ORM model representing the skills table structure
- app.schemas.skill: Pydantic schemas for request validation and response serialization
- app.core.dependencies: Authentication and authorization functions (get_current_user, require_role)
- app.core.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List

from app.database import get_db
from app.models.skill import Skill
from app.schemas.skill import SkillCreate, SkillUpdate, SkillOut
from app.core.dependencies import get_current_user, require_role
from app.core.plan_limits import check_plan_limit
from app.models.auth import User

router = APIRouter()


@router.get("/", response_model=List[SkillOut])
def list_skills(
    active_only: bool = False,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    q = db.query(Skill).filter(Skill.tenant_id == current_user.tenant_id)
    if active_only:
        q = q.filter(Skill.is_active == True)
    return q.order_by(Skill.name).all()


@router.get("/{skill_id}", response_model=SkillOut)
def get_skill(
    skill_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    skill = db.query(Skill).filter(
        Skill.id == skill_id,
        Skill.tenant_id == current_user.tenant_id,
    ).first()
    if not skill:
        raise HTTPException(status_code=404, detail="Skill not found")
    return skill


@router.post(
    "/",
    response_model=SkillOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(check_plan_limit("skills", Skill))],
)
def create_skill(
    payload: SkillCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("proprietor")),
):
    existing = db.query(Skill).filter(
        Skill.name == payload.name,
        Skill.tenant_id == current_user.tenant_id,
    ).first()
    if existing:
        raise HTTPException(status_code=400, detail="Skill with this name already exists")
    skill = Skill(**payload.model_dump(), tenant_id=current_user.tenant_id)
    db.add(skill)
    db.commit()
    db.refresh(skill)
    return skill


@router.patch("/{skill_id}", response_model=SkillOut)
def update_skill(
    skill_id: int,
    payload: SkillUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("proprietor")),
):
    skill = db.query(Skill).filter(
        Skill.id == skill_id,
        Skill.tenant_id == current_user.tenant_id,
    ).first()
    if not skill:
        raise HTTPException(status_code=404, detail="Skill not found")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(skill, field, value)
    db.commit()
    db.refresh(skill)
    return skill


@router.delete("/{skill_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_skill(
    skill_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("proprietor")),
):
    skill = db.query(Skill).filter(
        Skill.id == skill_id,
        Skill.tenant_id == current_user.tenant_id,
    ).first()
    if not skill:
        raise HTTPException(status_code=404, detail="Skill not found")
    db.delete(skill)
    db.commit()
