# app/routers/unavailability.py - Version 1.0
# Branch: both
#
# FILE PURPOSE
# REST endpoints for managing employee leaves and machine downtime periods.
# These feed into the availability engine to block resources on specific dates.
# Layer: router
#
# WHAT THIS FILE DOES
# 1. GET/POST /unavailability/employees/{id}/leaves        - list and create leaves
# 2. DELETE   /unavailability/employees/{id}/leaves/{lid} - delete a leave
# 3. GET/POST /unavailability/machines/{id}/downtimes      - list and create downtimes
# 4. DELETE   /unavailability/machines/{id}/downtimes/{did} - delete a downtime
#
# WHO CALLS THIS FILE
# - app/main.py - registered at prefix /api
#   final paths: /api/unavailability/employees/{id}/leaves etc.
# - frontend UnavailabilityPanel.tsx
#
# INTERN NOTES
# - All queries filter by tenant_id - never cross-tenant
# - Models live in app/models/unavailability.py (EmployeeLeave, MachineDowntime)
# - Tables: employee_leaves, machine_downtimes (created in migration 020)
# - start_date must be <= end_date - validated in schema

from datetime import date
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from pydantic import BaseModel, ConfigDict, field_validator
from typing import Optional

from app.database import get_db
from app.core.dependencies import get_current_user, require_operational
from app.models.auth import User
from app.models.unavailability import EmployeeLeave, MachineDowntime
from app.models.employee import Employee
from app.models.machine import Machine

router = APIRouter()


# -- Schemas ------------------------------------------------------------------

class LeaveIn(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    start_date: date
    end_date:   date
    reason:     Optional[str] = None

    @field_validator("end_date")
    @classmethod
    def end_after_start(cls, v: date, info) -> date:
        start = info.data.get("start_date")
        if start and v < start:
            raise ValueError("end_date must be on or after start_date")
        return v


class LeaveOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id:          int
    employee_id: int
    start_date:  date
    end_date:    date
    reason:      Optional[str] = None


class DowntimeIn(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    start_date: date
    end_date:   date
    reason:     Optional[str] = None

    @field_validator("end_date")
    @classmethod
    def end_after_start(cls, v: date, info) -> date:
        start = info.data.get("start_date")
        if start and v < start:
            raise ValueError("end_date must be on or after start_date")
        return v


class DowntimeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id:         int
    machine_id: int
    start_date: date
    end_date:   date
    reason:     Optional[str] = None


# -- Employee Leaves ----------------------------------------------------------

@router.get("/unavailability/employees/{employee_id}/leaves")
def list_employee_leaves(
    employee_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List all leave periods for an employee. Scoped to tenant."""
    emp = db.query(Employee).filter(
        Employee.id == employee_id,
        Employee.tenant_id == current_user.tenant_id,
    ).first()
    if not emp:
        raise HTTPException(status_code=404, detail="Employee not found")

    rows = db.query(EmployeeLeave).filter(
        EmployeeLeave.employee_id == employee_id,
        EmployeeLeave.tenant_id == current_user.tenant_id,
    ).order_by(EmployeeLeave.start_date).all()

    return [LeaveOut.model_validate(r) for r in rows]


@router.post(
    "/unavailability/employees/{employee_id}/leaves",
    status_code=status.HTTP_201_CREATED,
)
def create_employee_leave(
    employee_id: int,
    payload: LeaveIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_operational()),
):
    """Create a leave period for an employee."""
    emp = db.query(Employee).filter(
        Employee.id == employee_id,
        Employee.tenant_id == current_user.tenant_id,
    ).first()
    if not emp:
        raise HTTPException(status_code=404, detail="Employee not found")

    leave = EmployeeLeave(
        tenant_id=current_user.tenant_id,
        employee_id=employee_id,
        start_date=payload.start_date,
        end_date=payload.end_date,
        reason=payload.reason,
    )
    db.add(leave)
    db.commit()
    db.refresh(leave)
    return LeaveOut.model_validate(leave)


@router.delete(
    "/unavailability/employees/{employee_id}/leaves/{leave_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_employee_leave(
    employee_id: int,
    leave_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_operational()),
):
    """Delete a leave period. Verifies tenant ownership."""
    leave = db.query(EmployeeLeave).filter(
        EmployeeLeave.id == leave_id,
        EmployeeLeave.employee_id == employee_id,
        EmployeeLeave.tenant_id == current_user.tenant_id,
    ).first()
    if not leave:
        raise HTTPException(status_code=404, detail="Leave not found")

    db.delete(leave)
    db.commit()


# -- Machine Downtimes --------------------------------------------------------

@router.get("/unavailability/machines/{machine_id}/downtimes")
def list_machine_downtimes(
    machine_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List all downtime periods for a machine. Scoped to tenant."""
    machine = db.query(Machine).filter(
        Machine.id == machine_id,
        Machine.tenant_id == current_user.tenant_id,
    ).first()
    if not machine:
        raise HTTPException(status_code=404, detail="Machine not found")

    rows = db.query(MachineDowntime).filter(
        MachineDowntime.machine_id == machine_id,
        MachineDowntime.tenant_id == current_user.tenant_id,
    ).order_by(MachineDowntime.start_date).all()

    return [DowntimeOut.model_validate(r) for r in rows]


@router.post(
    "/unavailability/machines/{machine_id}/downtimes",
    status_code=status.HTTP_201_CREATED,
)
def create_machine_downtime(
    machine_id: int,
    payload: DowntimeIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_operational()),
):
    """Create a downtime period for a machine."""
    machine = db.query(Machine).filter(
        Machine.id == machine_id,
        Machine.tenant_id == current_user.tenant_id,
    ).first()
    if not machine:
        raise HTTPException(status_code=404, detail="Machine not found")

    downtime = MachineDowntime(
        tenant_id=current_user.tenant_id,
        machine_id=machine_id,
        start_date=payload.start_date,
        end_date=payload.end_date,
        reason=payload.reason,
    )
    db.add(downtime)
    db.commit()
    db.refresh(downtime)
    return DowntimeOut.model_validate(downtime)


@router.delete(
    "/unavailability/machines/{machine_id}/downtimes/{downtime_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_machine_downtime(
    machine_id: int,
    downtime_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_operational()),
):
    """Delete a downtime period. Verifies tenant ownership."""
    downtime = db.query(MachineDowntime).filter(
        MachineDowntime.id == downtime_id,
        MachineDowntime.machine_id == machine_id,
        MachineDowntime.tenant_id == current_user.tenant_id,
    ).first()
    if not downtime:
        raise HTTPException(status_code=404, detail="Downtime not found")

    db.delete(downtime)
    db.commit()
