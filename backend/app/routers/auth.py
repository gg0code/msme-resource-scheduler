"""app/routers/auth.py — register, login, refresh, logout, me"""
from typing import Optional
from fastapi import APIRouter, Cookie, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session
from app.core.dependencies import get_current_user
from app.database import get_db
from app.models.auth import Tenant
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
    # Create tenant + user and get back tokens
    result = auth_service.register_tenant_and_user(payload, db)

    # v6.1: Seed RAG industry knowledge files for the new tenant.
    # Copies rag_data/_templates/{industry_type}/*.txt -> rag_data/{tenant_id}/
    # This gives the tenant industry-relevant AI context from Day 1.
    #
    # IMPORTANT: seeding runs AFTER the DB commit inside register_tenant_and_user.
    # If seeding fails, we log the error but do NOT fail the registration —
    # the tenant gets a working account, just without RAG context initially.
    # They can be re-seeded manually if needed.
    try:
        from app.services.rag_service import seed_rag_from_template
        tenant_id   = result.get("tenant_id")
        industry    = getattr(payload, "industry_type", None) or "printing"
        if tenant_id:
            seed_rag_from_template(tenant_id=tenant_id, industry_type=industry)
    except Exception as exc:
        # Never block registration because of RAG seeding failure
        import logging as _logging
        _logging.getLogger(__name__).error(
            "register: RAG seeding failed for new tenant (industry=%s): %s. "
            "Tenant registered successfully. Run seed_rag_from_template() manually.",
            getattr(payload, "industry_type", "unknown"), exc,
        )

    # SRS §6.14: Seed demo data (skills, employees, machines, jobs) for the
    # new tenant so they land on a populated dashboard instead of a blank screen.
    # Same contract as RAG seeding above: runs AFTER DB commit, failures are
    # logged but never block registration.
    try:
        from app.services.demo_seeder import seed_demo_data
        tenant_id = result.get("tenant_id")
        industry  = getattr(payload, "industry_type", None) or "printing"
        if tenant_id:
            seed_demo_data(db, tenant_id, industry)
    except Exception as exc:
        import logging as _logging
        _logging.getLogger(__name__).error(
            "register: demo seeding failed for new tenant (industry=%s): %s. "
            "Tenant registered successfully. Run seed_demo_data() manually.",
            getattr(payload, "industry_type", "unknown"), exc,
        )

    _set_cookie(response, result["refresh_token"])
    return TokenResponse(
        access_token=result["access_token"],
        next_step=result.get("next_step"),
    )


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
def me(current_user=Depends(get_current_user), db: Session = Depends(get_db)):
    tenant = db.query(Tenant).filter(Tenant.id == current_user.tenant_id).first()
    return {
        "id": current_user.id,
        "email": current_user.email,
        "role": current_user.role,
        "tenant_id": current_user.tenant_id,
        "is_active": current_user.is_active,
        "industry_type": tenant.industry_type if tenant else None,
    }
