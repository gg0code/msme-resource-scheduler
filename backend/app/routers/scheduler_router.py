"""
backend/app/routers/scheduler.py — V3.7

POST /api/scheduler/run
  - Loads all jobs/steps/resources for tenant from DB
  - Builds locked_entries from existing schedule_entries for locked jobs
  - Calls run_scheduler()
  - Persists ScheduleEntry results (skips locked jobs)
  - Returns SchedulerResult JSON

GET /api/scheduler/entries
  - Returns all schedule_entries for current tenant

V3.7: feature flag guard — returns warm message if scheduler flag is False
"""

from __future__ import annotations

from datetime import date, datetime, time
from typing import List, Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import Column, DateTime, Integer, String, select
from sqlalchemy.dialects.postgresql import ARRAY as PG_ARRAY
from sqlalchemy.orm import Session

from app.database import Base, get_db
from app.models.scheduling import (
    SchedJob, SchedResource, SchedStep,
    SchedStepMachine, SchedStepHelper,
    StepStatus,
)
from app.routers.auth import get_current_user
from app.scheduler.engine import (
    ConflictEntry, JobInput, LockedEntry,
    ResourceSlot, ScheduleEntry, SchedulerResult,
    StepInput, run_scheduler,
)
from app.utils.feature_guard import require_feature

router = APIRouter()


# ─── DB Model for persisted schedule entries ─────────────────────────────────

class ScheduleEntryModel(Base):
    __tablename__ = "schedule_entries"

    id                   = Column(Integer, primary_key=True, index=True)
    tenant_id            = Column(Integer, nullable=False, index=True)
    job_id               = Column(Integer, nullable=False, index=True)
    step_id              = Column(Integer, nullable=False)
    assigned_machine_ids = Column(PG_ARRAY(Integer), nullable=False, default=[])
    assigned_helper_ids  = Column(PG_ARRAY(Integer), nullable=False, default=[])
    scheduled_start      = Column(DateTime, nullable=False)
    scheduled_end        = Column(DateTime, nullable=False)
    created_at           = Column(DateTime, default=datetime.utcnow)


# ─── Pydantic response models ─────────────────────────────────────────────────

class ScheduleEntryOut(BaseModel):
    id:                   int
    tenant_id:            int
    job_id:               int
    step_id:              int
    assigned_machine_ids: List[int]
    assigned_helper_ids:  List[int]
    scheduled_start:      datetime
    scheduled_end:        datetime
    created_at:           datetime

    model_config = {"from_attributes": True}


class ConflictEntryOut(BaseModel):
    job_id:         int
    step_id:        int
    sequence_order: int
    reason:         str


class SchedulerResultOut(BaseModel):
    resolved:   List[ScheduleEntryOut]
    unresolved: List[ConflictEntryOut]


class RunSchedulerRequest(BaseModel):
    schedule_date: Optional[date] = None   # defaults to today


# ─── Auth helper ─────────────────────────────────────────────────────────────

def _tenant(current_user=Depends(get_current_user)) -> int:
    return current_user.tenant_id


# ─── Loaders ─────────────────────────────────────────────────────────────────

def _load_resources(db: Session, tenant_id: int) -> List[ResourceSlot]:
    rows = db.scalars(
        select(SchedResource).where(SchedResource.tenant_id == tenant_id)
    ).all()
    return [
        ResourceSlot(
            id=r.id, name=r.name, type=r.type.value,
            shift_start=r.shift_start, shift_end=r.shift_end,
        )
        for r in rows
    ]


def _load_jobs(db: Session, tenant_id: int) -> List[JobInput]:
    rows = db.scalars(
        select(SchedJob).where(SchedJob.tenant_id == tenant_id)
    ).all()
    return [
        JobInput(
            id=j.id, name=j.name,
            priority=j.priority.value,
            expected_profit=j.expected_profit,
            deadline=j.deadline,
            shift=j.shift.value,
            lock_status=j.lock_status,
        )
        for j in rows
    ]


def _load_steps(db: Session, tenant_id: int) -> List[StepInput]:
    job_ids = db.scalars(
        select(SchedJob.id).where(SchedJob.tenant_id == tenant_id)
    ).all()
    if not job_ids:
        return []

    steps = db.scalars(
        select(SchedStep).where(SchedStep.job_id.in_(job_ids))
    ).all()

    machine_links = db.execute(
        select(SchedStepMachine.step_id, SchedStepMachine.resource_id)
        .where(SchedStepMachine.step_id.in_([s.id for s in steps]))
    ).all()
    helper_links = db.execute(
        select(SchedStepHelper.step_id, SchedStepHelper.resource_id)
        .where(SchedStepHelper.step_id.in_([s.id for s in steps]))
    ).all()

    machine_map: dict = {}
    for step_id, res_id in machine_links:
        machine_map.setdefault(step_id, []).append(res_id)

    helper_map: dict = {}
    for step_id, res_id in helper_links:
        helper_map.setdefault(step_id, []).append(res_id)

    return [
        StepInput(
            id=s.id,
            job_id=s.job_id,
            sequence_order=s.sequence_order,
            step_type=s.step_type.value,
            duration_minutes=s.duration_minutes,
            required_machine_ids=machine_map.get(s.id, []),
            required_helper_ids=helper_map.get(s.id, []),
            reserve_machine_id=s.reserve_machine_id,
        )
        for s in steps
    ]


def _load_locked_entries(db: Session, tenant_id: int) -> List[LockedEntry]:
    """
    Build LockedEntry list from existing schedule_entries for locked jobs.
    These represent committed windows that the scheduler must not overwrite.
    """
    locked_job_ids = db.scalars(
        select(SchedJob.id).where(
            SchedJob.tenant_id == tenant_id,
            SchedJob.lock_status == True,
        )
    ).all()
    if not locked_job_ids:
        return []

    entries = db.scalars(
        select(ScheduleEntryModel).where(
            ScheduleEntryModel.tenant_id == tenant_id,
            ScheduleEntryModel.job_id.in_(locked_job_ids),
        )
    ).all()

    locked: List[LockedEntry] = []
    for e in entries:
        for mid in (e.assigned_machine_ids or []):
            locked.append(LockedEntry(
                job_id=e.job_id, step_id=e.step_id,
                resource_id=mid, resource_type="machine",
                start=e.scheduled_start, end=e.scheduled_end,
            ))
        for hid in (e.assigned_helper_ids or []):
            locked.append(LockedEntry(
                job_id=e.job_id, step_id=e.step_id,
                resource_id=hid, resource_type="helper",
                start=e.scheduled_start, end=e.scheduled_end,
            ))

    all_steps = db.scalars(
        select(SchedStep).where(SchedStep.job_id.in_(locked_job_ids))
    ).all()
    step_entries = {e.step_id: e for e in entries}
    for step in all_steps:
        if step.reserve_machine_id and step.id in step_entries:
            e = step_entries[step.id]
            locked.append(LockedEntry(
                job_id=step.job_id, step_id=step.id,
                resource_id=step.reserve_machine_id, resource_type="reserve",
                start=e.scheduled_start, end=e.scheduled_end,
            ))

    return locked


# ─── Endpoints ───────────────────────────────────────────────────────────────

@router.post("/scheduler/run")
def run_scheduler_endpoint(
    body: RunSchedulerRequest = RunSchedulerRequest(),
    db: Session = Depends(get_db),
    tenant_id: int = Depends(_tenant),
):
    # V3.7 — feature flag guard
    guard = require_feature("scheduler")
    if guard:
        return guard

    schedule_date = body.schedule_date or date.today()

    resources      = _load_resources(db, tenant_id)
    jobs           = _load_jobs(db, tenant_id)
    steps          = _load_steps(db, tenant_id)
    locked_entries = _load_locked_entries(db, tenant_id)

    result = run_scheduler(
        jobs=jobs,
        steps=steps,
        resources=resources,
        locked_entries=locked_entries,
        schedule_date=schedule_date,
    )

    locked_job_ids = {j.id for j in jobs if j.lock_status}
    unlocked_step_ids = {
        e.step_id for e in result.resolved
        if e.job_id not in locked_job_ids
    }

    stale = db.scalars(
        select(ScheduleEntryModel).where(
            ScheduleEntryModel.tenant_id == tenant_id,
            ScheduleEntryModel.job_id.not_in(locked_job_ids) if locked_job_ids
            else ScheduleEntryModel.tenant_id == tenant_id,
        )
    ).all()
    for row in stale:
        if row.job_id not in locked_job_ids:
            db.delete(row)
    db.flush()

    for entry in result.resolved:
        if entry.job_id in locked_job_ids:
            continue
        db.add(ScheduleEntryModel(
            tenant_id=tenant_id,
            job_id=entry.job_id,
            step_id=entry.step_id,
            assigned_machine_ids=entry.assigned_machine_ids,
            assigned_helper_ids=entry.assigned_helper_ids,
            scheduled_start=entry.scheduled_start,
            scheduled_end=entry.scheduled_end,
        ))

    db.commit()

    saved = db.scalars(
        select(ScheduleEntryModel).where(
            ScheduleEntryModel.tenant_id == tenant_id,
            ScheduleEntryModel.step_id.in_([e.step_id for e in result.resolved]),
        )
    ).all()
    saved_map = {row.step_id: row for row in saved}

    resolved_out = []
    for entry in result.resolved:
        row = saved_map.get(entry.step_id)
        if row:
            resolved_out.append(ScheduleEntryOut.model_validate(row))
        else:
            resolved_out.append(ScheduleEntryOut(
                id=0, tenant_id=tenant_id,
                job_id=entry.job_id, step_id=entry.step_id,
                assigned_machine_ids=entry.assigned_machine_ids,
                assigned_helper_ids=entry.assigned_helper_ids,
                scheduled_start=entry.scheduled_start,
                scheduled_end=entry.scheduled_end,
                created_at=datetime.utcnow(),
            ))

    return SchedulerResultOut(
        resolved=resolved_out,
        unresolved=[
            ConflictEntryOut(
                job_id=c.job_id, step_id=c.step_id,
                sequence_order=c.sequence_order, reason=c.reason,
            )
            for c in result.unresolved
        ],
    )


@router.get("/scheduler/entries")
def get_schedule_entries(
    db: Session = Depends(get_db),
    tenant_id: int = Depends(_tenant),
):
    # V3.7 — feature flag guard
    guard = require_feature("scheduler")
    if guard:
        return guard

    rows = db.scalars(
        select(ScheduleEntryModel)
        .where(ScheduleEntryModel.tenant_id == tenant_id)
        .order_by(ScheduleEntryModel.scheduled_start)
    ).all()
    return [ScheduleEntryOut.model_validate(r) for r in rows]
