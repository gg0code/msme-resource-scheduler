"""
routers/machines.py — V1.1
Added: JWT auth, tenant_id scoping, RBAC, plan limit enforcement
  GET    — any authenticated user
  POST   — scheduler+ (+ free plan: max 5 machines)
  PATCH  — scheduler+
  DELETE — proprietor only
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List

from app.database import get_db
from app.models.machine import Machine, MachineSkillRequirement
from app.schemas.machine import MachineCreate, MachineUpdate, MachineOut
from app.core.dependencies import get_current_user, require_operational, require_top_tier
from app.core.plan_limits import check_plan_limit
from app.models.auth import User

router = APIRouter()


def _sync_skill_reqs(db: Session, machine: Machine, reqs: list):
    db.query(MachineSkillRequirement).filter(MachineSkillRequirement.machine_id == machine.id).delete()
    for r in reqs:
        db.add(MachineSkillRequirement(
            machine_id=machine.id,
            skill_id=r.skill_id,
            min_skill_level=r.min_skill_level,
            employees_required=r.employees_required,
        ))


@router.get("/", response_model=List[MachineOut])
def list_machines(
    status: str = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    q = db.query(Machine).filter(Machine.tenant_id == current_user.tenant_id)
    if status:
        q = q.filter(Machine.status == status)
    return q.order_by(Machine.name).all()


@router.get("/{machine_id}", response_model=MachineOut)
def get_machine(
    machine_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    m = db.query(Machine).filter(
        Machine.id == machine_id,
        Machine.tenant_id == current_user.tenant_id,
    ).first()
    if not m:
        raise HTTPException(status_code=404, detail="Machine not found")
    return m


@router.post(
    "/",
    response_model=MachineOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(check_plan_limit("machines", Machine))],
)
def create_machine(
    payload: MachineCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_operational()),
):
    data = payload.model_dump(exclude={"skill_requirements"})
    data["tenant_id"] = current_user.tenant_id
    machine = Machine(**data)
    db.add(machine)
    db.flush()
    _sync_skill_reqs(db, machine, payload.skill_requirements)
    db.commit()
    db.refresh(machine)
    return machine


@router.patch("/{machine_id}", response_model=MachineOut)
def update_machine(
    machine_id: int,
    payload: MachineUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_operational()),
):
    m = db.query(Machine).filter(
        Machine.id == machine_id,
        Machine.tenant_id == current_user.tenant_id,
    ).first()
    if not m:
        raise HTTPException(status_code=404, detail="Machine not found")
    data = payload.model_dump(exclude_unset=True, exclude={"skill_requirements"})
    for field, value in data.items():
        setattr(m, field, value)
    if payload.skill_requirements is not None:
        _sync_skill_reqs(db, m, payload.skill_requirements)
    db.commit()
    db.refresh(m)
    return m


@router.delete("/{machine_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_machine(
    machine_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_top_tier()),
):
    m = db.query(Machine).filter(
        Machine.id == machine_id,
        Machine.tenant_id == current_user.tenant_id,
    ).first()
    if not m:
        raise HTTPException(status_code=404, detail="Machine not found")
    db.delete(m)
    db.commit()
