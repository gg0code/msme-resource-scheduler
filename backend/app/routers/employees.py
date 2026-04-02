"""
```python
"""
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
backend/app/routers/employees.py — Employee Management API Router (v4-dev)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

FILE PURPOSE
This FastAPI router handles all HTTP endpoints for employee management in the ZetaOps Copilot workforce scheduling 
system. It was introduced in v1.1 with JWT authentication, tenant scoping, RBAC (Role-Based Access Control), and 
plan limit enforcement. This file sits in the API layer of our 3-tier architecture, receiving HTTP requests from 
the frontend React app, validating permissions and plan limits, then delegating to SQLAlchemy ORM models for 
database operations. All employee data is strictly scoped by tenant_id to ensure multi-tenant security isolation.

WHAT THIS FILE DOES — step by step
1. Defines a FastAPI APIRouter instance with 5 HTTP endpoints for employee CRUD operations
2. Imports all necessary dependencies: database session, ORM models, Pydantic schemas, auth functions, and plan limits
3. Defines a private helper function _sync_skills() that manages employee skill associations in the database
4. Implements GET / endpoint to list all employees for the current user's tenant, with optional status filtering
5. Implements GET /{employee_id} endpoint to retrieve a single employee by ID within the tenant scope
6. Implements POST / endpoint to create new employees with role-based permissions and plan limit checking
7. Implements PATCH /{employee_id} endpoint to update existing employees with proper tenant scoping
8. Implements DELETE /{employee_id} endpoint restricted to proprietor role only for employee deletion

KEY FUNCTIONS / CLASSES / COMPONENTS

Name         : _sync_skills
Type         : Private helper function
Purpose      : Synchronizes employee skill associations by completely replacing all existing skills with new ones. 
               This function ensures that skill updates are atomic and prevents orphaned skill records.
Parameters   : db (Session) - SQLAlchemy database session for executing queries
               employee (Employee) - The Employee ORM instance to sync skills for
               skills_data (list) - List of skill objects containing skill_id and skill_level
               tenant_id (int) - Tenant ID for ensuring all skill records are properly scoped
Returns      : None - This function performs side effects only and doesn't return data
Calls        : SQLAlchemy ORM methods (db.query, db.add) and EmployeeSkill model
DB/API       : Deletes all existing EmployeeSkill records for the employee, then inserts new ones
Side effects : Modifies EmployeeSkill table by deleting and inserting records

Name         : list_employees
Type         : FastAPI GET endpoint (/api/employees/)
Purpose      : Returns a list of all employees belonging to the current user's tenant, with optional filtering by 
               employee status. This endpoint is accessible to any authenticated user regardless of role.
Parameters   : status (str, optional) - Filter employees by their status field (active, inactive, etc.)
               db (Session) - Injected database session via FastAPI dependency
               current_user (User) - Injected current authenticated user via JWT token validation
Returns      : List[EmployeeOut] - Pydantic serialized list of employee objects matching the tenant and status filter
Calls        : SQLAlchemy query methods, Employee ORM model, and tenant scoping via current_user.tenant_id
DB/API       : Executes SELECT query on Employee table with tenant_id filter and optional status filter
Side effects : None - read-only operation that doesn't modify any data

Name         : get_employee
Type         : FastAPI GET endpoint (/api/employees/{employee_id})
Purpose      : Retrieves a single employee by their ID, but only if they belong to the current user's tenant. 
               Raises 404 if employee doesn't exist or belongs to a different tenant.
Parameters   : employee_id (int) - Path parameter specifying which employee to retrieve
               db (Session) - Injected database session via FastAPI dependency
               current_user (User) - Injected current authenticated user via JWT token validation
Returns      : EmployeeOut - Pydantic serialized employee object if found within tenant scope
Calls        : SQLAlchemy query methods and Employee ORM model for database lookup
DB/API       : Executes SELECT query on Employee table with both id and tenant_id filters
Side effects : None - read-only operation, but raises HTTPException if employee not found

Name         : create_employee
Type         : FastAPI POST endpoint (/api/employees/)
Purpose      : Creates a new employee record with associated skills, but only for users with scheduler or proprietor 
               roles. Enforces plan limits to prevent free plan users from exceeding their employee quota.
Parameters   : payload (EmployeeCreate) - Pydantic schema containing employee data and skills list
               db (Session) - Injected database session via FastAPI dependency
               current_user (User) - Injected user with scheduler+ role verification via require_role dependency
Returns      : EmployeeOut - Pydantic serialized newly created employee object with database-generated ID
Calls        : Employee ORM constructor, _sync_skills helper function, and plan limit checking via dependency
DB/API       : Inserts new Employee record, then calls _sync_skills to insert associated EmployeeSkill records
Side effects : Creates database records in both Employee and EmployeeSkill tables, commits transaction

Name         : update_employee
Type         : FastAPI PATCH endpoint (/api/employees/{employee_id})
Purpose      : Updates an existing employee's data and optionally their skills, but only for scheduler+ roles and 
               only within the user's tenant. Uses PATCH semantics to update only provided fields.
Parameters   : employee_id (int) - Path parameter specifying which employee to update
               payload (EmployeeUpdate) - Pydantic schema with optional fields to update
               db (Session) - Injected database session via FastAPI dependency
               current_user (User) - Injected user with scheduler+ role verification via require_role dependency
Returns      : EmployeeOut - Pydantic serialized updated employee object reflecting all changes
Calls        : SQLAlchemy query and update methods, _sync_skills helper if skills are provided
DB/API       : Updates Employee record fields, optionally replaces all EmployeeSkill associations
Side effects : Modifies Employee table record, potentially modifies EmployeeSkill table if skills included

Name         : delete_employee
Type         : FastAPI DELETE endpoint (/api/employees/{employee_id})
Purpose      : Permanently deletes an employee record from the database, but only for proprietor role users and 
               only within their tenant scope. This is the most restrictive endpoint due to data loss implications.
Parameters   : employee_id (int) - Path parameter specifying which employee to delete
               db (Session) - Injected database session via FastAPI dependency
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List

from app.database import get_db
from app.models.employee import Employee, EmployeeSkill
from app.schemas.employee import EmployeeCreate, EmployeeUpdate, EmployeeOut
from app.core.dependencies import get_current_user, require_role
from app.core.plan_limits import check_plan_limit
from app.models.auth import User

router = APIRouter()


def _sync_skills(db: Session, employee: Employee, skills_data: list, tenant_id: int):
    db.query(EmployeeSkill).filter(EmployeeSkill.employee_id == employee.id).delete()
    for s in skills_data:
        db.add(EmployeeSkill(tenant_id=tenant_id, employee_id=employee.id, skill_id=s.skill_id, skill_level=s.skill_level))


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
    current_user: User = Depends(require_role("proprietor", "scheduler")),
):
    data = payload.model_dump(exclude={"skills"})
    data["tenant_id"] = current_user.tenant_id
    emp = Employee(**data)
    db.add(emp)
    db.flush()
    _sync_skills(db, emp, payload.skills, current_user.tenant_id)
    db.commit()
    db.refresh(emp)
    return emp


@router.patch("/{employee_id}", response_model=EmployeeOut)
def update_employee(
    employee_id: int,
    payload: EmployeeUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("proprietor", "scheduler")),
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
        _sync_skills(db, emp, payload.skills, current_user.tenant_id)
    db.commit()
    db.refresh(emp)
    return emp


@router.delete("/{employee_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_employee(
    employee_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("proprietor")),
):
    emp = db.query(Employee).filter(
        Employee.id == employee_id,
        Employee.tenant_id == current_user.tenant_id,
    ).first()
    if not emp:
        raise HTTPException(status_code=404, detail="Employee not found")
    db.delete(emp)
    db.commit()
