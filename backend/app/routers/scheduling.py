"""
app/routers/scheduling.py — Prompt 1 API endpoints

Resources:  GET/POST /api/resources/   PUT/DELETE /api/resources/{id}
Jobs:       GET/POST /api/jobs-v2/     GET/PUT/DELETE /api/jobs-v2/{id}
Steps:      GET/POST /api/jobs-v2/{job_id}/steps/
            GET/PUT/DELETE /api/jobs-v2/{job_id}/steps/{step_id}
            PATCH /api/jobs-v2/{job_id}/steps/{step_id}/status

Note: router is mounted at /api so paths below are relative to that.
The prefix "jobs-v2" avoids collision with the existing /api/jobs router.
Rename to "jobs" once the old router is retired (or keep separate).
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
from app.routers.auth import get_current_user  # reuse existing auth

router = APIRouter()


def _current_tenant(current_user=Depends(get_current_user)) -> int:
    return current_user.tenant_id


def _step_out(step) -> StepResponse:
    return StepResponse.from_orm(step)


def _job_out(job) -> JobResponse:
    resp = JobResponse.from_orm(job)
    resp.steps = [StepResponse.from_orm(s) for s in job.steps]
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
