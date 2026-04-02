"""
```python
"""
FILE PURPOSE
This file provides FastAPI dependency functions for authentication and role-based access control (RBAC) 
throughout the ZetaOps Copilot application. It was introduced in early v4 development and serves as the 
central authentication layer that all protected API endpoints use to verify JWT tokens, extract user 
information, and enforce role-based permissions. This sits between the FastAPI router layer and the 
core security module, acting as the bridge that converts HTTP Bearer tokens into authenticated User 
objects for business logic.

WHAT THIS FILE DOES — step by step
1. Sets up HTTPBearer security scheme for extracting Authorization headers from requests
2. Defines get_current_user() which decodes JWT tokens and fetches the corresponding User from database
3. Implements require_role() factory function that creates role-checking dependencies for specific permission levels
4. Exports three pre-configured dependency shortcuts: ProprietorOnly, SchedulerAbove, and AnyAuthUser
5. Ensures all user lookups include tenant_id filtering for multi-tenant security isolation
6. Provides standardized HTTP 401/403 error responses for authentication and authorization failures

KEY FUNCTIONS / CLASSES / COMPONENTS

Name         : bearer_scheme
Type         : HTTPBearer security scheme instance  
Purpose      : FastAPI security scheme that automatically extracts Bearer tokens from the Authorization 
               header of incoming HTTP requests. This is used by FastAPI's dependency injection system 
               to provide the token credentials to authentication functions.
Parameters   : None (configured with defaults)
Returns      : HTTPAuthorizationCredentials containing the extracted Bearer token
Calls        : None (FastAPI built-in)
DB/API       : No direct calls
Side effects : None

Name         : get_current_user
Type         : FastAPI dependency function
Purpose      : Core authentication function that validates JWT access tokens and retrieves the 
               corresponding User object from the database. This implements design principle #2 
               by ensuring tenant-scoped database queries and principle #1 by handling only 
               authentication logic without business computations.
Parameters   : credentials (HTTPAuthorizationCredentials) - Bearer token from request header via bearer_scheme
               db (Session) - SQLAlchemy database session from get_db dependency  
Returns      : User object representing the authenticated user, including their tenant_id and role
Calls        : app.core.security.decode_access_token() to verify and decode JWT payload
               app.database.get_db() for database session
DB/API       : Queries User table filtered by id, tenant_id, and is_active status
Side effects : Raises HTTPException with 401 status if token invalid or user not found

Name         : require_role  
Type         : Dependency factory function
Purpose      : Creates FastAPI dependency functions that enforce role-based access control by checking 
               if the authenticated user's role matches any of the allowed roles. This implements a 
               hierarchical permission system where higher roles can access lower-level endpoints.
Parameters   : *allowed_roles (str) - Variable number of role names that are permitted access
Returns      : FastAPI dependency function that returns User object if role check passes
Calls        : get_current_user() to get the authenticated user first
DB/API       : No direct calls (relies on get_current_user's DB query)
Side effects : Raises HTTPException with 403 status if user's role not in allowed_roles list

Name         : ProprietorOnly
Type         : Pre-configured FastAPI dependency
Purpose      : Shortcut dependency that restricts access to proprietor role only. Used for 
               tenant-level administrative functions like billing, user management, and 
               system configuration changes.
Parameters   : None (uses FastAPI dependency injection)
Returns      : User object with proprietor role
Calls        : require_role("proprietor") internally
DB/API       : Inherited from get_current_user
Side effects : 403 error if user is not proprietor

Name         : SchedulerAbove  
Type         : Pre-configured FastAPI dependency
Purpose      : Allows access to both proprietor and scheduler roles. Used for scheduling operations, 
               job management, and resource allocation endpoints that require elevated permissions 
               but don't need full proprietor access.
Parameters   : None (uses FastAPI dependency injection) 
Returns      : User object with proprietor or scheduler role
Calls        : require_role("proprietor", "scheduler") internally
DB/API       : Inherited from get_current_user
Side effects : 403 error if user role is below scheduler level

Name         : AnyAuthUser
Type         : Pre-configured FastAPI dependency  
Purpose      : Requires only valid authentication without role restrictions. Used for general 
               endpoints that any logged-in user can access, such as viewing their own profile 
               or accessing basic tenant data.
Parameters   : None (uses FastAPI dependency injection)
Returns      : Any valid User object regardless of role  
Calls        : get_current_user() directly
DB/API       : Inherited from get_current_user
Side effects : 401 error if user not authenticated, but no role restrictions

WHO CALLS THIS FILE
- backend/app/routers/auth_router.py - imports AnyAuthUser for profile endpoints
- backend/app/routers/scheduler_router.py - imports SchedulerAbove for scheduling operations  
- backend/app/routers/jobs_router.py - imports various role dependencies for job management
- backend/app/routers/employees_router.py - imports ProprietorOnly for employee management
- backend/app/routers/machines_router.py - imports SchedulerAbove for machine operations
- backend/app/routers/reports_router.py - imports role dependencies based on report sensitivity
- backend/app/routers/whatsapp_router.py - imports dependencies for WhatsApp integration endpoints

IMPORTS EXPLAINED
- typing.Annotated - Python type hint decorator for adding metadata to function parameters, used with FastAPI dependency injection
- fastapi.Depends - FastAPI dependency injection decorator that tells FastAPI to resolve dependencies automatically
- fastapi.HTTPException - FastAPI exception class for returning structured HTTP error responses with status codes  
- fastapi.status - Constants for HTTP status codes to avoid magic numbers in error responses
- fastapi.security.HTTPAuthorizationCredentials - Type representing extracted Bearer token credentials from Authorization header
- fastapi.security.HTTPBearer - FastAPI security scheme for handling Bearer token authentication automatically
- jose.JWTError - Exception raised when JWT token decoding fails due to invalid signature, expiration, or format
- sqlalchemy.orm.Session - SQLAlchemy database session type for executing database queries with proper transaction handling
- app.core.security.decode_access_token - Custom function that validates and decodes JWT access tokens into user payload  
- app.database.get_db - Database session dependency that provides SQLAlchemy Session instances to endpoint functions
- app.models.auth.User - SQLAlchemy ORM model representing user entities with authentication and role information

INTERN NOTES  
• Easiest thing to break: Forgetting to include tenant_id in the User query filter, which would allow users to access data across tenant boundaries and create a critical security vulnerability
• Non-obvious design decision: require_role() returns a closure/inner function rather than directly checking roles, because FastAPI's dependency system needs a callable that can be resolved at request time with the current user context
• Most common mistake: Using the wrong role dependency level (e.g., ProprietorOnly when SchedulerAbove would suffice), which unnecessarily restricts access and breaks functionality for scheduler-level users  
• Design principle #2: This file implements tenant scoping by always filtering User queries with both id AND tenant_id, ensuring users can never authenticate into wrong tenant contexts
• What to check if unexpected behavior: Verify JWT token format in decode_access_token(), check User.is_active status
"""

from typing import Annotated
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError
from sqlalchemy.orm import Session
from app.core.security import decode_access_token
from app.database import get_db
from app.models.auth import User

bearer_scheme = HTTPBearer()


def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(bearer_scheme)],
    db: Session = Depends(get_db),
) -> User:
    exc = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = decode_access_token(credentials.credentials)
        user_id = int(payload["sub"])
        tenant_id = int(payload["tenant_id"])
    except (JWTError, KeyError, ValueError):
        raise exc
    user = db.query(User).filter(
        User.id == user_id, User.tenant_id == tenant_id, User.is_active == True
    ).first()
    if not user:
        raise exc
    return user


def require_role(*allowed_roles: str):
    def _check(user: User = Depends(get_current_user)) -> User:
        if user.role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Role '{user.role}' not permitted. Required: {list(allowed_roles)}",
            )
        return user
    return _check


ProprietorOnly = Depends(require_role("proprietor"))
SchedulerAbove = Depends(require_role("proprietor", "scheduler"))
AnyAuthUser    = Depends(get_current_user)
