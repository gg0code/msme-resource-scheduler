"""
routers/skills.py — V1.1
Added: JWT auth, tenant_id scoping, RBAC, plan limit enforcement
  GET    — any authenticated user
  POST   — proprietor only (+ free plan: max 20 skills)
  PATCH  — proprietor only
  DELETE — proprietor only
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List

from app.database import get_db
from app.models.skill import Skill
from app.schemas.skill import SkillCreate, SkillUpdate, SkillOut
from app.core.dependencies import get_current_user, require_top_tier
from app.core.plan_limits import check_plan_limit
from app.models.auth import User

router = APIRouter()


@router.get("/", response_model=List[SkillOut])
def list_skills(
    active_only: bool = False,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    q = db.query(Skill).filter(Skill.tenant_id == current_user.tenant_id)
    if active_only:
        q = q.filter(Skill.is_active == True)
    return q.order_by(Skill.name).all()


@router.get("/{skill_id}", response_model=SkillOut)
def get_skill(
    skill_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    skill = db.query(Skill).filter(
        Skill.id == skill_id,
        Skill.tenant_id == current_user.tenant_id,
    ).first()
    if not skill:
        raise HTTPException(status_code=404, detail="Skill not found")
    return skill


@router.post(
    "/",
    response_model=SkillOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(check_plan_limit("skills", Skill))],
)
def create_skill(
    payload: SkillCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_top_tier()),
):
    existing = db.query(Skill).filter(
        Skill.name == payload.name,
        Skill.tenant_id == current_user.tenant_id,
    ).first()
    if existing:
        raise HTTPException(status_code=400, detail="Skill with this name already exists")
    skill = Skill(**payload.model_dump(), tenant_id=current_user.tenant_id)
    db.add(skill)
    db.commit()
    db.refresh(skill)
    return skill


@router.patch("/{skill_id}", response_model=SkillOut)
def update_skill(
    skill_id: int,
    payload: SkillUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_top_tier()),
):
    skill = db.query(Skill).filter(
        Skill.id == skill_id,
        Skill.tenant_id == current_user.tenant_id,
    ).first()
    if not skill:
        raise HTTPException(status_code=404, detail="Skill not found")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(skill, field, value)
    db.commit()
    db.refresh(skill)
    return skill


@router.delete("/{skill_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_skill(
    skill_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_top_tier()),
):
    skill = db.query(Skill).filter(
        Skill.id == skill_id,
        Skill.tenant_id == current_user.tenant_id,
    ).first()
    if not skill:
        raise HTTPException(status_code=404, detail="Skill not found")
    db.delete(skill)
    db.commit()
