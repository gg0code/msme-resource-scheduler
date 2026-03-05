"""
routers/import_csv.py — V1.1
Added: JWT auth, RBAC
  GET  template — any authenticated user
  POST import   — scheduler+
"""

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.database import get_db
from app.utils.csv_import import import_employees, import_machines, import_skills, TEMPLATES
from app.core.dependencies import get_current_user, require_role
from app.models.auth import User

router = APIRouter()


@router.get("/template/{resource}")
def download_template(
    resource: str,
    current_user: User = Depends(get_current_user),
):
    if resource not in TEMPLATES:
        raise HTTPException(status_code=404, detail=f"No template for '{resource}'. Use: employees, machines, skills")
    filename, content = TEMPLATES[resource]
    return Response(
        content=content,
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@router.post("/employees")
async def upload_employees(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("proprietor", "scheduler")),
):
    if not file.filename.endswith(".csv"):
        raise HTTPException(status_code=400, detail="Only .csv files are accepted")
    content = await file.read()
    result = import_employees(db, content, tenant_id=current_user.tenant_id)
    return result


@router.post("/machines")
async def upload_machines(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("proprietor", "scheduler")),
):
    if not file.filename.endswith(".csv"):
        raise HTTPException(status_code=400, detail="Only .csv files are accepted")
    content = await file.read()
    result = import_machines(db, content, tenant_id=current_user.tenant_id)
    return result


@router.post("/skills")
async def upload_skills(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("proprietor", "scheduler")),
):
    if not file.filename.endswith(".csv"):
        raise HTTPException(status_code=400, detail="Only .csv files are accepted")
    content = await file.read()
    result = import_skills(db, content, tenant_id=current_user.tenant_id)
    return result
