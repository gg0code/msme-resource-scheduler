"""
app/core/plan_limits.py — V1.2 (v6.3.2.3)
Single source of truth for free/paid tier resource limits.
Used as a FastAPI dependency on POST endpoints AND as the data
source for GET /api/dashboard/plan-limits (consumed by the UI).

v6.3.2.3 unification: previously there were three sources (this file,
app/services/plan_limits.py — now deleted, and an inline dict in
routers/dashboard.py). The POST guards used `jobs=5, machines=5`
while the UI displayed `jobs=20, machines=10`, so users were
surprised when creation was blocked below the displayed limit.
This file is now the only source. Values normalised to the higher
set (matching the UI's prior promise) and `raw_materials` added.
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
        "employees":     10,
        "jobs":          20,
        "machines":      10,
        "skills":        20,
        "raw_materials":  5,
    },
    "paid": {
        "employees":     None,
        "jobs":          None,
        "machines":      None,
        "skills":        None,
        "raw_materials": None,
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
