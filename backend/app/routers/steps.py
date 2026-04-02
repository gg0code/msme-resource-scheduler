"""
```python
"""
backend/app/routers/steps.py — Step Intelligence Router (v3.7+)

FILE PURPOSE
This FastAPI router provides complete CRUD operations for job steps and their resource assignments.
It was introduced in v3.7 as part of the Step Intelligence feature, allowing users to break down
jobs into sequential steps with individual resource requirements and status tracking. This sits
in the API layer of our 3-tier architecture, handling HTTP requests for step management and
delegating business logic to the database layer via SQLAlchemy ORM models.

WHAT THIS FILE DOES — step by step
1. Defines valid step status transitions and step/resource types as constants
2. Creates Pydantic schemas for request/response validation (StepCreate, StepUpdate, etc.)
3. Implements serializer functions to convert ORM models to JSON dictionaries
4. Provides guard functions to ensure job/step belong to the current user's tenant
5. Exposes 8 FastAPI endpoints for step and resource management
6. Enforces business rules like "only last step can be deleted" and status transition validation
7. Handles automatic step unlocking when previous steps complete
8. Manages step resource assignments (employees, machines, materials)

KEY FUNCTIONS / CLASSES / COMPONENTS

Name         : VALID_TRANSITIONS
Type         : constant dictionary
Purpose      : Defines which step status transitions are allowed. Steps start as "locked" (except first step which is "ready"), can progress to "in_progress" when work begins, and finally "complete" when finished. This enforces the sequential workflow where steps must be completed in order.
Parameters   : N/A (constant)
Returns      : N/A (constant)
Calls        : N/A
DB/API       : N/A
Side effects : Used by update_step_status to validate transitions

Name         : StepCreate
Type         : Pydantic BaseModel class
Purpose      : Validates incoming requests to create new job steps. Ensures required fields like name are provided and sets sensible defaults for step_type ("production") and duration_minutes (60).
Parameters   : name (str), step_type (str, optional), duration_minutes (int, optional), notes (str, optional)
Returns      : Validated data object
Calls        : Pydantic validation
DB/API       : N/A
Side effects : None

Name         : resource_to_dict
Type         : function
Purpose      : Converts a StepResource ORM model to a JSON-serializable dictionary. Looks up employee/machine names from their respective tables to provide human-readable resource names instead of just IDs.
Parameters   : r (StepResource ORM object), db (SQLAlchemy Session)
Returns      : Dictionary with resource details including resolved names
Calls        : SQLAlchemy queries to Employee and Machine tables
DB/API       : Queries Employee and Machine tables by ID
Side effects : None (read-only)

Name         : step_to_dict
Type         : function
Purpose      : Converts a JobStep ORM model to a JSON-serializable dictionary. Includes all step details plus nested resources array. Formats timestamps as ISO strings for frontend consumption.
Parameters   : step (JobStep ORM object), db (SQLAlchemy Session)
Returns      : Dictionary with complete step details including nested resources
Calls        : resource_to_dict for each step resource
DB/API       : Indirect queries via resource_to_dict
Side effects : None (read-only)

Name         : _get_job
Type         : function
Purpose      : Security guard function that verifies a job exists and belongs to the current user's tenant. Implements design principle #2 (tenant scoping) by always filtering on tenant_id. Raises 404 if job not found or doesn't belong to tenant.
Parameters   : job_id (int), tenant_id (int), db (SQLAlchemy Session)
Returns      : Job ORM object if found and accessible
Calls        : SQLAlchemy Job query
DB/API       : Queries Job table with tenant_id filter
Side effects : Raises HTTPException on security violation

Name         : _get_step
Type         : function
Purpose      : Security guard function that verifies a step exists, belongs to the specified job, and belongs to the current user's tenant. Triple security check ensuring step→job→tenant ownership chain.
Parameters   : step_id (int), job_id (int), tenant_id (int), db (SQLAlchemy Session)
Returns      : JobStep ORM object if found and accessible
Calls        : SQLAlchemy JobStep query
DB/API       : Queries JobStep table with multi-column filter
Side effects : Raises HTTPException on security violation

Name         : list_steps
Type         : FastAPI endpoint (GET)
Purpose      : Returns all steps for a job, ordered by sequence_no. Feature-flagged behind "step_intelligence" flag. Provides complete step details including resources for frontend display.
Parameters   : job_id (int from path), db (Session), current_user (User from JWT)
Returns      : List of step dictionaries with nested resources
Calls        : _get_job, step_to_dict, require_feature
DB/API       : Queries JobStep table filtered by job_id and tenant_id
Side effects : None (read-only)

Name         : create_step
Type         : FastAPI endpoint (POST)
Purpose      : Creates a new step at the end of the sequence. Validates step_type and duration. First step gets "ready" status, subsequent steps get "locked" status to enforce sequential execution.
Parameters   : job_id (int from path), body (StepCreate), db (Session), current_user (User)
Returns      : Created step dictionary
Calls        : _get_job, step_to_dict, require_feature
DB/API       : Queries for max sequence_no, inserts new JobStep record
Side effects : Creates new JobStep in database

Name         : update_step
Type         : FastAPI endpoint (PATCH)
Purpose      : Updates step details like name, type, duration, notes. Validates step_type and duration constraints. Updates the updated_at timestamp automatically.
Parameters   : job_id (int), step_id (int), body (StepUpdate), db (Session), current_user (User)
Returns      : Updated step dictionary
Calls        : _get_step, step_to_dict, require_feature
DB/API       : Updates JobStep record
Side effects : Modifies JobStep in database, sets updated_at timestamp

Name         : delete_step
Type         : FastAPI endpoint (DELETE)
Purpose      : Deletes the last step in the sequence only. After deletion, renumbers remaining steps to maintain gap-free sequence. This business rule prevents deleting steps in the middle which would break the sequential workflow.
Parameters   : job_id (int), step_id (int), db (Session), current_user (User)
Returns      : Confirmation dictionary with deleted step ID
Calls        : _get_job, _get_step, require_feature
DB/API       : Deletes JobStep, updates sequence_no on remaining steps
Side effects : Deletes step from database, renumbers remaining steps

Name         : update_step_status
Type         : FastAPI endpoint (PATCH)
Purpose      : Changes step status following valid transition rules. When a step completes, automatically unlocks the next step (changes from "locked" to "ready"). If the last step completes, marks the entire job as "Completed".
Parameters   : job_id (int), step_id (int), body (StepStatusUpdate), db (Session), current_user (User)
Returns      : Updated step dictionary
Calls        : _get_step, step_to_dict, require_feature
DB/API       : Updates JobStep status, potentially updates next step and job status
Side effects : Modifies step
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime, timezone

from app.database import get_db
from app.core.dependencies import get_current_user
from app.models.auth import User
from app.models.job import Job
from app.models.job_steps import JobStep, StepResource
from app.models.employee import Employee
from app.models.machine import Machine
from app.utils.feature_guard import require_feature

router = APIRouter()

# ── Valid transitions ─────────────────────────────────────────────────────────
VALID_TRANSITIONS = {
    "locked":      [],                  # only system can unlock via previous step completing
    "ready":       ["in_progress"],
    "in_progress": ["complete"],
    "complete":    [],                  # terminal
}

STEP_TYPES  = {"setup", "production", "inspection"}
RES_TYPES   = {"employee", "machine", "material"}


# ── Schemas ───────────────────────────────────────────────────────────────────
class StepCreate(BaseModel):
    name: str
    step_type: str = "production"
    duration_minutes: int = 60
    notes: Optional[str] = None

class StepUpdate(BaseModel):
    name: Optional[str] = None
    step_type: Optional[str] = None
    duration_minutes: Optional[int] = None
    notes: Optional[str] = None

class StepStatusUpdate(BaseModel):
    status: str  # the target status

class ResourceCreate(BaseModel):
    resource_type: str       # employee | machine | material
    resource_id: Optional[int] = None   # null for material
    quantity: Optional[float] = None
    unit_cost: Optional[float] = None
    notes: Optional[str] = None


# ── Serializers ───────────────────────────────────────────────────────────────
def resource_to_dict(r: StepResource, db: Session) -> dict:
    name = None
    if r.resource_type == "employee" and r.resource_id:
        emp = db.query(Employee).filter(Employee.id == r.resource_id).first()
        name = emp.full_name if emp else f"Employee #{r.resource_id}"
    elif r.resource_type == "machine" and r.resource_id:
        mac = db.query(Machine).filter(Machine.id == r.resource_id).first()
        name = mac.name if mac else f"Machine #{r.resource_id}"
    return {
        "id": r.id,
        "step_id": r.step_id,
        "resource_type": r.resource_type,
        "resource_id": r.resource_id,
        "resource_name": name,
        "quantity": r.quantity,
        "unit_cost": r.unit_cost,
        "notes": r.notes,
        "created_at": r.created_at.isoformat() if r.created_at else None,
    }

def step_to_dict(step: JobStep, db: Session) -> dict:
    return {
        "id": step.id,
        "job_id": step.job_id,
        "sequence_no": step.sequence_no,
        "name": step.name,
        "step_type": step.step_type,
        "duration_minutes": step.duration_minutes,
        "status": step.status,
        "notes": step.notes,
        "use_job_resources": step.use_job_resources,
        "resources": [resource_to_dict(r, db) for r in step.resources],
        "created_at": step.created_at.isoformat() if step.created_at else None,
        "updated_at": step.updated_at.isoformat() if step.updated_at else None,
    }


# ── Guard: job must belong to tenant ─────────────────────────────────────────
def _get_job(job_id: int, tenant_id: int, db: Session) -> Job:
    job = db.query(Job).filter(Job.id == job_id, Job.tenant_id == tenant_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job

def _get_step(step_id: int, job_id: int, tenant_id: int, db: Session) -> JobStep:
    step = db.query(JobStep).filter(
        JobStep.id == step_id,
        JobStep.job_id == job_id,
        JobStep.tenant_id == tenant_id,
    ).first()
    if not step:
        raise HTTPException(status_code=404, detail="Step not found")
    return step


# ── Routes ────────────────────────────────────────────────────────────────────

@router.get("/jobs/{job_id}/steps")
def list_steps(
    job_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # V3.7 — feature flag guard
    guard = require_feature("step_intelligence")
    if guard:
        return guard
    _get_job(job_id, current_user.tenant_id, db)
    steps = (
        db.query(JobStep)
        .filter(JobStep.job_id == job_id, JobStep.tenant_id == current_user.tenant_id)
        .order_by(JobStep.sequence_no)
        .all()
    )
    return [step_to_dict(s, db) for s in steps]


@router.post("/jobs/{job_id}/steps", status_code=201)
def create_step(
    job_id: int,
    body: StepCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # V3.7 — feature flag guard
    guard = require_feature("step_intelligence")
    if guard:
        return guard
    _get_job(job_id, current_user.tenant_id, db)

    if body.step_type not in STEP_TYPES:
        raise HTTPException(status_code=422, detail=f"step_type must be one of {STEP_TYPES}")
    if body.duration_minutes <= 0:
        raise HTTPException(status_code=422, detail="duration_minutes must be > 0")

    # Get current max sequence_no
    existing = (
        db.query(JobStep)
        .filter(JobStep.job_id == job_id, JobStep.tenant_id == current_user.tenant_id)
        .order_by(JobStep.sequence_no.desc())
        .first()
    )
    next_seq = (existing.sequence_no + 1) if existing else 1

    # First step is always ready; subsequent steps are locked
    initial_status = "ready" if next_seq == 1 else "locked"

    step = JobStep(
        job_id=job_id,
        tenant_id=current_user.tenant_id,
        sequence_no=next_seq,
        name=body.name,
        step_type=body.step_type,
        duration_minutes=body.duration_minutes,
        status=initial_status,
        notes=body.notes,
        use_job_resources=True,
    )
    db.add(step)
    db.commit()
    db.refresh(step)
    return step_to_dict(step, db)


@router.patch("/jobs/{job_id}/steps/{step_id}")
def update_step(
    job_id: int,
    step_id: int,
    body: StepUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # V3.7 — feature flag guard
    guard = require_feature("step_intelligence")
    if guard:
        return guard
    step = _get_step(step_id, job_id, current_user.tenant_id, db)

    if body.name is not None:
        step.name = body.name
    if body.step_type is not None:
        if body.step_type not in STEP_TYPES:
            raise HTTPException(status_code=422, detail=f"step_type must be one of {STEP_TYPES}")
        step.step_type = body.step_type
    if body.duration_minutes is not None:
        if body.duration_minutes <= 0:
            raise HTTPException(status_code=422, detail="duration_minutes must be > 0")
        step.duration_minutes = body.duration_minutes
    if body.notes is not None:
        step.notes = body.notes

    step.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(step)
    return step_to_dict(step, db)


@router.delete("/jobs/{job_id}/steps/{step_id}", status_code=200)
def delete_step(
    job_id: int,
    step_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Only the last step (highest sequence_no) can be deleted.
    After deletion, remaining steps are renumbered gap-free.
    """
    # V3.7 — feature flag guard
    guard = require_feature("step_intelligence")
    if guard:
        return guard
    _get_job(job_id, current_user.tenant_id, db)
    step = _get_step(step_id, job_id, current_user.tenant_id, db)

    # Find the last step
    last = (
        db.query(JobStep)
        .filter(JobStep.job_id == job_id, JobStep.tenant_id == current_user.tenant_id)
        .order_by(JobStep.sequence_no.desc())
        .first()
    )
    if last is None or step.id != last.id:
        raise HTTPException(
            status_code=400,
            detail="Only the last step can be deleted. Remove later steps first."
        )

    db.delete(step)
    db.commit()

    # Renumber remaining steps (gap-free)
    remaining = (
        db.query(JobStep)
        .filter(JobStep.job_id == job_id, JobStep.tenant_id == current_user.tenant_id)
        .order_by(JobStep.sequence_no)
        .all()
    )
    for i, s in enumerate(remaining, start=1):
        s.sequence_no = i
    db.commit()

    return {"deleted": True, "step_id": step_id}


@router.patch("/jobs/{job_id}/steps/{step_id}/status")
def update_step_status(
    job_id: int,
    step_id: int,
    body: StepStatusUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Enforce valid status transitions:
      ready       → in_progress  (manual: worker starts)
      in_progress → complete     (manual: worker finishes)

    When a step completes:
      - next step (sequence_no + 1) automatically becomes ready
      - if this was the last step, job status is set to Completed
    """
    # V3.7 — feature flag guard
    guard = require_feature("step_intelligence")
    if guard:
        return guard
    step = _get_step(step_id, job_id, current_user.tenant_id, db)
    target = body.status

    allowed = VALID_TRANSITIONS.get(step.status, [])
    if target not in allowed:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot transition from '{step.status}' to '{target}'. "
                   f"Allowed from '{step.status}': {allowed or ['none']}"
        )

    step.status = target
    step.updated_at = datetime.now(timezone.utc)

    # When step completes → unlock next step
    if target == "complete":
        next_step = (
            db.query(JobStep)
            .filter(
                JobStep.job_id == job_id,
                JobStep.tenant_id == current_user.tenant_id,
                JobStep.sequence_no == step.sequence_no + 1,
            )
            .first()
        )
        if next_step:
            next_step.status = "ready"
            next_step.updated_at = datetime.now(timezone.utc)
        else:
            # No next step — this was the last step → complete the job
            job = db.query(Job).filter(Job.id == job_id).first()
            if job and job.status not in ("Completed", "Cancelled"):
                job.status = "Completed"

    db.commit()
    db.refresh(step)
    return step_to_dict(step, db)


# ── Step Resource endpoints ───────────────────────────────────────────────────

@router.get("/jobs/{job_id}/steps/{step_id}/resources")
def list_step_resources(
    job_id: int,
    step_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # V3.7 — feature flag guard
    guard = require_feature("step_intelligence")
    if guard:
        return guard
    step = _get_step(step_id, job_id, current_user.tenant_id, db)
    return [resource_to_dict(r, db) for r in step.resources]


@router.post("/jobs/{job_id}/steps/{step_id}/resources", status_code=201)
def add_step_resource(
    job_id: int,
    step_id: int,
    body: ResourceCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # V3.7 — feature flag guard
    guard = require_feature("step_intelligence")
    if guard:
        return guard
    step = _get_step(step_id, job_id, current_user.tenant_id, db)

    if body.resource_type not in RES_TYPES:
        raise HTTPException(status_code=422, detail=f"resource_type must be one of {RES_TYPES}")

    if body.resource_type in ("employee", "machine") and not body.resource_id:
        raise HTTPException(status_code=422, detail="resource_id required for employee/machine")

    if body.resource_type == "material" and (body.quantity is None or body.quantity <= 0):
        raise HTTPException(status_code=422, detail="quantity required for material")

    # Validate resource_id exists
    if body.resource_type == "employee" and body.resource_id:
        emp = db.query(Employee).filter(
            Employee.id == body.resource_id,
            Employee.tenant_id == current_user.tenant_id
        ).first()
        if not emp:
            raise HTTPException(status_code=404, detail="Employee not found")

    if body.resource_type == "machine" and body.resource_id:
        mac = db.query(Machine).filter(
            Machine.id == body.resource_id,
            Machine.tenant_id == current_user.tenant_id
        ).first()
        if not mac:
            raise HTTPException(status_code=404, detail="Machine not found")

    res = StepResource(
        step_id=step.id,
        tenant_id=current_user.tenant_id,
        resource_type=body.resource_type,
        resource_id=body.resource_id,
        quantity=body.quantity,
        unit_cost=body.unit_cost,
        notes=body.notes,
    )
    db.add(res)

    # Flip step to step-level resources
    step.use_job_resources = False
    step.updated_at = datetime.now(timezone.utc)

    db.commit()
    db.refresh(res)
    return resource_to_dict(res, db)


@router.delete("/jobs/{job_id}/steps/{step_id}/resources/{resource_id}", status_code=200)
def remove_step_resource(
    job_id: int,
    step_id: int,
    resource_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    step = _get_step(step_id, job_id, current_user.tenant_id, db)
    res = db.query(StepResource).filter(
        StepResource.id == resource_id,
        StepResource.step_id == step.id,
    ).first()
    if not res:
        raise HTTPException(status_code=404, detail="Resource not found")

    db.delete(res)

    # If no resources remain, flip back to job-level
    remaining = db.query(StepResource).filter(StepResource.step_id == step.id).count()
    if remaining <= 1:  # the one we just deleted hasn't committed yet
        step.use_job_resources = True

    step.updated_at = datetime.now(timezone.utc)
    db.commit()
    return {"deleted": True, "resource_id": resource_id}


@router.post("/jobs/{job_id}/steps/{step_id}/use-job-resources", status_code=200)
def reset_to_job_resources(
    job_id: int,
    step_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Reset step to use job-level resources — deletes all step_resources for this step."""
    step = _get_step(step_id, job_id, current_user.tenant_id, db)

    # Delete all step-level resources
    db.query(StepResource).filter(StepResource.step_id == step.id).delete()
    step.use_job_resources = True
    step.updated_at = datetime.now(timezone.utc)

    db.commit()
    db.refresh(step)
    return step_to_dict(step, db)
