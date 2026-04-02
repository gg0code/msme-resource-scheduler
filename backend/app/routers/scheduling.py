"""
FILE PURPOSE
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
This file defines FastAPI REST endpoints for the scheduling system in ZetaOps Copilot,
providing CRUD operations for resources, jobs, and job steps. It was introduced in v4-dev
as part of the new scheduling engine architecture and serves as the HTTP API layer between
the React frontend and the core scheduling engine. This router is mounted at /api in main.py
and handles all tenant-scoped scheduling data operations.

WHAT THIS FILE DOES — step by step
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
1. Creates a FastAPI router instance for scheduling endpoints
2. Defines helper functions for tenant authentication and response serialization
3. Implements 5 resource endpoints: list, create, update, delete, with optional type filtering
4. Implements 5 job endpoints under /jobs-v2/ prefix: list, create, get, update, delete
5. Implements 6 job step endpoints: list, create, get, update, delete, plus status patch
6. All endpoints enforce tenant isolation by extracting tenant_id from JWT auth
7. Converts SQLAlchemy models to Pydantic response schemas before returning to client
8. Handles errors by converting ValueError exceptions to HTTP 422 and missing records to HTTP 404

KEY FUNCTIONS / CLASSES / COMPONENTS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Name         : _current_tenant
Type         : dependency function
Purpose      : FastAPI dependency that extracts the tenant_id from the current authenticated
               user's JWT token. Used by all endpoints to enforce tenant isolation per 
               design principle #2.
Parameters   : current_user (User model) - injected by get_current_user dependency
Returns      : int - the tenant_id of the authenticated user
Calls        : app.core.dependencies.get_current_user
DB/API       : None - just extracts field from User object
Side effects : None

Name         : _step_out
Type         : helper function
Purpose      : Converts a SQLAlchemy Step model instance to a StepResponse Pydantic schema.
               Centralizes the model-to-schema conversion logic for consistency.
Parameters   : step (Step model) - SQLAlchemy model instance from database
Returns      : StepResponse - Pydantic schema suitable for JSON serialization
Calls        : StepResponse.model_validate from app.schemas.scheduling
DB/API       : None
Side effects : None

Name         : _job_out
Type         : helper function
Purpose      : Converts a SQLAlchemy Job model instance to a JobResponse Pydantic schema,
               including nested conversion of all associated steps. Handles the complex
               job-with-steps serialization that multiple endpoints need.
Parameters   : job (Job model) - SQLAlchemy model instance with loaded steps relationship
Returns      : JobResponse - Pydantic schema with nested steps array
Calls        : JobResponse.model_validate, StepResponse.model_validate
DB/API       : None
Side effects : None

Name         : list_resources
Type         : FastAPI GET endpoint
Purpose      : Returns all resources for the current tenant, optionally filtered by resource
               type (EMPLOYEE or MACHINE). Supports the resource management UI in the frontend.
Parameters   : type (Optional[ResourceType]) - query parameter to filter by resource type,
               db (Session) - SQLAlchemy database session,
               tenant_id (int) - extracted from JWT via _current_tenant dependency
Returns      : List[ResourceResponse] - array of resource objects as JSON
Calls        : app.crud.scheduling.list_resources
DB/API       : Queries Resource table filtered by tenant_id and optional resource_type
Side effects : None

Name         : create_resource
Type         : FastAPI POST endpoint
Purpose      : Creates a new resource (employee or machine) for the current tenant. Validates
               the resource data and returns the created resource with generated ID.
Parameters   : data (ResourceCreate) - Pydantic schema with resource fields from request body,
               db (Session) - SQLAlchemy database session,
               tenant_id (int) - extracted from JWT via _current_tenant dependency
Returns      : ResourceResponse - the created resource object as JSON with HTTP 201 status
Calls        : app.crud.scheduling.create_resource
DB/API       : Inserts new row into Resource table with tenant_id
Side effects : Creates database record, may raise HTTPException 422 on validation error

Name         : update_resource
Type         : FastAPI PUT endpoint
Purpose      : Updates an existing resource for the current tenant. Validates tenant ownership
               and field constraints, returns the updated resource or 404 if not found.
Parameters   : resource_id (int) - path parameter identifying the resource to update,
               data (ResourceUpdate) - Pydantic schema with updated fields from request body,
               db (Session) - SQLAlchemy database session,
               tenant_id (int) - extracted from JWT via _current_tenant dependency
Returns      : ResourceResponse - the updated resource object as JSON
Calls        : app.crud.scheduling.update_resource
DB/API       : Updates Resource table row where id=resource_id AND tenant_id=tenant_id
Side effects : Modifies database record, may raise HTTPException 422/404 on error

Name         : delete_resource
Type         : FastAPI DELETE endpoint
Purpose      : Deletes a resource for the current tenant. Returns 204 No Content on success
               or 404 if the resource doesn't exist or belong to the tenant.
Parameters   : resource_id (int) - path parameter identifying the resource to delete,
               db (Session) - SQLAlchemy database session,
               tenant_id (int) - extracted from JWT via _current_tenant dependency
Returns      : None (HTTP 204 status code)
Calls        : app.crud.scheduling.delete_resource
DB/API       : Deletes from Resource table where id=resource_id AND tenant_id=tenant_id
Side effects : Removes database record, may raise HTTPException 404 if not found

Name         : list_jobs
Type         : FastAPI GET endpoint
Purpose      : Returns all jobs for the current tenant, optionally filtered by job status.
               Each job includes its nested steps. Used by the main scheduling dashboard.
Parameters   : status (Optional[SchedJobStatus]) - query parameter to filter by job status,
               db (Session) - SQLAlchemy database session,
               tenant_id (int) - extracted from JWT via _current_tenant dependency
Returns      : List[JobResponse] - array of job objects with nested steps as JSON
Calls        : app.crud.scheduling.list_jobs, _job_out helper function
DB/API       : Queries Job table with joined Step table, filtered by tenant_id and optional status
Side effects : None

Name
"""

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.scheduling import ResourceType, SchedJobStatus
from app.schemas.scheduling import (
    JobCreate, JobResponse, JobUpdate,
    ResourceCreate, ResourceResponse, ResourceUpdate,
    StepCreate, StepResponse, StepStatusUpdate, StepUpdate,
)
import app.crud.scheduling as crud
from app.core.dependencies import get_current_user  # reuse existing auth

router = APIRouter()


def _current_tenant(current_user=Depends(get_current_user)) -> int:
    return current_user.tenant_id


def _step_out(step) -> StepResponse:
    return StepResponse.model_validate(step)


def _job_out(job) -> JobResponse:
    resp = JobResponse.model_validate(job)
    resp.steps = [StepResponse.model_validate(s) for s in job.steps]
    return resp


# ─── Resources ────────────────────────────────────────────────────────────────

@router.get("/resources/", response_model=List[ResourceResponse], tags=["resources"])
def list_resources(
    type: Optional[ResourceType] = Query(None),
    db: Session = Depends(get_db),
    tenant_id: int = Depends(_current_tenant),
):
    return crud.list_resources(db, tenant_id, resource_type=type)


@router.post("/resources/", response_model=ResourceResponse, status_code=201, tags=["resources"])
def create_resource(
    data: ResourceCreate,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(_current_tenant),
):
    try:
        return crud.create_resource(db, tenant_id, data)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


@router.put("/resources/{resource_id}", response_model=ResourceResponse, tags=["resources"])
def update_resource(
    resource_id: int,
    data: ResourceUpdate,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(_current_tenant),
):
    try:
        result = crud.update_resource(db, tenant_id, resource_id, data)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    if result is None:
        raise HTTPException(status_code=404, detail="Resource not found")
    return result


@router.delete("/resources/{resource_id}", status_code=204, tags=["resources"])
def delete_resource(
    resource_id: int,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(_current_tenant),
):
    if not crud.delete_resource(db, tenant_id, resource_id):
        raise HTTPException(status_code=404, detail="Resource not found")


# ─── Jobs ─────────────────────────────────────────────────────────────────────

@router.get("/jobs-v2/", response_model=List[JobResponse], tags=["sched-jobs"])
def list_jobs(
    status: Optional[SchedJobStatus] = Query(None),
    db: Session = Depends(get_db),
    tenant_id: int = Depends(_current_tenant),
):
    jobs = crud.list_jobs(db, tenant_id, status=status)
    return [_job_out(j) for j in jobs]


@router.post("/jobs-v2/", response_model=JobResponse, status_code=201, tags=["sched-jobs"])
def create_job(
    data: JobCreate,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(_current_tenant),
):
    job = crud.create_job(db, tenant_id, data)
    return _job_out(job)


@router.get("/jobs-v2/{job_id}", response_model=JobResponse, tags=["sched-jobs"])
def get_job(
    job_id: int,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(_current_tenant),
):
    job = crud.get_job(db, tenant_id, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return _job_out(job)


@router.put("/jobs-v2/{job_id}", response_model=JobResponse, tags=["sched-jobs"])
def update_job(
    job_id: int,
    data: JobUpdate,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(_current_tenant),
):
    job = crud.update_job(db, tenant_id, job_id, data)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return _job_out(job)


@router.delete("/jobs-v2/{job_id}", status_code=204, tags=["sched-jobs"])
def delete_job(
    job_id: int,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(_current_tenant),
):
    if not crud.delete_job(db, tenant_id, job_id):
        raise HTTPException(status_code=404, detail="Job not found")


# ─── Steps ────────────────────────────────────────────────────────────────────

@router.get("/jobs-v2/{job_id}/steps/", response_model=List[StepResponse], tags=["sched-steps"])
def list_steps(
    job_id: int,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(_current_tenant),
):
    try:
        steps = crud.list_steps(db, tenant_id, job_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    return [_step_out(s) for s in steps]


@router.post("/jobs-v2/{job_id}/steps/", response_model=StepResponse, status_code=201, tags=["sched-steps"])
def create_step(
    job_id: int,
    data: StepCreate,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(_current_tenant),
):
    try:
        step = crud.create_step(db, tenant_id, job_id, data)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    return _step_out(step)


@router.get("/jobs-v2/{job_id}/steps/{step_id}", response_model=StepResponse, tags=["sched-steps"])
def get_step(
    job_id: int,
    step_id: int,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(_current_tenant),
):
    step = crud.get_step(db, tenant_id, step_id)
    if step is None or step.job_id != job_id:
        raise HTTPException(status_code=404, detail="Step not found")
    return _step_out(step)


@router.put("/jobs-v2/{job_id}/steps/{step_id}", response_model=StepResponse, tags=["sched-steps"])
def update_step(
    job_id: int,
    step_id: int,
    data: StepUpdate,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(_current_tenant),
):
    try:
        step = crud.update_step(db, tenant_id, step_id, data)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    if step is None or step.job_id != job_id:
        raise HTTPException(status_code=404, detail="Step not found")
    return _step_out(step)


@router.delete("/jobs-v2/{job_id}/steps/{step_id}", status_code=204, tags=["sched-steps"])
def delete_step(
    job_id: int,
    step_id: int,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(_current_tenant),
):
    step = crud.get_step(db, tenant_id, step_id)
    if step is None or step.job_id != job_id:
        raise HTTPException(status_code=404, detail="Step not found")
    crud.delete_step(db, tenant_id, step_id)


@router.patch(
    "/jobs-v2/{job_id}/steps/{step_id}/status",
    response_model=StepResponse,
    tags=["sched-steps"],
)
def patch_step_status(
    job_id: int,
    step_id: int,
    data: StepStatusUpdate,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(_current_tenant),
):
    try:
        step = crud.update_step_status(db, tenant_id, step_id, data.status)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    if step is None or step.job_id != job_id:
        raise HTTPException(status_code=404, detail="Step not found")
    return _step_out(step)
