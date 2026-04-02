"""
```python
"""
FILE PURPOSE
This file defines the authentication endpoints for the ZetaOps Copilot web application, handling user registration, login, logout, token refresh, and user profile retrieval. Introduced in the initial v4.0 release and enhanced in v4.0.2 to include industry_type in user profiles, this file sits at the API layer of the authentication system, orchestrating between incoming HTTP requests and the auth_service business logic layer while managing secure HTTP-only refresh token cookies.

WHAT THIS FILE DOES — step by step
1. Sets up a FastAPI router with /auth prefix for all authentication endpoints
2. Defines cookie configuration constants for refresh token storage (7-day expiry, HTTP-only)
3. Provides helper functions to set and clear refresh token cookies with proper security settings
4. Exposes POST /auth/register endpoint to create new tenant accounts with admin users
5. Exposes POST /auth/login endpoint to authenticate existing users and issue tokens
6. Exposes POST /auth/refresh endpoint to generate new access tokens using refresh cookies
7. Exposes POST /auth/logout endpoint to invalidate refresh tokens and clear cookies
8. Exposes GET /auth/me endpoint to return current user profile with tenant industry type

KEY FUNCTIONS / CLASSES / COMPONENTS

Name         : _set_cookie
Type         : function
Purpose      : Internal helper function that securely sets the refresh token as an HTTP-only cookie with proper security attributes. Encapsulates all cookie security configuration in one place to ensure consistency across all authentication endpoints.
Parameters   : response (Response) - FastAPI response object to attach cookie to, token (str) - refresh token value to store
Returns      : None (modifies response object in-place)
Calls        : FastAPI Response.set_cookie method
DB/API       : None
Side effects : Sets HTTP-only cookie named "refresh_token" on the response with 7-day expiry, lax samesite policy, and /auth path restriction

Name         : _clear_cookie
Type         : function
Purpose      : Internal helper function that removes the refresh token cookie from the client browser during logout. Ensures proper cleanup of authentication state by explicitly deleting the cookie rather than just expiring it.
Parameters   : response (Response) - FastAPI response object to modify
Returns      : None (modifies response object in-place)
Calls        : FastAPI Response.delete_cookie method
DB/API       : None
Side effects : Deletes the "refresh_token" cookie from the client browser with matching path

Name         : register
Type         : FastAPI endpoint
Purpose      : Creates a new tenant account with an admin user in a single transaction. This is the primary onboarding endpoint that sets up both the business tenant and the first user account, then immediately logs them in with fresh tokens.
Parameters   : payload (RegisterRequest) - contains email, password, company name, and industry type, response (Response) - FastAPI response object, db (Session) - SQLAlchemy database session
Returns      : TokenResponse containing access_token field for immediate frontend authentication
Calls        : auth_service.register_tenant_and_user, _set_cookie
DB/API       : Database writes through auth_service (creates Tenant and User records)
Side effects : Creates new tenant and user in database, sets refresh token cookie, returns access token

Name         : login
Type         : FastAPI endpoint
Purpose      : Authenticates existing users by validating email/password credentials and issuing fresh JWT tokens. This endpoint handles the standard login flow for users who already have accounts within existing tenants.
Parameters   : payload (LoginRequest) - contains email and password, response (Response) - FastAPI response object, db (Session) - SQLAlchemy database session
Returns      : TokenResponse containing access_token for frontend storage in memory
Calls        : auth_service.login, _set_cookie
DB/API       : Database queries through auth_service to validate user credentials
Side effects : Sets refresh token cookie, returns access token, may update last_login timestamp

Name         : refresh
Type         : FastAPI endpoint
Purpose      : Issues new access tokens using valid refresh tokens stored in HTTP-only cookies. This endpoint enables seamless token renewal without requiring users to re-enter credentials, supporting the security pattern of short-lived access tokens with longer-lived refresh tokens.
Parameters   : response (Response) - FastAPI response object, refresh_token (Optional[str]) - refresh token from HTTP-only cookie, db (Session) - SQLAlchemy database session
Returns      : TokenResponse containing new access_token
Calls        : auth_service.refresh_access_token, _set_cookie
DB/API       : Database queries to validate refresh token and potentially rotate it
Side effects : Sets new refresh token cookie, returns new access token, may invalidate old refresh token

Name         : logout
Type         : FastAPI endpoint
Purpose      : Invalidates user sessions by revoking refresh tokens and clearing authentication cookies. This endpoint ensures proper cleanup of authentication state on both server and client sides when users explicitly log out.
Parameters   : response (Response) - FastAPI response object, refresh_token (Optional[str]) - refresh token from HTTP-only cookie, db (Session) - SQLAlchemy database session
Returns      : MessageResponse with success message
Calls        : auth_service.logout, _clear_cookie
DB/API       : Database writes to invalidate refresh token if present
Side effects : Invalidates refresh token in database, clears refresh token cookie from browser

Name         : me
Type         : FastAPI endpoint
Purpose      : Returns the current authenticated user's profile information including their role, tenant association, and importantly the tenant's industry_type for frontend configuration. Enhanced in v4.0.2 to include industry_type so the frontend can load industry-specific UI components and workflows.
Parameters   : current_user (User) - authenticated user from JWT token via get_current_user dependency, db (Session) - SQLAlchemy database session
Returns      : UserResponse containing id, email, role, tenant_id, is_active, and industry_type fields
Calls        : Direct SQLAlchemy query to Tenant model
DB/API       : SELECT query on Tenant table filtered by tenant_id
Side effects : None (read-only operation)

WHO CALLS THIS FILE
- frontend/src/api/api_auth.ts - makes HTTP requests to all these endpoints
- frontend/src/auth/AuthContext.tsx - calls login, logout, refresh, and me endpoints
- frontend/src/pages/LoginPage.tsx - calls login endpoint
- frontend/src/pages/RegisterPage.tsx - calls register endpoint
- backend/app/main.py - includes this router in the main FastAPI application

IMPORTS EXPLAINED
- typing.Optional - used for refresh_token parameter that may be None if no cookie present
- fastapi.APIRouter - creates the /auth router that groups all authentication endpoints
- fastapi.Cookie - extracts refresh_token from HTTP-only cookie in request headers
- fastapi.Depends - dependency injection for database sessions and current user authentication
- fastapi.HTTPException - raises 401 errors when refresh tokens are missing or invalid
- fastapi.Response - modifies HTTP response to set/clear cookies
- fastapi.status - provides HTTP status code constants for consistent API responses
- sqlalchemy.orm.Session - database session type for dependency injection
- app.core.dependencies.get_current_user - validates JWT tokens and returns authenticated User objects
- app.database.get_db - provides SQLAlchemy database sessions with proper cleanup
- app.schemas.auth - Pydantic models for request/response validation and serialization
- app.services.auth_service - business logic layer that handles actual authentication operations

INTERN NOTES
- Easiest thing to break: Changing cookie path or security settings without updating both set and clear functions - cookies won't be properly removed on logout
- Non-obvious design decision: Access tokens are returned in response body for frontend memory storage while refresh tokens go in HTTP-only cookies to prevent XS
"""

from typing import Optional
from fastapi import APIRouter, Cookie, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session
from app.core.dependencies import get_current_user
from app.database import get_db
from app.schemas.auth import LoginRequest, MessageResponse, RegisterRequest, TokenResponse, UserResponse
from app.services import auth_service

router = APIRouter(prefix="/auth", tags=["auth"])
COOKIE_NAME = "refresh_token"
COOKIE_MAX_AGE = 7 * 24 * 60 * 60


def _set_cookie(response: Response, token: str):
    response.set_cookie(key=COOKIE_NAME, value=token, httponly=True,
        samesite="lax", secure=False, max_age=COOKIE_MAX_AGE, path="/auth")

def _clear_cookie(response: Response):
    response.delete_cookie(key=COOKIE_NAME, path="/auth")


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
def register(payload: RegisterRequest, response: Response, db: Session = Depends(get_db)):
    result = auth_service.register_tenant_and_user(payload, db)
    _set_cookie(response, result["refresh_token"])
    return TokenResponse(access_token=result["access_token"])


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest, response: Response, db: Session = Depends(get_db)):
    result = auth_service.login(payload, db)
    _set_cookie(response, result["refresh_token"])
    return TokenResponse(access_token=result["access_token"])


@router.post("/refresh", response_model=TokenResponse)
def refresh(
    response: Response,
    refresh_token: Optional[str] = Cookie(default=None, alias=COOKIE_NAME),
    db: Session = Depends(get_db),
):
    if not refresh_token:
        raise HTTPException(status_code=401, detail="No refresh token provided")
    result = auth_service.refresh_access_token(refresh_token, db)
    _set_cookie(response, result["refresh_token"])
    return TokenResponse(access_token=result["access_token"])


@router.post("/logout", response_model=MessageResponse)
def logout(
    response: Response,
    refresh_token: Optional[str] = Cookie(default=None, alias=COOKIE_NAME),
    db: Session = Depends(get_db),
):
    if refresh_token:
        auth_service.logout(refresh_token, db)
    _clear_cookie(response)
    return MessageResponse(message="Logged out successfully")


@router.get("/me", response_model=UserResponse)
def me(
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    # v4.0.2 — include industry_type from tenant so frontend loads correct config
    from app.models.auth import Tenant
    tenant = db.query(Tenant).filter(Tenant.id == current_user.tenant_id).first()
    industry_type = (tenant.industry_type or "printing") if tenant else "printing"
    return {
        "id":            current_user.id,
        "email":         current_user.email,
        "role":          current_user.role,
        "tenant_id":     current_user.tenant_id,
        "is_active":     current_user.is_active,
        "industry_type": industry_type,
    }
