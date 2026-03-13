# app/routers/unavailability.py
"""
CRUD endpoints for employee leaves and machine downtimes.

Employee leaves:
  GET    /api/unavailability/employees/{employee_id}/leaves
  POST   /api/unavailability/employees/{employee_id}/leaves
  DELETE /api/unavailability/employees/{employee_id}/leaves/{leave_id}

Machine downtimes:
  GET    /api/unavailability/machines/{machine_id}/downtimes
  POST   /api/unavailability/machines/{machine_id}/downtimes
  DELETE /api/unavailability/machines/{machine_id}/downtimes/{downtime_id}
"""

from datetime import date
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.core.dependencies import get_current_user
from app.models.unavailability import EmployeeLeave, MachineDowntime

router = APIRouter()


# ── Pydantic schemas ──────────────────────────────────────────────────────────

class LeaveIn(BaseModel):
    start_date: date
    end_date:   date
    reason:     Optional[str] = None

class LeaveOut(BaseModel):
    id:          int
    employee_id: int
    start_date:  date
    end_date:    date
    reason:      Optional[str]
    class Config: from_attributes = True

class DowntimeIn(BaseModel):
    start_date: date
    end_date:   date
    reason:     Optional[str] = None

class DowntimeOut(BaseModel):
    id:         int
    machine_id: int
    start_date: date
    end_date:   date
    reason:     Optional[str]
    class Config: from_attributes = True


# ── Employee leaves ───────────────────────────────────────────────────────────

@router.get("/employees/{employee_id}/leaves", response_model=List[LeaveOut])
def list_leaves(
    employee_id: int,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user),
):
    return (
        db.query(EmployeeLeave)
        .filter(
            EmployeeLeave.employee_id == employee_id,
            EmployeeLeave.tenant_id   == current_user.tenant_id,
        )
        .order_by(EmployeeLeave.start_date)
        .all()
    )


@router.post("/employees/{employee_id}/leaves", response_model=LeaveOut, status_code=201)
def create_leave(
    employee_id: int,
    payload: LeaveIn,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user),
):
    if payload.end_date < payload.start_date:
        raise HTTPException(status_code=422, detail="end_date must be >= start_date")
    leave = EmployeeLeave(
        tenant_id   = current_user.tenant_id,
        employee_id = employee_id,
        start_date  = payload.start_date,
        end_date    = payload.end_date,
        reason      = payload.reason,
    )
    db.add(leave)
    db.commit()
    db.refresh(leave)
    return leave


@router.delete("/employees/{employee_id}/leaves/{leave_id}", status_code=204)
def delete_leave(
    employee_id: int,
    leave_id: int,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user),
):
    leave = db.query(EmployeeLeave).filter(
        EmployeeLeave.id          == leave_id,
        EmployeeLeave.employee_id == employee_id,
        EmployeeLeave.tenant_id   == current_user.tenant_id,
    ).first()
    if not leave:
        raise HTTPException(status_code=404, detail="Leave not found")
    db.delete(leave)
    db.commit()


# ── Machine downtimes ─────────────────────────────────────────────────────────

@router.get("/machines/{machine_id}/downtimes", response_model=List[DowntimeOut])
def list_downtimes(
    machine_id: int,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user),
):
    return (
        db.query(MachineDowntime)
        .filter(
            MachineDowntime.machine_id == machine_id,
            MachineDowntime.tenant_id  == current_user.tenant_id,
        )
        .order_by(MachineDowntime.start_date)
        .all()
    )


@router.post("/machines/{machine_id}/downtimes", response_model=DowntimeOut, status_code=201)
def create_downtime(
    machine_id: int,
    payload: DowntimeIn,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user),
):
    if payload.end_date < payload.start_date:
        raise HTTPException(status_code=422, detail="end_date must be >= start_date")
    downtime = MachineDowntime(
        tenant_id  = current_user.tenant_id,
        machine_id = machine_id,
        start_date = payload.start_date,
        end_date   = payload.end_date,
        reason     = payload.reason,
    )
    db.add(downtime)
    db.commit()
    db.refresh(downtime)
    return downtime


@router.delete("/machines/{machine_id}/downtimes/{downtime_id}", status_code=204)
def delete_downtime(
    machine_id: int,
    downtime_id: int,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user),
):
    downtime = db.query(MachineDowntime).filter(
        MachineDowntime.id         == downtime_id,
        MachineDowntime.machine_id == machine_id,
        MachineDowntime.tenant_id  == current_user.tenant_id,
    ).first()
    if not downtime:
        raise HTTPException(status_code=404, detail="Downtime not found")
    db.delete(downtime)
    db.commit()
