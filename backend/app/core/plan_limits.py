"""
app/core/plan_limits.py — V1.1
Single source of truth for free/paid tier limits.
Used as a FastAPI dependency on POST endpoints.
"""

from typing import Optional
from fastapi import Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.core.dependencies import get_current_user
from app.models.auth import User, Tenant

# ── Plan limits config ────────────────────────────────────────────────────────
# None = unlimited. Change numbers here only — applies everywhere automatically.
PLAN_LIMITS: dict[str, dict[str, Optional[int]]] = {
    "free": {
        "employees": 10,
        "jobs":       5,
        "machines":   5,
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
            db.query(model_class)
            .filter(model_class.tenant_id == current_user.tenant_id)
            .count()
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
