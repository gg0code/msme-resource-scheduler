"""
```python
"""
FILE PURPOSE
This file handles all user authentication and tenant registration operations for the ZetaOps Copilot
application. It serves as the core authentication service layer, providing secure user registration,
login, token refresh, and logout functionality with proper tenant isolation. This file was part of
the original v4.0 architecture and sits between the FastAPI router layer and the database models,
implementing the business logic for user identity management and multi-tenant security.

WHAT THIS FILE DOES — step by step
1. Imports security utilities for password hashing, token generation, and validation
2. Imports database models (User, Tenant, RefreshToken) and request schemas
3. Imports demo data seeding service for new tenant onboarding
4. Defines register_tenant_and_user() to create new tenants with their first proprietor user
5. Defines login() to authenticate existing users and generate new token pairs
6. Defines refresh_access_token() to issue new access tokens using valid refresh tokens
7. Defines logout() to revoke refresh tokens and end user sessions
8. Defines _create_refresh_token() as internal helper to generate and store refresh tokens

KEY FUNCTIONS / CLASSES / COMPONENTS

Name         : register_tenant_and_user
Type         : function
Purpose      : Creates a new tenant organization and its first proprietor user in a single transaction.
               Validates uniqueness of tenant slug and user email, then seeds industry-specific demo
               data to help new customers get started quickly. Returns authentication tokens so the
               user is immediately logged in after registration.
Parameters   : payload (RegisterRequest) - contains company_name, slug, email, password, industry_type
               db (Session) - SQLAlchemy database session for transaction management
Returns      : dict with "access_token" (JWT), "refresh_token" (opaque string), "user" (User model)
Calls        : app.core.security.hash_password, _create_refresh_token, create_access_token
               app.services.demo_seeder.seed_demo_data
DB/API       : Queries Tenant and User tables to check uniqueness, inserts new Tenant and User records
Side effects : Creates database records, commits transaction, may seed demo data (Jobs, Employees, etc.)

Name         : login
Type         : function
Purpose      : Authenticates an existing user by email and password, then generates a new token pair
               for the session. Validates the user is active and their credentials are correct.
               Each login creates a new refresh token while old ones remain valid until expiration.
Parameters   : payload (LoginRequest) - contains email and password for authentication
               db (Session) - SQLAlchemy database session for queries and token storage
Returns      : dict with "access_token" (JWT), "refresh_token" (opaque string), "user" (User model)
Calls        : app.core.security.verify_password, _create_refresh_token, create_access_token
DB/API       : Queries User table by email, inserts new RefreshToken record
Side effects : Creates new refresh token in database, commits transaction

Name         : refresh_access_token
Type         : function
Purpose      : Exchanges a valid refresh token for a new access token and refresh token pair.
               Implements token rotation security pattern by immediately revoking the used refresh
               token and issuing a replacement. Validates token hasn't expired or been revoked.
Parameters   : raw_token (str) - the unhashed refresh token string from the client
               db (Session) - SQLAlchemy database session for token lookup and updates
Returns      : dict with "access_token" (new JWT) and "refresh_token" (new opaque string)
Calls        : app.core.security.hash_refresh_token, _create_refresh_token, create_access_token
DB/API       : Queries RefreshToken by hash and expiration, queries User for active status
Side effects : Marks old refresh token as revoked, creates new refresh token, commits transaction

Name         : logout
Type         : function
Purpose      : Ends a user session by revoking their refresh token, preventing future token refreshes.
               Access tokens remain valid until natural expiration since they cannot be revoked
               server-side. Safe to call even if token doesn't exist or is already revoked.
Parameters   : raw_token (str) - the unhashed refresh token string to revoke
               db (Session) - SQLAlchemy database session for token updates
Returns      : None (void function)
Calls        : app.core.security.hash_refresh_token
DB/API       : Queries RefreshToken by hash, updates revoked status if found
Side effects : Marks refresh token as revoked in database, commits transaction

Name         : _create_refresh_token
Type         : function (private helper)
Purpose      : Internal utility to generate a new refresh token, hash it for database storage,
               and create a RefreshToken record with proper expiration. Used by login and refresh
               operations to avoid code duplication and ensure consistent token handling.
Parameters   : db (Session) - SQLAlchemy database session for inserting token record
               user (User) - User model instance to associate the token with
Returns      : str - the raw (unhashed) refresh token string to send to the client
Calls        : app.core.security.generate_refresh_token, hash_refresh_token, refresh_token_expiry
DB/API       : Inserts new RefreshToken record with hashed token and calculated expiration
Side effects : Creates RefreshToken database record (not committed until caller commits)

WHO CALLS THIS FILE
- backend/app/routers/auth_router.py imports all public functions for FastAPI endpoints
- backend/app/routers/user_router.py may import for user management operations
- Any service that needs to programmatically authenticate users or manage tokens

IMPORTS EXPLAINED
- datetime, timezone: For handling refresh token expiration timestamps with UTC timezone awareness
- HTTPException from fastapi: For raising HTTP 400/401/403 errors with proper status codes and messages
- Session from sqlalchemy.orm: Type hint and interface for database transaction management
- app.core.security functions: Cryptographic utilities for password hashing, token generation, and validation
- app.models.auth models: SQLAlchemy ORM models for User, Tenant, and RefreshToken database tables
- app.schemas.auth schemas: Pydantic request validation models for login and registration endpoints
- app.services.demo_seeder.seed_demo_data: Service to populate new tenants with sample industry data

INTERN NOTES
- Easiest thing to break: Forgetting to include tenant_id when creating RefreshToken records, violating design principle #2 about tenant scoping
- Non-obvious design decision: refresh_access_token() revokes the old token immediately (token rotation) for security, so clients must store the new refresh token or lose access
- Most common mistake: Not wrapping registration in try/catch for demo seeding - seeding failures must never break the core registration flow
- Design principle implemented: #2 (tenant scoping) - all tokens and users are properly associated with tenant_id for multi-tenant isolation
- What to check if behaving unexpectedly: Verify refresh tokens aren't being reused after revocation, check token expiration timestamps are in UTC, confirm demo seeding isn't throwing exceptions
- v4-dev specific: This file is stable production code - any changes must maintain backward compatibility with existing token formats and database schema
```
"""

from datetime import datetime, timezone
from fastapi import HTTPException
from sqlalchemy.orm import Session
from app.core.security import (
    create_access_token, generate_refresh_token, hash_password,
    hash_refresh_token, refresh_token_expiry, verify_password,
)
from app.models.auth import RefreshToken, Tenant, User
from app.schemas.auth import LoginRequest, RegisterRequest
from app.services.demo_seeder import seed_demo_data


def register_tenant_and_user(payload: RegisterRequest, db: Session) -> dict:
    if db.query(Tenant).filter(Tenant.slug == payload.slug).first():
        raise HTTPException(status_code=400, detail="Slug already taken")
    if db.query(User).filter(User.email == payload.email).first():
        raise HTTPException(status_code=400, detail="Email already registered")
    tenant = Tenant(name=payload.company_name, slug=payload.slug, plan="free", industry_type=payload.industry_type)
    db.add(tenant)
    db.flush()
    user = User(tenant_id=tenant.id, email=payload.email,
                hashed_password=hash_password(payload.password), role="proprietor")
    db.add(user)
    db.flush()
    raw_refresh = _create_refresh_token(db, user)
    db.commit()
    db.refresh(user)

    # v4.0.6 — seed industry-specific demo data for new tenant
    try:
        seed_demo_data(db, tenant.id, payload.industry_type)
    except Exception:
        pass  # seeding failure must never break registration

    access_token = create_access_token(user.id, tenant.id, user.role)
    return {"access_token": access_token, "refresh_token": raw_refresh, "user": user}


def login(payload: LoginRequest, db: Session) -> dict:
    user = db.query(User).filter(User.email == payload.email).first()
    if not user or not verify_password(payload.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    if not user.is_active:
        raise HTTPException(status_code=403, detail="Account is inactive")
    raw_refresh = _create_refresh_token(db, user)
    db.commit()
    access_token = create_access_token(user.id, user.tenant_id, user.role)
    return {"access_token": access_token, "refresh_token": raw_refresh, "user": user}


def refresh_access_token(raw_token: str, db: Session) -> dict:
    token_hash = hash_refresh_token(raw_token)
    now = datetime.now(timezone.utc)
    record = db.query(RefreshToken).filter(
        RefreshToken.token_hash == token_hash,
        RefreshToken.revoked == False,
        RefreshToken.expires_at > now,
    ).first()
    if not record:
        raise HTTPException(status_code=401, detail="Invalid or expired refresh token")
    user = db.query(User).filter(User.id == record.user_id, User.is_active == True).first()
    if not user:
        raise HTTPException(status_code=401, detail="User not found or inactive")
    record.revoked = True
    raw_refresh = _create_refresh_token(db, user)
    db.commit()
    access_token = create_access_token(user.id, user.tenant_id, user.role)
    return {"access_token": access_token, "refresh_token": raw_refresh}


def logout(raw_token: str, db: Session) -> None:
    record = db.query(RefreshToken).filter(
        RefreshToken.token_hash == hash_refresh_token(raw_token)
    ).first()
    if record:
        record.revoked = True
        db.commit()


def _create_refresh_token(db: Session, user: User) -> str:
    raw = generate_refresh_token()
    db.add(RefreshToken(
        user_id=user.id, tenant_id=user.tenant_id,
        token_hash=hash_refresh_token(raw), expires_at=refresh_token_expiry(),
    ))
    return raw
