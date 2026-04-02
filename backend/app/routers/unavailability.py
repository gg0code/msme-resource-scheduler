"""
```python
"""
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
UNAVAILABILITY ROUTER - Employee Leave & Machine Downtime CRUD Operations
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

FILE PURPOSE
This FastAPI router provides REST API endpoints for managing employee unavailability 
(leaves/vacation) and machine downtime periods in the ZetaOps Copilot scheduling 
system. Introduced in v4.x production branch, it sits in the API layer between 
the frontend scheduling UI and the database models, enabling users to mark when 
employees or machines are unavailable so the scheduler can avoid assigning work 
during these periods.

WHAT THIS FILE DOES — step by step
1. Defines Pydantic schemas for leave/downtime input validation and output serialization
2. Implements GET /api/unavailability/employees/{employee_id}/leaves to list all leaves for an employee
3. Implements POST /api/unavailability/employees/{employee_id}/leaves to create new employee leave periods
4. Implements DELETE /api/unavailability/employees/{employee_id}/leaves/{leave_id} to remove leave periods
5. Implements GET /api/unavailability/machines/{machine_id}/downtimes to list all downtimes for a machine
6. Implements POST /api/unavailability/machines/{machine_id}/downtimes to create new machine downtime periods
7. Implements DELETE /api/unavailability/machines/{machine_id}/downtimes/{downtime_id} to remove downtimes
8. All operations enforce tenant isolation by filtering on current_user.tenant_id

KEY FUNCTIONS / CLASSES / COMPONENTS

Name         : LeaveIn
Type         : Pydantic model class
Purpose      : Validates incoming employee leave request data from frontend. Ensures start_date, 
               end_date are proper date objects and reason is optional string.
Parameters   : start_date (date) - first day of leave, end_date (date) - last day of leave, 
               reason (Optional[str]) - human readable explanation for leave
Returns      : N/A (data validation class)
Calls        : N/A (Pydantic validation)
DB/API       : None
Side effects : Raises validation errors if dates are malformed

Name         : LeaveOut
Type         : Pydantic model class
Purpose      : Serializes EmployeeLeave database records to JSON for API responses. Configured 
               with from_attributes=True to work with SQLAlchemy ORM objects.
Parameters   : id (int), employee_id (int), start_date (date), end_date (date), reason (Optional[str])
Returns      : N/A (serialization class)
Calls        : N/A (Pydantic serialization)
DB/API       : None
Side effects : None

Name         : DowntimeIn
Type         : Pydantic model class
Purpose      : Validates incoming machine downtime request data from frontend. Identical structure 
               to LeaveIn but semantically different (machines vs employees).
Parameters   : start_date (date) - first day of downtime, end_date (date) - last day of downtime, 
               reason (Optional[str]) - explanation for downtime (maintenance, repair, etc)
Returns      : N/A (data validation class)
Calls        : N/A (Pydantic validation)
DB/API       : None
Side effects : Raises validation errors if dates are malformed

Name         : DowntimeOut
Type         : Pydantic model class
Purpose      : Serializes MachineDowntime database records to JSON for API responses. Configured 
               with from_attributes=True to work with SQLAlchemy ORM objects.
Parameters   : id (int), machine_id (int), start_date (date), end_date (date), reason (Optional[str])
Returns      : N/A (serialization class)
Calls        : N/A (Pydantic serialization)
DB/API       : None
Side effects : None

Name         : list_leaves
Type         : FastAPI endpoint function
Purpose      : Retrieves all leave periods for a specific employee within the current user's tenant. 
               Returns leaves sorted by start_date chronologically for easy frontend display.
Parameters   : employee_id (int) - target employee ID from URL path, db (Session) - database session 
               via dependency injection, current_user - authenticated user object via dependency
Returns      : List[LeaveOut] - all leave records for the employee as JSON array
Calls        : get_db(), get_current_user() via FastAPI dependencies
DB/API       : SELECT query on EmployeeLeave table with tenant_id and employee_id filters
Side effects : None (read-only operation)

Name         : create_leave
Type         : FastAPI endpoint function
Purpose      : Creates a new employee leave period in the database. Validates that end_date is not 
               before start_date and automatically assigns the current user's tenant_id for security.
Parameters   : employee_id (int) - target employee from URL, payload (LeaveIn) - validated leave data,
               db (Session) - database session, current_user - authenticated user object
Returns      : LeaveOut - newly created leave record with generated ID
Calls        : get_db(), get_current_user() via FastAPI dependencies
DB/API       : INSERT into EmployeeLeave table, followed by COMMIT and REFRESH
Side effects : Creates new database record, raises HTTPException 422 if end_date < start_date

Name         : delete_leave
Type         : FastAPI endpoint function
Purpose      : Permanently removes an employee leave period from the database. Verifies the leave 
               exists, belongs to the specified employee, and is within the user's tenant before deletion.
Parameters   : employee_id (int) - employee ID from URL, leave_id (int) - leave record ID from URL,
               db (Session) - database session, current_user - authenticated user object
Returns      : None (HTTP 204 No Content status)
Calls        : get_db(), get_current_user() via FastAPI dependencies
DB/API       : SELECT to find leave record, DELETE if found, COMMIT transaction
Side effects : Deletes database record, raises HTTPException 404 if leave not found

Name         : list_downtimes
Type         : FastAPI endpoint function
Purpose      : Retrieves all downtime periods for a specific machine within the current user's tenant.
               Returns downtimes sorted by start_date chronologically for easy frontend display.
Parameters   : machine_id (int) - target machine ID from URL path, db (Session) - database session
               via dependency injection, current_user - authenticated user object via dependency
Returns      : List[DowntimeOut] - all downtime records for the machine as JSON array
Calls        : get_db(), get_current_user() via FastAPI dependencies
DB/API       : SELECT query on MachineDowntime table with tenant_id and machine_id filters
Side effects : None (read-only operation)

Name         : create_downtime
Type         : FastAPI endpoint function
Purpose      : Creates a new machine downtime period in the database
"""

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
    model_config = {"from_attributes": True}

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
    model_config = {"from_attributes": True}


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
