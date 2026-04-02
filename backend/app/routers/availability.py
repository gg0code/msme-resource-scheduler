"""
routers/availability.py — V1.1
Added: JWT auth, tenant_id scoping, RBAC
  GET    — any authenticated user
  POST   — scheduler+
  PATCH  — scheduler+
  DELETE — scheduler+
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List

from app.database import get_db
from app.models.availability import AvailabilityOverride
from app.schemas.availability import (
    AvailabilityOverrideCreate,
    AvailabilityOverrideUpdate,
    AvailabilityOverrideOut,
)
from app.core.dependencies import get_current_user, require_role
from app.models.auth import User

router = APIRouter()


@router.get("/", response_model=List[AvailabilityOverrideOut])
def list_overrides(
    employee_id: int = None,
    machine_id: int = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    q = db.query(AvailabilityOverride).filter(
        AvailabilityOverride.tenant_id == current_user.tenant_id
    )
    if employee_id:
        q = q.filter(AvailabilityOverride.employee_id == employee_id)
    if machine_id:
        q = q.filter(AvailabilityOverride.machine_id == machine_id)
    return q.order_by(AvailabilityOverride.date_from).all()


@router.post("/", response_model=AvailabilityOverrideOut, status_code=status.HTTP_201_CREATED)
def create_override(
    payload: AvailabilityOverrideCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("proprietor", "scheduler")),
):
    if not payload.employee_id and not payload.machine_id:
        raise HTTPException(status_code=400, detail="Must specify either employee_id or machine_id")
    override = AvailabilityOverride(**payload.model_dump(), tenant_id=current_user.tenant_id)
    db.add(override)
    db.commit()
    db.refresh(override)
    return override


@router.patch("/{override_id}", response_model=AvailabilityOverrideOut)
def update_override(
    override_id: int,
    payload: AvailabilityOverrideUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("proprietor", "scheduler")),
):
    override = db.query(AvailabilityOverride).filter(
        AvailabilityOverride.id == override_id,
        AvailabilityOverride.tenant_id == current_user.tenant_id,
    ).first()
    if not override:
        raise HTTPException(status_code=404, detail="Override not found")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(override, field, value)
    db.commit()
    db.refresh(override)
    return override


@router.delete("/{override_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_override(
    override_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("proprietor", "scheduler")),
):
    override = db.query(AvailabilityOverride).filter(
        AvailabilityOverride.id == override_id,
        AvailabilityOverride.tenant_id == current_user.tenant_id,
    ).first()
    if not override:
        raise HTTPException(status_code=404, detail="Override not found")
    db.delete(override)
    db.commit()
