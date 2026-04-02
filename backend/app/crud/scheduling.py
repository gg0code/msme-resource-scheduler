"""
```python
"""
app/crud/scheduling.py — Legacy Scheduling System CRUD Operations

FILE PURPOSE
This file provides database CRUD (Create, Read, Update, Delete) operations for the legacy scheduling system in ZetaOps Copilot. It was introduced in early v4.x development and handles the SchedJob/SchedStep/SchedResource data model, which is separate from the main Job/JobStep system used by the current scheduler engine. This file sits in the data access layer and enforces critical business rules around step sequencing and readiness propagation. Note that this is legacy code - the main scheduler in backend/app/scheduler/engine.py uses the Job/JobStep models instead.

WHAT THIS FILE DOES — step by step
1. Defines internal helper functions for eager-loading database relationships
2. Validates that resource references (machines/helpers) exist and belong to the correct tenant
3. Manages step resource associations through link tables (SchedStepMachine, SchedStepHelper)
4. Enforces step sequencing rules - automatically assigns sequence_order and resequences after deletions
5. Implements readiness propagation - updates step status based on predecessor completion
6. Provides CRUD operations for SchedResource entities (machines and helpers)
7. Provides CRUD operations for SchedJob entities with eager-loaded relationships
8. Provides CRUD operations for SchedStep entities with automatic business rule enforcement

KEY FUNCTIONS / CLASSES / COMPONENTS

Name         : _eager_step
Type         : function
Purpose      : Internal helper that loads a SchedStep with all its resource associations (machine_links, helper_links) in a single query. Prevents N+1 query problems when accessing step resources.
Parameters   : db (Session) - SQLAlchemy database session, step_id (int) - primary key of step to load
Returns      : Optional[SchedStep] - step object with preloaded relationships, or None if not found
Calls        : SQLAlchemy select() and selectinload() for eager loading
DB/API       : Single SELECT query on SchedStep with JOIN to association tables
Side effects : None - pure read operation

Name         : _eager_job
Type         : function
Purpose      : Internal helper that loads a SchedJob with all its steps and each step's resource associations. Essential for job detail views and scheduling operations.
Parameters   : db (Session) - SQLAlchemy database session, job_id (int) - primary key of job to load
Returns      : Optional[SchedJob] - job object with preloaded steps and step resources, or None if not found
Calls        : SQLAlchemy select() with nested selectinload() for deep eager loading
DB/API       : Single SELECT query with multiple JOINs to load entire job hierarchy
Side effects : None - pure read operation

Name         : _validate_resource_refs
Type         : function
Purpose      : Critical security function that verifies all resource IDs exist in the database, belong to the correct tenant, and have the expected resource type (machine vs helper). Prevents tenant isolation violations.
Parameters   : db (Session) - database session, tenant_id (int) - tenant scope, machine_ids (List[int]) - machine IDs to validate, helper_ids (List[int]) - helper IDs to validate, reserve_machine_id (Optional[int]) - optional reserved machine ID
Returns      : None - raises ValueError if validation fails
Calls        : SQLAlchemy queries to check SchedResource table
DB/API       : SELECT queries on SchedResource filtered by tenant_id
Side effects : Raises ValueError exceptions for invalid references

Name         : _set_step_resources
Type         : function
Purpose      : Replaces all resource associations for a step by deleting existing links and creating new ones. Used during step updates to change required machines/helpers.
Parameters   : db (Session) - database session, step (SchedStep) - step to update, machine_ids (List[int]) - new machine requirements, helper_ids (List[int]) - new helper requirements
Returns      : None
Calls        : SQLAlchemy delete() and add() operations
DB/API       : DELETE on existing links, INSERT new SchedStepMachine and SchedStepHelper records
Side effects : Modifies database by replacing step resource associations

Name         : _resequence
Type         : function
Purpose      : Implements Rule 2 - renumbers all steps in a job to have consecutive sequence_order values 1, 2, 3... after a step deletion. Maintains sequence integrity.
Parameters   : db (Session) - database session, job_id (int) - job whose steps need resequencing
Returns      : None
Calls        : SQLAlchemy select() and attribute updates
DB/API       : SELECT steps ordered by sequence, UPDATE sequence_order values
Side effects : Modifies sequence_order field on multiple SchedStep records

Name         : _refresh_readiness
Type         : function
Purpose      : Implements Rule 1 - updates step status to enforce readiness propagation. A step can only be 'ready' if all predecessor steps are 'complete'. Reverts steps to 'pending' if predecessors become incomplete.
Parameters   : db (Session) - database session, job_id (int) - job whose step readiness needs refresh
Returns      : None
Calls        : SQLAlchemy select() and status updates
DB/API       : SELECT steps in sequence order, UPDATE status fields
Side effects : Changes status field on SchedStep records based on predecessor completion

Name         : create_resource
Type         : function
Purpose      : Creates a new SchedResource (machine or helper) for a tenant. Enforces unique naming constraint within tenant scope.
Parameters   : db (Session) - database session, tenant_id (int) - tenant creating the resource, data (ResourceCreate) - Pydantic schema with resource details
Returns      : SchedResource - newly created resource object
Calls        : SQLAlchemy queries and model creation
DB/API       : SELECT to check name uniqueness, INSERT new resource
Side effects : Creates new database record, commits transaction

Name         : get_resource
Type         : function
Purpose      : Retrieves a single resource by ID, filtered by tenant for security. Used in resource detail views and validation.
Parameters   : db (Session) - database session, tenant_id (int) - tenant scope filter, resource_id (int) - resource primary key
Returns      : Optional[SchedResource] - resource if found and owned by tenant, None otherwise
Calls        : SQLAlchemy select() with WHERE clause
DB/API       : Single SELECT query with tenant_id filter
Side effects : None - pure read operation

Name         : list_resources
Type         : function
Purpose      : Lists all resources for a tenant, optionally filtered by resource type (machine/helper). Used in resource management screens and dropdowns.
Parameters   : db (Session) - database session, tenant_id (int) - tenant scope filter, resource_type (Optional[ResourceType]) - optional filter for machines vs helpers
Returns      : List[SchedResource] - all matching resources ordered by name
Calls        : SQLAlchemy select() with conditional filtering
DB/API       : SELECT query with tenant filter and optional type filter
Side effects : None - pure read operation

Name         : update_resource
Type         : function
Purpose      : Updates an existing resource with new data. Validates shift timing (start must be before end) and enforces tenant ownership.
Parameters   : db (Session) - database session, tenant_id (int) - tenant scope, resource_id (int) - resource to update, data (ResourceUpdate) - Pydantic schema with changes
Returns      : Optional[SchedResource] - updated resource or None if not found
Calls        : get_resource() for retrieval, SQLAlchemy attribute updates
DB/API       : SELECT via get_resource(), UPDATE resource fields
Side effects : Modifies database record, commits transaction
"""

from __future__ import annotations

from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models.scheduling import (
    ResourceType, SchedJob, SchedJobStatus, SchedResource,
    SchedStep, SchedStepHelper, SchedStepMachine,
    StepStatus, StepType,
)
from app.schemas.scheduling import (
    JobCreate, JobUpdate, ResourceCreate, ResourceUpdate,
    StepCreate, StepUpdate,
)


# ─── Internal helpers ─────────────────────────────────────────────────────────

def _eager_step(db: Session, step_id: int) -> Optional[SchedStep]:
    return db.scalars(
        select(SchedStep)
        .where(SchedStep.id == step_id)
        .options(
            selectinload(SchedStep.machine_links),
            selectinload(SchedStep.helper_links),
        )
    ).first()


def _eager_job(db: Session, job_id: int) -> Optional[SchedJob]:
    return db.scalars(
        select(SchedJob)
        .where(SchedJob.id == job_id)
        .options(
            selectinload(SchedJob.steps)
            .selectinload(SchedStep.machine_links),
            selectinload(SchedJob.steps)
            .selectinload(SchedStep.helper_links),
        )
    ).first()


def _validate_resource_refs(
    db: Session,
    tenant_id: int,
    machine_ids: List[int],
    helper_ids: List[int],
    reserve_machine_id: Optional[int],
) -> None:
    """Verify IDs exist, belong to tenant, and have the correct type."""
    def _check(ids: List[int], expected_type: ResourceType, label: str) -> None:
        if not ids:
            return
        rows = db.scalars(
            select(SchedResource).where(
                SchedResource.id.in_(ids),
                SchedResource.tenant_id == tenant_id,
            )
        ).all()
        found = {r.id for r in rows}
        missing = set(ids) - found
        if missing:
            raise ValueError(f"{label} IDs not found for this tenant: {sorted(missing)}")
        wrong = [r.id for r in rows if r.type != expected_type]
        if wrong:
            raise ValueError(
                f"Resource IDs {wrong} are not of type '{expected_type.value}' "
                f"(required for {label})."
            )

    _check(machine_ids, ResourceType.machine, "required_machine_ids")
    _check(helper_ids,  ResourceType.helper,  "required_helper_ids")

    if reserve_machine_id is not None:
        res = db.scalars(
            select(SchedResource).where(
                SchedResource.id == reserve_machine_id,
                SchedResource.tenant_id == tenant_id,
            )
        ).first()
        if res is None:
            raise ValueError(f"reserve_machine_id={reserve_machine_id} not found.")
        if res.type != ResourceType.machine:
            raise ValueError(
                f"reserve_machine_id must reference a machine resource "
                f"(ID {reserve_machine_id} is type '{res.type.value}')."
            )


def _set_step_resources(
    db: Session,
    step: SchedStep,
    machine_ids: List[int],
    helper_ids: List[int],
) -> None:
    """Replace all resource associations on a step."""
    for link in list(step.machine_links):
        db.delete(link)
    for link in list(step.helper_links):
        db.delete(link)
    db.flush()
    for rid in machine_ids:
        db.add(SchedStepMachine(step_id=step.id, resource_id=rid))
    for rid in helper_ids:
        db.add(SchedStepHelper(step_id=step.id, resource_id=rid))
    db.flush()


def _resequence(db: Session, job_id: int) -> None:
    """Rule 2: renumber remaining steps 1..N after a deletion."""
    steps = db.scalars(
        select(SchedStep)
        .where(SchedStep.job_id == job_id)
        .order_by(SchedStep.sequence_order)
    ).all()
    for new_order, step in enumerate(steps, start=1):
        step.sequence_order = new_order
    db.flush()


def _refresh_readiness(db: Session, job_id: int) -> None:
    """
    Rule 1: walk steps in sequence order.
    A step is 'ready' only when all prior steps are 'complete'.
    If a prior step is not complete, any later 'ready' step reverts to 'pending'.
    """
    steps = db.scalars(
        select(SchedStep)
        .where(SchedStep.job_id == job_id)
        .order_by(SchedStep.sequence_order)
    ).all()

    all_prior_complete = True
    for step in steps:
        if step.status == StepStatus.complete:
            continue  # completed steps are immutable here
        if step.status == StepStatus.in_progress:
            all_prior_complete = False
            continue
        # pending or ready
        if all_prior_complete and step.status == StepStatus.pending:
            step.status = StepStatus.ready
        elif not all_prior_complete and step.status == StepStatus.ready:
            step.status = StepStatus.pending  # predecessor moved back
        all_prior_complete = False  # first non-complete blocks all successors

    db.flush()


# ─── Resource CRUD ────────────────────────────────────────────────────────────

def create_resource(db: Session, tenant_id: int, data: ResourceCreate) -> SchedResource:
    existing = db.scalars(
        select(SchedResource).where(
            SchedResource.tenant_id == tenant_id,
            SchedResource.name == data.name,
        )
    ).first()
    if existing:
        raise ValueError(f"A resource named '{data.name}' already exists for this tenant.")

    resource = SchedResource(tenant_id=tenant_id, **data.model_dump())
    db.add(resource)
    db.commit()
    db.refresh(resource)
    return resource


def get_resource(db: Session, tenant_id: int, resource_id: int) -> Optional[SchedResource]:
    return db.scalars(
        select(SchedResource).where(
            SchedResource.id == resource_id,
            SchedResource.tenant_id == tenant_id,
        )
    ).first()


def list_resources(
    db: Session,
    tenant_id: int,
    resource_type: Optional[ResourceType] = None,
) -> List[SchedResource]:
    q = select(SchedResource).where(SchedResource.tenant_id == tenant_id)
    if resource_type is not None:
        q = q.where(SchedResource.type == resource_type)
    return db.scalars(q.order_by(SchedResource.name)).all()


def update_resource(
    db: Session, tenant_id: int, resource_id: int, data: ResourceUpdate
) -> Optional[SchedResource]:
    resource = get_resource(db, tenant_id, resource_id)
    if resource is None:
        return None

    updates = data.model_dump(exclude_unset=True)
    new_start = updates.get("shift_start", resource.shift_start)
    new_end   = updates.get("shift_end",   resource.shift_end)
    if new_start >= new_end:
        raise ValueError("shift_start must be earlier than shift_end")

    for k, v in updates.items():
        setattr(resource, k, v)
    db.commit()
    db.refresh(resource)
    return resource


def delete_resource(db: Session, tenant_id: int, resource_id: int) -> bool:
    resource = get_resource(db, tenant_id, resource_id)
    if resource is None:
        return False
    db.delete(resource)
    db.commit()
    return True


# ─── Job CRUD ─────────────────────────────────────────────────────────────────

def create_job(db: Session, tenant_id: int, data: JobCreate) -> SchedJob:
    job = SchedJob(tenant_id=tenant_id, **data.model_dump())
    db.add(job)
    db.commit()
    db.refresh(job)
    return _eager_job(db, job.id)


def get_job(db: Session, tenant_id: int, job_id: int) -> Optional[SchedJob]:
    return _eager_job(db, job_id) if db.scalars(
        select(SchedJob).where(
            SchedJob.id == job_id, SchedJob.tenant_id == tenant_id
        )
    ).first() else None


def list_jobs(
    db: Session,
    tenant_id: int,
    status: Optional[SchedJobStatus] = None,
) -> List[SchedJob]:
    q = (
        select(SchedJob)
        .where(SchedJob.tenant_id == tenant_id)
        .options(
            selectinload(SchedJob.steps).selectinload(SchedStep.machine_links),
            selectinload(SchedJob.steps).selectinload(SchedStep.helper_links),
        )
        .order_by(SchedJob.created_at.desc())
    )
    if status:
        q = q.where(SchedJob.status == status)
    return db.scalars(q).all()


def update_job(
    db: Session, tenant_id: int, job_id: int, data: JobUpdate
) -> Optional[SchedJob]:
    job = db.scalars(
        select(SchedJob).where(SchedJob.id == job_id, SchedJob.tenant_id == tenant_id)
    ).first()
    if job is None:
        return None
    for k, v in data.model_dump(exclude_unset=True).items():
        setattr(job, k, v)
    db.commit()
    return _eager_job(db, job_id)


def delete_job(db: Session, tenant_id: int, job_id: int) -> bool:
    job = db.scalars(
        select(SchedJob).where(SchedJob.id == job_id, SchedJob.tenant_id == tenant_id)
    ).first()
    if job is None:
        return False
    db.delete(job)
    db.commit()
    return True


# ─── Step CRUD ────────────────────────────────────────────────────────────────

def create_step(db: Session, tenant_id: int, job_id: int, data: StepCreate) -> SchedStep:
    # Verify job belongs to tenant
    job = db.scalars(
        select(SchedJob).where(SchedJob.id == job_id, SchedJob.tenant_id == tenant_id)
    ).first()
    if job is None:
        raise ValueError(f"Job {job_id} not found.")

    # Rule 2: always append at end
    existing_orders = db.scalars(
        select(SchedStep.sequence_order).where(SchedStep.job_id == job_id)
    ).all()
    next_order = (max(existing_orders) + 1) if existing_orders else 1

    # Validate resource refs
    _validate_resource_refs(
        db, tenant_id,
        data.required_machine_ids,
        data.required_helper_ids,
        data.reserve_machine_id,
    )

    step = SchedStep(
        job_id=job_id,
        sequence_order=next_order,
        step_type=data.step_type,
        duration_minutes=data.duration_minutes,
        reserve_machine_id=data.reserve_machine_id,
        status=StepStatus.pending,
    )
    db.add(step)
    db.flush()

    for rid in data.required_machine_ids:
        db.add(SchedStepMachine(step_id=step.id, resource_id=rid))
    for rid in data.required_helper_ids:
        db.add(SchedStepHelper(step_id=step.id, resource_id=rid))
    db.flush()

    _refresh_readiness(db, job_id)
    db.commit()
    return _eager_step(db, step.id)


def get_step(db: Session, tenant_id: int, step_id: int) -> Optional[SchedStep]:
    step = _eager_step(db, step_id)
    if step is None:
        return None
    # verify tenant via job
    job = db.get(SchedJob, step.job_id)
    return step if (job and job.tenant_id == tenant_id) else None


def list_steps(db: Session, tenant_id: int, job_id: int) -> List[SchedStep]:
    # Verify job belongs to tenant
    job = db.scalars(
        select(SchedJob).where(SchedJob.id == job_id, SchedJob.tenant_id == tenant_id)
    ).first()
    if job is None:
        raise ValueError(f"Job {job_id} not found.")
    return db.scalars(
        select(SchedStep)
        .where(SchedStep.job_id == job_id)
        .order_by(SchedStep.sequence_order)
        .options(
            selectinload(SchedStep.machine_links),
            selectinload(SchedStep.helper_links),
        )
    ).all()


def update_step(
    db: Session, tenant_id: int, step_id: int, data: StepUpdate
) -> Optional[SchedStep]:
    step = get_step(db, tenant_id, step_id)
    if step is None:
        return None

    updates = data.model_dump(exclude_unset=True)
    new_machine_ids = updates.pop("required_machine_ids", None)
    new_helper_ids  = updates.pop("required_helper_ids",  None)

    # Determine effective types after update
    eff_type    = updates.get("step_type", step.step_type)
    eff_reserve = updates.get("reserve_machine_id", step.reserve_machine_id)
    eff_machines = (
        new_machine_ids if new_machine_ids is not None
        else [m.resource_id for m in step.machine_links]
    )

    # Cross-validate combined state
    if eff_type == StepType.setup and eff_machines:
        raise ValueError("Setup steps cannot have required_machine_ids.")
    if eff_type == StepType.regular and eff_reserve is not None:
        raise ValueError("reserve_machine_id is only valid for setup steps.")

    if new_machine_ids is not None or new_helper_ids is not None:
        m_ids = new_machine_ids or []
        h_ids = new_helper_ids  or []
        _validate_resource_refs(db, tenant_id, m_ids, h_ids, None)
        _set_step_resources(db, step, m_ids, h_ids)

    if "reserve_machine_id" in updates:
        _validate_resource_refs(db, tenant_id, [], [], updates["reserve_machine_id"])

    for k, v in updates.items():
        setattr(step, k, v)

    db.flush()
    _refresh_readiness(db, step.job_id)
    db.commit()
    return _eager_step(db, step_id)


def delete_step(db: Session, tenant_id: int, step_id: int) -> bool:
    step = get_step(db, tenant_id, step_id)
    if step is None:
        return False
    job_id = step.job_id
    db.delete(step)
    db.flush()
    _resequence(db, job_id)       # Rule 2: close gap
    _refresh_readiness(db, job_id) # Rule 1: re-evaluate
    db.commit()
    return True


def update_step_status(
    db: Session, tenant_id: int, step_id: int, new_status: StepStatus
) -> Optional[SchedStep]:
    """
    PATCH /status — update one step's status then re-evaluate all siblings.
    Rule 1 is always applied after this change.
    Guard: cannot set 'ready' if predecessors are not complete.
    """
    step = get_step(db, tenant_id, step_id)
    if step is None:
        return None

    if new_status == StepStatus.ready:
        predecessors = db.scalars(
            select(SchedStep).where(
                SchedStep.job_id == step.job_id,
                SchedStep.sequence_order < step.sequence_order,
            )
        ).all()
        not_done = [s for s in predecessors if s.status != StepStatus.complete]
        if not_done:
            orders = sorted(s.sequence_order for s in not_done)
            raise ValueError(
                f"Cannot set step to 'ready': predecessors at positions "
                f"{orders} are not yet complete."
            )

    step.status = new_status
    db.flush()
    _refresh_readiness(db, step.job_id)
    db.commit()
    return _eager_step(db, step_id)
