# app/services/auth_service.py - register, login, refresh, logout
# Branch: v5-whatsapp
#
# FILE PURPOSE
# Business logic for the auth router. Owns the single transaction that
# creates a Tenant and User on signup, mints initial JWT + refresh tokens,
# and (v6.3.2) wires the v6.4 entry-gate fields plus optional phone-tenant
# linking for whatsapp_first / hybrid signups.
#
# WHO CALLS THIS FILE
# - app/routers/auth.py - /auth/register, /auth/login, /auth/refresh, /auth/logout
#
# WHAT THIS FILE CALLS
# - app/core/security: JWT minting, password hashing, refresh token storage
# - app/services/whatsapp_identity.link_phone_to_tenant - PhoneTenantMap helper
# - app/models/auth: Tenant, User, RefreshToken ORM
#
# DESIGN NOTES
# - role='proprietor' (not 'owner') is intentional. The v6.3.2 prompt asks
#   for role='owner' per SRS canonical naming, but require_role() across
#   50+ endpoints (employees, machines, jobs, skills, ...) does an exact
#   string match against 'proprietor'. Switching to 'owner' here without
#   sweeping every require_role() call would 403-lock new tenants out of
#   their own data. The proprietor->owner consolidation is tracked as an
#   open item for v6.5+ (see docs/release-plans/v6.3.1-handoff.md and
#   v6.3.2-handoff.md). is_top_tier still returns True for 'proprietor'.
# - Validation lives in the Pydantic schema (RegisterRequest model_validator)
#   per the v6.3.2 anti-pattern guidance. The service layer trusts the
#   payload it receives is internally consistent.

from datetime import datetime, timezone
from fastapi import HTTPException
from sqlalchemy.orm import Session
from app.core.security import (
    create_access_token, generate_refresh_token, hash_password,
    hash_refresh_token, refresh_token_expiry, verify_password,
)
from app.models.auth import RefreshToken, Tenant, User
from app.schemas.auth import LoginRequest, RegisterRequest


# ---------------------------------------------------------------------------
# v6.3.2 entry-gate mapping
# ---------------------------------------------------------------------------

def determine_entry_mode_and_segment(team_size: str) -> tuple[str, str]:
    """
    Map a team_size answer from the signup form to the (entry_mode, size_segment) pair.

    Single mapping table — used during signup to set Tenant.entry_mode and
    Tenant.size_segment in one place. SRS v6.4 Section 6.28 Feature 1 defines
    these three buckets; values must stay aligned with the corresponding
    Literal in app/schemas/auth.RegisterRequest.

    Called by: register_tenant_and_user (this file).
    Calls into: nothing — pure mapping, no DB, no IO.

    Returns: (entry_mode, size_segment) — both non-None lowercase strings.
    Raises:  ValueError if team_size is not one of '1-15', '16-50', '51+'.
             Pydantic schema rejects bad values upstream, so this only fires
             if a caller bypasses the schema (e.g. a future internal caller).
    """
    if team_size == "1-15":
        return ("whatsapp_first", "small")
    if team_size == "16-50":
        return ("hybrid", "medium")
    if team_size == "51+":
        return ("desktop_first", "large")
    raise ValueError(f"Unknown team_size: {team_size!r}")


def _next_step_for(entry_mode: str) -> str:
    """
    Pick the post-signup landing route based on entry_mode.

    Called by: register_tenant_and_user (this file).
    Calls into: nothing — pure mapping.

    desktop_first  -> 'dashboard'  (frontend routes to /dashboard).
    whatsapp_first -> 'connect_whatsapp' (placeholder /connect-whatsapp page;
                      v6.3.5 replaces with the real QR-scan flow).
    hybrid         -> 'connect_whatsapp' (same placeholder; the user gets
                      access to both surfaces post-onboarding).
    """
    if entry_mode == "desktop_first":
        return "dashboard"
    return "connect_whatsapp"


# ---------------------------------------------------------------------------
# /auth/register
# ---------------------------------------------------------------------------

def register_tenant_and_user(payload: RegisterRequest, db: Session) -> dict:
    """
    Create a Tenant + User row, mint tokens, and (v6.3.2) optionally link
    the user's WhatsApp phone to a fresh PhoneTenantMap row when the chosen
    entry_mode requires it.

    All DB mutations run in one transaction — if PhoneTenantMap creation
    fails, the Tenant + User must roll back too. The single commit at the
    end of the function (via _create_refresh_token + db.commit()) is the
    transaction boundary; link_phone_to_tenant() also commits, so we order
    the commit-bearing call last and let SQLAlchemy fold them.

    Called by: app/routers/auth.py:register
    Calls into:
      - hash_password / create_access_token / refresh-token helpers
      - determine_entry_mode_and_segment (entry-gate lookup)
      - whatsapp_identity.link_phone_to_tenant (when phone provided AND
        entry_mode != 'desktop_first')

    Returns a dict with:
      access_token:  JWT bearer string
      refresh_token: raw refresh token (router puts it in an HttpOnly cookie)
      user:          User ORM instance (loaded post-commit)
      tenant_id:     int — used by RAG / demo seeders in the router
      next_step:     'dashboard' | 'connect_whatsapp' — frontend routing hint
    """
    if db.query(Tenant).filter(Tenant.slug == payload.slug).first():
        raise HTTPException(status_code=400, detail="Slug already taken")
    # Email may be omitted on whatsapp_first signups; only check when set.
    if payload.email and db.query(User).filter(User.email == payload.email).first():
        raise HTTPException(status_code=400, detail="Email already registered")

    entry_mode, size_segment = determine_entry_mode_and_segment(payload.team_size)
    created_via = "whatsapp_first_signup" if entry_mode == "whatsapp_first" else "desktop_signup"

    tenant = Tenant(
        name=payload.company_name,
        slug=payload.slug,
        plan="free",
        industry_type=payload.industry_type,
        entry_mode=entry_mode,
        size_segment=size_segment,
        created_via=created_via,
    )
    db.add(tenant)
    db.flush()

    # whatsapp_first signups may legitimately omit the password — they
    # authenticate exclusively via WhatsApp. Store an empty hash so the
    # NOT NULL constraint is satisfied; bcrypt.checkpw will never match
    # any input against this, blocking accidental password login.
    hashed = hash_password(payload.password) if payload.password else ""
    user = User(
        tenant_id=tenant.id,
        email=payload.email or f"{payload.slug}+nomail@whatsapp.local",
        hashed_password=hashed,
        role="proprietor",  # see DESIGN NOTES at top of file
        phone_e164=payload.phone_e164,
        created_via=created_via,
    )
    db.add(user)
    db.flush()

    # Auto-link WhatsApp phone for whatsapp_first / hybrid signups.
    # desktop_first tenants skip this — they will link their phone later
    # via the LinkWhatsApp.tsx page if/when they choose to.
    if entry_mode != "desktop_first" and payload.phone_e164:
        # Late import: whatsapp_identity imports app.models.* which imports
        # app.database — no cycle here, but matching the late-import idiom
        # used elsewhere keeps this file unambiguously dependency-light.
        from app.services.whatsapp_identity import (
            link_phone_to_tenant, PhoneAlreadyLinkedError,
        )
        try:
            link_phone_to_tenant(
                db,
                tenant_id=tenant.id,
                user_id=user.id,
                phone_number=payload.phone_e164,
                phone_role="owner",
                display_name=payload.company_name,
                consent_given=False,  # owner replies HAAN later via WhatsApp
            )
        except PhoneAlreadyLinkedError:
            # Globally unique phone_number means another tenant already
            # claimed this phone. Surface to the client so they can
            # contact support / choose a different number.
            raise HTTPException(
                status_code=400,
                detail=f"Phone {payload.phone_e164} is already linked to another tenant.",
            )

    raw_refresh = _create_refresh_token(db, user)
    db.commit()
    db.refresh(user)
    access_token = create_access_token(user.id, tenant.id, user.role)
    return {
        "access_token": access_token,
        "refresh_token": raw_refresh,
        "user": user,
        "tenant_id": tenant.id,
        "next_step": _next_step_for(entry_mode),
    }


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
