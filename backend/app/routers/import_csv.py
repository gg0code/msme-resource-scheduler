"""
```python
"""
FILE PURPOSE
This file defines FastAPI endpoints for CSV and Excel file imports in the ZetaOps Copilot
scheduling system. It handles bulk importing of employees, machines, and skills data from
uploaded files, with proper authentication, role-based access control, and feature flag
gating. Introduced in v3.7 on the v4-dev branch, it sits in the API router layer and
delegates actual import logic to the csv_import utility module.

WHAT THIS FILE DOES — step by step
1. Creates a FastAPI APIRouter instance for handling CSV/Excel import endpoints
2. Defines GET endpoints for downloading CSV and Excel templates for employees, machines, and skills
3. Defines POST endpoints for uploading and importing employee, machine, and skills data files
4. Guards all endpoints with feature flag checks using require_feature("csv_import")
5. Enforces authentication on template downloads (any authenticated user can access)
6. Enforces role-based access control on imports (only proprietor and scheduler roles allowed)
7. Validates file extensions (.csv for all imports, .xlsx supported for employees and machines)
8. Passes uploaded file content and tenant context to utility import functions
9. Returns appropriate HTTP responses with file attachments for templates or import results

KEY FUNCTIONS / CLASSES / COMPONENTS

Name         : download_template
Type         : FastAPI endpoint (GET /template/{resource})
Purpose      : Downloads CSV templates for bulk data import. Provides pre-formatted CSV files
               with correct headers and example data that users can fill out before importing.
Parameters   : resource (str) - the type of template to download (employees/machines/skills)
               current_user (User) - authenticated user from JWT token dependency injection
Returns      : FastAPI Response with CSV file attachment containing template data and appropriate headers
Calls        : require_feature() from app.utils.feature_guard, accesses TEMPLATES dict from app.utils.csv_import
DB/API       : No database queries, reads template data from in-memory TEMPLATES constant
Side effects : None, purely read-only operation that serves file downloads

Name         : download_xlsx_template
Type         : FastAPI endpoint (GET /template-xlsx/{resource})
Purpose      : Downloads Excel (.xlsx) templates for bulk data import. Similar to CSV templates
               but in Excel format which some users prefer for data entry and validation.
Parameters   : resource (str) - the type of template to download (employees/machines only)
               current_user (User) - authenticated user from JWT token dependency injection
Returns      : FastAPI Response with Excel file attachment containing template data and Excel MIME type
Calls        : require_feature() from app.utils.feature_guard, accesses XLSX_TEMPLATES dict from app.utils.csv_import
DB/API       : No database queries, reads template data from in-memory XLSX_TEMPLATES constant
Side effects : None, purely read-only operation that serves Excel file downloads

Name         : upload_employees
Type         : FastAPI endpoint (POST /employees)
Purpose      : Handles bulk import of employee data from uploaded CSV or Excel files. Validates
               file format, reads content, and delegates to import utility function while ensuring
               proper tenant scoping and role-based access control.
Parameters   : file (UploadFile) - the uploaded CSV or Excel file containing employee data
               db (Session) - SQLAlchemy database session for persistence operations
               current_user (User) - authenticated user with proprietor or scheduler role
Returns      : Import result dictionary containing success/failure counts and error messages from import_employees()
Calls        : require_feature(), require_role(), import_employees() from app.utils.csv_import
DB/API       : Passes database session to import_employees() which performs bulk Employee table inserts
Side effects : Creates new Employee records in database, scoped to current user's tenant_id

Name         : upload_machines
Type         : FastAPI endpoint (POST /machines)
Purpose      : Handles bulk import of machine data from uploaded CSV or Excel files. Similar to
               employee import but for manufacturing equipment and machinery data with proper
               validation and tenant isolation.
Parameters   : file (UploadFile) - the uploaded CSV or Excel file containing machine data
               db (Session) - SQLAlchemy database session for persistence operations
               current_user (User) - authenticated user with proprietor or scheduler role
Returns      : Import result dictionary containing success/failure counts and error messages from import_machines()
Calls        : require_feature(), require_role(), import_machines() from app.utils.csv_import
DB/API       : Passes database session to import_machines() which performs bulk Machine table inserts
Side effects : Creates new Machine records in database, scoped to current user's tenant_id

Name         : upload_skills
Type         : FastAPI endpoint (POST /skills)
Purpose      : Handles bulk import of skills data from uploaded CSV files. Note that skills import
               only supports CSV format (not Excel) and manages skill definitions and employee-skill
               associations for scheduling optimization.
Parameters   : file (UploadFile) - the uploaded CSV file containing skills data
               db (Session) - SQLAlchemy database session for persistence operations
               current_user (User) - authenticated user with proprietor or scheduler role
Returns      : Import result dictionary containing success/failure counts and error messages from import_skills()
Calls        : require_feature(), require_role(), import_skills() from app.utils.csv_import
DB/API       : Passes database session to import_skills() which performs bulk Skill and EmployeeSkill table operations
Side effects : Creates new Skill records and EmployeeSkill associations in database, scoped to current user's tenant_id

WHO CALLS THIS FILE
This router is registered in backend/app/main.py and mounted with the /api/import prefix.
Frontend components in frontend/src/pages/ that handle bulk data import features call these
endpoints through API functions in frontend/src/api/ files. The main.py file includes this
router via app.include_router(import_csv.router, prefix="/api/import", tags=["import"]).

IMPORTS EXPLAINED
fastapi.APIRouter: Creates the router instance that groups related endpoints together for organization.
fastapi.Depends: Enables dependency injection for database sessions, authentication, and authorization.
fastapi.HTTPException: Provides structured HTTP error responses with proper status codes and messages.
fastapi.UploadFile and fastapi.File: Handle multipart file upload parsing and validation from HTTP requests.
fastapi.responses.Response: Creates custom HTTP responses with file attachments and appropriate headers.
sqlalchemy.orm.Session: Database session type for SQLAlchemy ORM operations and transaction management.
app.database.get_db: Dependency that provides database session instances with proper connection pooling.
app.utils.csv_import: Contains the actual import logic functions and template data constants.
app.core.dependencies: Provides authentication and authorization dependency functions.
app.models.auth.User: SQLAlchemy model representing authenticated users with tenant associations.
app.utils.feature_guard.require_feature: Enforces feature flag checks to gate optional functionality.

INTERN NOTES
- Easiest thing to break: Forgetting to check the feature flag guard return value - if require_feature() returns a response, you must return it immediately to show the warm disabled message
- Non-obvious design decision: Skills import only supports CSV while employees/machines support both CSV and Excel because skills data structure is simpler and doesn't benefit from Excel features
- Most common mistake: Not validating file extensions properly or allowing uploads without proper role checks, which could lead to security issues or data corruption
- Design principle implemented: Principle #8 (Feature flags gate all optional features) - every endpoint checks the csv_import feature flag before proceeding
- What to check if behaving unexpectedly: Verify the csv_import feature flag is enabled in FEATURE_FLAGS, check that user has proprietor or scheduler role, and ensure uploaded
"""

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.database import get_db
from app.utils.csv_import import import_employees, import_machines, import_skills, TEMPLATES, XLSX_TEMPLATES
from app.core.dependencies import get_current_user, require_role
from app.models.auth import User
from app.utils.feature_guard import require_feature

router = APIRouter()


@router.get("/template/{resource}")
def download_template(
    resource: str,
    current_user: User = Depends(get_current_user),
):
    # V3.7 — feature flag guard
    guard = require_feature("csv_import")
    if guard:
        return guard

    if resource not in TEMPLATES:
        raise HTTPException(status_code=404, detail=f"No template for '{resource}'. Use: employees, machines, skills")
    filename, content = TEMPLATES[resource]
    return Response(
        content=content,
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@router.get("/template-xlsx/{resource}")
def download_xlsx_template(
    resource: str,
    current_user: User = Depends(get_current_user),
):
    # V3.7 — feature flag guard
    guard = require_feature("csv_import")
    if guard:
        return guard

    if resource not in XLSX_TEMPLATES:
        raise HTTPException(status_code=404, detail=f"No xlsx template for '{resource}'. Use: employees, machines")
    filename, content_bytes = XLSX_TEMPLATES[resource]
    return Response(
        content=content_bytes,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@router.post("/employees")
async def upload_employees(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("proprietor", "scheduler")),
):
    # V3.7 — feature flag guard
    guard = require_feature("csv_import")
    if guard:
        return guard

    if not (file.filename.endswith(".csv") or file.filename.endswith(".xlsx")):
        raise HTTPException(status_code=400, detail="Only .csv or .xlsx files are accepted")
    content = await file.read()
    result = import_employees(db, content, tenant_id=current_user.tenant_id, filename=file.filename)
    return result


@router.post("/machines")
async def upload_machines(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("proprietor", "scheduler")),
):
    # V3.7 — feature flag guard
    guard = require_feature("csv_import")
    if guard:
        return guard

    if not (file.filename.endswith(".csv") or file.filename.endswith(".xlsx")):
        raise HTTPException(status_code=400, detail="Only .csv or .xlsx files are accepted")
    content = await file.read()
    result = import_machines(db, content, tenant_id=current_user.tenant_id, filename=file.filename)
    return result


@router.post("/skills")
async def upload_skills(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("proprietor", "scheduler")),
):
    # V3.7 — feature flag guard
    guard = require_feature("csv_import")
    if guard:
        return guard

    if not file.filename.endswith(".csv"):
        raise HTTPException(status_code=400, detail="Only .csv files are accepted")
    content = await file.read()
    result = import_skills(db, content, tenant_id=current_user.tenant_id)
    return result
