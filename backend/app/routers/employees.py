"""
routers/employees.py — V1.1
Added: JWT auth, tenant_id scoping, RBAC, plan limit enforcement
  GET    — any authenticated user
  POST   — scheduler+ (+ free plan: max 10 employees)
  PATCH  — scheduler+
  DELETE — proprietor only
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List

from app.database import get_db
from app.models.employee import Employee, EmployeeSkill
from app.schemas.employee import EmployeeCreate, EmployeeUpdate, EmployeeOut
from app.core.dependencies import get_current_user, require_operational, require_top_tier
from app.core.plan_limits import check_plan_limit
from app.models.auth import User

router = APIRouter()


def _sync_skills(db: Session, employee: Employee, skills_data: list):
    # tenant_id must be carried on every join-table row (CLAUDE.md rule 1).
    # employee_skills.tenant_id is NOT NULL in Postgres; SQLite did not enforce
    # this in unit tests, which masked the bug until v6.3.10's primary-skill
    # picker started attaching a skill on every Employee create.
    db.query(EmployeeSkill).filter(EmployeeSkill.employee_id == employee.id).delete()
    for s in skills_data:
        db.add(EmployeeSkill(
            tenant_id=employee.tenant_id,
            employee_id=employee.id,
            skill_id=s.skill_id,
            skill_level=s.skill_level,
        ))


@router.get("/", response_model=List[EmployeeOut])
def list_employees(
    status: str = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    q = db.query(Employee).filter(Employee.tenant_id == current_user.tenant_id)
    if status:
        q = q.filter(Employee.status == status)
    return q.order_by(Employee.full_name).all()


@router.get("/{employee_id}", response_model=EmployeeOut)
def get_employee(
    employee_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    emp = db.query(Employee).filter(
        Employee.id == employee_id,
        Employee.tenant_id == current_user.tenant_id,
    ).first()
    if not emp:
        raise HTTPException(status_code=404, detail="Employee not found")
    return emp


@router.post(
    "/",
    response_model=EmployeeOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(check_plan_limit("employees", Employee))],
)
def create_employee(
    payload: EmployeeCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_operational()),
):
    data = payload.model_dump(exclude={"skills"})
    data["tenant_id"] = current_user.tenant_id
    emp = Employee(**data)
    db.add(emp)
    db.flush()
    _sync_skills(db, emp, payload.skills)
    db.commit()
    db.refresh(emp)
    return emp


@router.patch("/{employee_id}", response_model=EmployeeOut)
def update_employee(
    employee_id: int,
    payload: EmployeeUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_operational()),
):
    emp = db.query(Employee).filter(
        Employee.id == employee_id,
        Employee.tenant_id == current_user.tenant_id,
    ).first()
    if not emp:
        raise HTTPException(status_code=404, detail="Employee not found")
    data = payload.model_dump(exclude_unset=True, exclude={"skills"})
    for field, value in data.items():
        setattr(emp, field, value)
    if payload.skills is not None:
        _sync_skills(db, emp, payload.skills)
    db.commit()
    db.refresh(emp)
    return emp


@router.delete("/{employee_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_employee(
    employee_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_top_tier()),
):
    emp = db.query(Employee).filter(
        Employee.id == employee_id,
        Employee.tenant_id == current_user.tenant_id,
    ).first()
    if not emp:
        raise HTTPException(status_code=404, detail="Employee not found")
    db.delete(emp)
    db.commit()
