"""
```python
"""
FILE PURPOSE
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
This file implements the subscription plan enforcement system for ZetaOps Copilot, 
preventing free-tier tenants from exceeding their resource limits (employees, jobs, 
machines, skills). Introduced in v4.x as a business monetization layer, it sits 
between the authentication system and the CRUD operations, acting as a gatekeeper 
for resource creation endpoints.

WHAT THIS FILE DOES — step by step
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
1. Defines PLAN_LIMITS dictionary mapping plan types ("free"/"paid") to resource 
   limits, where None means unlimited for paid plans
2. Provides get_limit() utility to safely extract limits with fallback to "free"
3. Implements check_plan_limit() dependency factory that generates FastAPI 
   dependencies for specific resource types
4. Generated dependencies query the database to count current tenant resources
5. Compares current count against plan limit and raises HTTP 402 if exceeded
6. Returns structured error response with upgrade messaging for the frontend

KEY FUNCTIONS / CLASSES / COMPONENTS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Name         : PLAN_LIMITS
Type         : module-level constant dictionary
Purpose      : Single source of truth for all subscription plan limits across the 
               application. Free plan has numeric limits, paid plan uses None for 
               unlimited resources. Changing values here automatically applies to 
               all endpoints using the plan limit system.
Parameters   : N/A (constant)
Returns      : N/A (constant)
Calls        : N/A
DB/API       : N/A
Side effects : N/A

Name         : get_limit
Type         : function
Purpose      : Safe accessor for plan limits with automatic fallback behavior. 
               Prevents KeyError exceptions when invalid plan names are provided 
               by defaulting to "free" plan limits. Returns None for unlimited 
               resources on paid plans.
Parameters   : plan (str) - plan name like "free" or "paid", 
               resource (str) - resource type like "jobs" or "employees"
Returns      : Optional[int] - numeric limit for free plans, None for unlimited paid plans
Calls        : dict.get() methods only
DB/API       : No database or API calls
Side effects : No side effects, pure function

Name         : check_plan_limit
Type         : function (FastAPI dependency factory)
Purpose      : Creates tenant-specific plan limit enforcement dependencies for FastAPI 
               endpoints. This is a factory pattern that generates actual dependency 
               functions customized for specific resource types and model classes. 
               Used to prevent resource creation when plan limits are reached.
Parameters   : resource (str) - resource name for error messages like "jobs",
               model_class - SQLAlchemy ORM model class to query for counting
Returns      : function - FastAPI dependency function that raises HTTPException on limit breach
Calls        : get_current_user dependency, get_db dependency, get_limit function
DB/API       : Queries Tenant table for plan info, counts model_class records by tenant_id
Side effects : Raises HTTP 402 exception when limits exceeded, blocking request processing

Name         : _check (inner function)
Type         : function (generated FastAPI dependency)
Purpose      : The actual dependency function created by check_plan_limit factory. 
               Performs the runtime plan limit validation by querying the current 
               user's tenant plan, counting existing resources, and comparing against 
               limits. Follows design principle #2 by always filtering by tenant_id.
Parameters   : db (Session) - SQLAlchemy database session from get_db dependency,
               current_user (User) - authenticated user from get_current_user dependency
Returns      : None on success (limit not reached), raises HTTPException on violation
Calls        : Tenant.query(), func.count(), model_class queries, get_limit()
DB/API       : SELECT Tenant WHERE id = current_user.tenant_id, 
               SELECT COUNT(*) FROM model_class WHERE tenant_id = current_user.tenant_id
Side effects : Raises HTTPException with 402 status and detailed error structure

WHO CALLS THIS FILE
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
- backend/app/routers/employees.py - applies check_plan_limit("employees", Employee) to POST /api/employees/
- backend/app/routers/jobs.py - applies check_plan_limit("jobs", Job) to POST /api/jobs/  
- backend/app/routers/machines.py - applies check_plan_limit("machines", Machine) to POST /api/machines/
- backend/app/routers/skills.py - applies check_plan_limit("skills", Skill) to POST /api/skills/
- Any future resource creation endpoints that need plan limit enforcement

IMPORTS EXPLAINED
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
- typing.Optional - enables type hints for values that can be None (unlimited limits)
- fastapi.Depends - FastAPI dependency injection system for creating reusable dependencies  
- fastapi.HTTPException - structured HTTP error responses with status codes and details
- sqlalchemy.orm.Session - database session type for SQLAlchemy ORM operations
- sqlalchemy.func - SQL function expressions like COUNT() for database aggregations
- app.database.get_db - database session dependency that provides SQLAlchemy connection
- app.core.dependencies.get_current_user - authentication dependency that validates JWT tokens
- app.models.auth.User - SQLAlchemy User model for current user data structure
- app.models.auth.Tenant - SQLAlchemy Tenant model containing plan subscription information

INTERN NOTES
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
• Easiest thing to break: Adding a new resource type without updating PLAN_LIMITS 
  will cause KeyError crashes - always add both "free" and "paid" entries
"""

from typing import Optional
from fastapi import Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.database import get_db
from app.core.dependencies import get_current_user
from app.models.auth import User, Tenant

# ── Plan limits config ────────────────────────────────────────────────────────
# None = unlimited. Change numbers here only — applies everywhere automatically.
PLAN_LIMITS: dict[str, dict[str, Optional[int]]] = {
    "free": {
        "employees": 10,
        "jobs":      20,
        "machines":  10,
        "skills":    20,
    },
    "paid": {
        "employees": None,
        "jobs":      None,
        "machines":  None,
        "skills":    None,
    },
}


def get_limit(plan: str, resource: str) -> Optional[int]:
    """Return numeric limit for a plan+resource, or None if unlimited."""
    return PLAN_LIMITS.get(plan, PLAN_LIMITS["free"]).get(resource)


def check_plan_limit(resource: str, model_class):
    """
    FastAPI dependency factory. Raises HTTP 402 if the tenant has hit their
    plan limit for the given resource.

    Usage:
        @router.post("/", dependencies=[Depends(check_plan_limit("jobs", Job))])
    """
    def _check(
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user),
    ):
        tenant = db.query(Tenant).filter(
            Tenant.id == current_user.tenant_id
        ).first()

        plan = (getattr(tenant, "plan", None) or "free").lower()
        limit = get_limit(plan, resource)

        if limit is None:
            return  # paid plan — unlimited, skip check

        current_count = (
            db.query(func.count())
            .select_from(model_class)
            .filter(model_class.tenant_id == current_user.tenant_id)
            .scalar()
        )

        if current_count >= limit:
            raise HTTPException(
                status_code=402,
                detail={
                    "error": "plan_limit_reached",
                    "message": (
                        f"Your free plan allows up to {limit} {resource}. "
                        f"You currently have {current_count}. "
                        f"Upgrade to a paid plan to add more."
                    ),
                    "resource": resource,
                    "limit": limit,
                    "current": current_count,
                    "upgrade_required": True,
                },
            )

    return _check
