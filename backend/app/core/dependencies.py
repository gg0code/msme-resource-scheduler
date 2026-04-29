# app/core/dependencies.py - Version 1.1
# Branch: v5-whatsapp
#
# FILE PURPOSE
# FastAPI auth + RBAC dependencies. Single home for the four permission
# factories that gate every protected endpoint:
#   - get_current_user       — JWT decode + user load (foundation for all RBAC).
#   - require_role(*roles)   — exact-string role match (legacy, still used for
#                              true commercial-only endpoints).
#   - require_top_tier()     — added v6.3.3. Allows any role in TOP_TIER_ROLES
#                              ('owner', 'proprietor', 'factory_manager',
#                              'co_owner'). Backs SRS v6.4 Section 6.28.6's
#                              role-group enforcement model.
#   - require_billing_view() — added v6.3.3. Owner + proprietor + co_owner
#                              only. factory_manager blocked. For future
#                              commercial-view endpoints (briefings, plan).
#
# WHO CALLS THIS FILE
# - app/routers/* — every protected route uses one of these four dependencies.
#
# WHAT THIS FILE CALLS
# - app.core.security.decode_access_token — JWT verification.
# - app.database.get_db — sync session factory.
# - app.models.auth.User, TOP_TIER_ROLES — User ORM and the canonical top-tier
#   role tuple. Single source of truth lives in models/auth.py; this file
#   imports rather than redefines (per CLAUDE.md "single source of truth" rule).
from typing import Annotated
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError
from sqlalchemy.orm import Session
from app.core.security import decode_access_token
from app.database import get_db
from app.models.auth import TOP_TIER_ROLES, User

bearer_scheme = HTTPBearer()


# Roles allowed to view commercial / billing data. factory_manager has
# operational rights but no commercial visibility per SRS Section 6.28.6.
# Kept as a module-level constant so test code and future callers can read
# the canonical set without hardcoding the same tuple in two places.
BILLING_VIEW_ROLES: tuple = ("owner", "proprietor", "co_owner")

# Roles allowed to perform operational shop-floor actions: TOP_TIER plus
# the existing mid-tier operator roles ('scheduler' = legacy, 'manager' =
# v6.4 spelling per SRS Section 6.17). Used by require_operational() to
# preserve v5.12-era access for scheduler users (the dev DB has 1 such
# user; production likely has more) while extending access to the new
# v6.4 top-tier roles (factory_manager, co_owner).
#
# Why a tuple alias instead of inlining: keeping it here makes the role
# set discoverable in one place and lets future iterations adjust the
# operational set (e.g. add 'shift_lead') without grepping every gate.
OPERATIONAL_ROLES: tuple = (*TOP_TIER_ROLES, "scheduler", "manager")


def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(bearer_scheme)],
    db: Session = Depends(get_db),
) -> User:
    """
    Decode the bearer JWT, load the matching active User row, return it.

    Called by:    every protected endpoint, directly or via require_role /
                  require_top_tier / require_billing_view.
    Calls into:   decode_access_token (JWT verify), Session.query (User load).
    Side effects: none — pure read of users table.

    Raises 401 on any failure: malformed token, missing claims, inactive user,
    user not found. The same exception wraps every failure mode so attackers
    cannot distinguish "wrong signature" from "user disabled".
    """
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
    """
    FastAPI dependency factory: allow only users whose role is in
    `allowed_roles` (exact string match).

    Called by:    routers needing legacy exact-role gating. v6.3.3 keeps
                  this for true commercial-only sites; most operational
                  endpoints have been migrated to require_top_tier().
    Calls into:   get_current_user.
    Side effects: raises 403 on mismatch.

    Note: when gating commercial endpoints, accept BOTH 'proprietor' and
    'owner' until the v6.5+ data consolidation runs (see v6.3.1 / v6.3.2
    handoff Decision 1 + memory/feedback_role_synonyms.md).
    """
    def _check(user: User = Depends(get_current_user)) -> User:
        if user.role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Role '{user.role}' not permitted. Required: {list(allowed_roles)}",
            )
        return user
    return _check


def require_top_tier():
    """
    FastAPI dependency factory: allow any user whose role grants top-tier
    (owner-equivalent) access — owner, proprietor, factory_manager, co_owner.

    Called by:    operational endpoints (employees, machines, jobs, skills,
                  assignments, timer, unavailability, import_csv,
                  availability) reclassified in v6.3.3. Also team_management
                  router for invite + role-change endpoints (handler-level
                  guards add the "only owner can promote into top-tier"
                  refinement on top of this base check).
    Calls into:   get_current_user, then User.is_top_tier (Python property
                  on the User model — pure tuple membership against
                  TOP_TIER_ROLES from models/auth.py).
    Side effects: raises 403 with the canonical TOP_TIER_ROLES list when
                  the caller's role is outside the set.

    Backs SRS v6.4 Section 6.28.6's role-group enforcement model. Pairs
    with require_billing_view() — both replace the v5 "proprietor only"
    pattern with a richer two-axis model (operational vs commercial).
    """
    def _check(user: User = Depends(get_current_user)) -> User:
        if not user.is_top_tier:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Role '{user.role}' not permitted. Required: {list(TOP_TIER_ROLES)}",
            )
        return user
    return _check


def require_operational():
    """
    FastAPI dependency factory: allow any role with operational shop-floor
    rights — TOP_TIER (owner, proprietor, factory_manager, co_owner) PLUS
    'scheduler' (legacy) and 'manager' (v6.4 SRS Section 6.17 spelling).

    Called by:    operational endpoints reclassified in v6.3.3 that
                  previously used require_role('proprietor', 'scheduler').
                  Covers POST/PUT/DELETE on employees, machines, jobs,
                  assignments, availability, unavailability, timer,
                  import_csv. Preserves v5.12 scheduler access while
                  extending the v6.4 top-tier roles to the same gate.
    Calls into:   get_current_user.
    Side effects: raises 403 with OPERATIONAL_ROLES when out of set.

    Distinction from require_top_tier(): this gate is broader. Use
    require_top_tier() for actions that should be restricted to
    owner-equivalent roles (resource deletes that were proprietor-only
    in v5.12, team management). Use require_operational() for actions
    that should remain accessible to mid-tier operator roles.
    """
    def _check(user: User = Depends(get_current_user)) -> User:
        if user.role not in OPERATIONAL_ROLES:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Role '{user.role}' not permitted. Required: {list(OPERATIONAL_ROLES)}",
            )
        return user
    return _check


def require_billing_view():
    """
    FastAPI dependency factory: allow only roles with commercial-view rights
    — owner, proprietor, co_owner. factory_manager is explicitly blocked.

    Called by:    commercial-view endpoints (plan limits readout, billing
                  dashboards, AI usage / token reports). No current endpoint
                  uses this — it is defined for v6.3.4+ briefing-config and
                  later commercial work. Keeping the helper available now
                  means future endpoints don't need to re-derive the tuple.
    Calls into:   get_current_user.
    Side effects: raises 403 with BILLING_VIEW_ROLES when out of set.

    Per SRS v6.4 Section 6.28.6: factory_manager has operational rights
    (require_top_tier passes) but no commercial visibility (this gate
    blocks). Co_owner is included because they share commercial visibility
    with the owner per the same SRS section.
    """
    def _check(user: User = Depends(get_current_user)) -> User:
        if user.role not in BILLING_VIEW_ROLES:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Role '{user.role}' not permitted. Required: {list(BILLING_VIEW_ROLES)}",
            )
        return user
    return _check


ProprietorOnly = Depends(require_role("proprietor"))
SchedulerAbove = Depends(require_role("proprietor", "scheduler"))
AnyAuthUser    = Depends(get_current_user)
