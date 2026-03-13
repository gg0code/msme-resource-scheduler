"""
app/crud/scheduling.py — Prompt 1 CRUD

Business rules enforced here:

Rule 1 — Readiness propagation:
  After ANY step status change, _refresh_readiness(db, job_id) is called.
  A step becomes 'ready' only when all steps with lower sequence_order are 'complete'.

Rule 2 — Sequence integrity:
  create → always appends at max_order + 1 (or 1 if first).
  delete → calls _resequence(db, job_id) to close gaps.
  sequence_order is never manually set by callers.

Rule 3 — Setup step validation:
  setup: required_machine_ids must be [] (validated in schema + here)
  regular: reserve_machine_id must be None
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
