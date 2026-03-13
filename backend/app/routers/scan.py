"""
app/routers/scan.py — Block 2 V3.0 + V3.1
Token generation and scan execution endpoints.

Endpoints:
  POST /api/jobs/{job_id}/scan-tokens   — generate all tokens for a job (auth required)
  POST /api/scan/execute                — execute a scan action (no auth, token-based)
  GET  /api/scan/verify                 — verify token and return metadata (no auth)
"""

from datetime import datetime, timezone
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.routers.auth import get_current_user
from app.services.token_service import create_scan_token, verify_scan_token

router = APIRouter()


# ── Schemas ───────────────────────────────────────────────────────────────────

class StepTokenPair(BaseModel):
    step_id:      int
    sequence_no:  int
    step_name:    str
    step_type:    str
    duration_minutes: int
    status:       str
    start_token:  str
    complete_token: str
    expires_at:   str


class JobTokensResponse(BaseModel):
    job_id:     int
    job_name:   str
    expires_at: str
    steps:      List[StepTokenPair]


class ScanExecuteRequest(BaseModel):
    token: str


class ScanExecuteResponse(BaseModel):
    success:    bool
    action:     str
    step_name:  str
    job_name:   str
    step_id:    int
    job_id:     int
    is_last_step: bool
    next_step_name: str | None = None
    job_completed:  bool = False
    message:    str


class ScanVerifyResponse(BaseModel):
    valid:      bool
    action:     str
    step_name:  str
    job_name:   str
    step_id:    int
    job_id:     int
    expires_at: str
    current_step_status: str
    can_execute: bool
    reason:     str | None = None


# ── Helpers ───────────────────────────────────────────────────────────────────

def _get_job(db: Session, job_id: int, tenant_id: int):
    from app.models.job import Job  # avoid circular import
    job = db.query(Job).filter(Job.id == job_id, Job.tenant_id == tenant_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


def _get_step(db: Session, step_id: int, tenant_id: int):
    from app.models.job_steps import JobStep
    step = db.query(JobStep).filter(
        JobStep.id == step_id,
        JobStep.tenant_id == tenant_id
    ).first()
    return step


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post(
    "/jobs/{job_id}/scan-tokens",
    response_model=JobTokensResponse,
    tags=["scan"],
    summary="Generate QR scan tokens for all steps of a job",
)
def generate_job_tokens(
    job_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    from app.models.job_steps import JobStep

    tenant_id = current_user.tenant_id
    job = _get_job(db, job_id, tenant_id)

    steps = (
        db.query(JobStep)
        .filter(JobStep.job_id == job_id, JobStep.tenant_id == tenant_id)
        .order_by(JobStep.sequence_no)
        .all()
    )

    if not steps:
        raise HTTPException(status_code=404, detail="This job has no steps. Add steps before printing.")

    job_name = job.name if hasattr(job, "name") else f"Job #{job_id}"
    job_end_date = getattr(job, "end_date", None)

    step_tokens = []
    expires_at_str = None

    for step in steps:
        start_tok = create_scan_token(
            action="start_step",
            job_id=job_id,
            step_id=step.id,
            tenant_id=tenant_id,
            step_name=step.name,
            job_name=job_name,
            job_end_date=job_end_date,
        )
        complete_tok = create_scan_token(
            action="complete_step",
            job_id=job_id,
            step_id=step.id,
            tenant_id=tenant_id,
            step_name=step.name,
            job_name=job_name,
            job_end_date=job_end_date,
        )
        expires_at_str = start_tok["expires_at"]  # same for all

        step_tokens.append(StepTokenPair(
            step_id=step.id,
            sequence_no=step.sequence_no,
            step_name=step.name,
            step_type=step.step_type,
            duration_minutes=step.duration_minutes,
            status=step.status,
            start_token=start_tok["token"],
            complete_token=complete_tok["token"],
            expires_at=expires_at_str,
        ))

    return JobTokensResponse(
        job_id=job_id,
        job_name=job_name,
        expires_at=expires_at_str or "",
        steps=step_tokens,
    )


@router.get(
    "/scan/verify",
    response_model=ScanVerifyResponse,
    tags=["scan"],
    summary="Verify a scan token and return step metadata (no auth)",
)
def verify_token(token: str, db: Session = Depends(get_db)):
    # Decode token
    try:
        payload = verify_scan_token(token)
    except ValueError as e:
        reason = str(e)
        return ScanVerifyResponse(
            valid=False,
            action="",
            step_name="",
            job_name="",
            step_id=0,
            job_id=0,
            expires_at="",
            current_step_status="",
            can_execute=False,
            reason="expired" if reason == "expired" else "invalid",
        )

    step = _get_step(db, payload["step_id"], payload["tenant_id"])
    if not step:
        return ScanVerifyResponse(
            valid=False, action="", step_name="", job_name="",
            step_id=0, job_id=0, expires_at="", current_step_status="",
            can_execute=False, reason="invalid",
        )

    # Check if action is executable given current status
    action = payload["action"]
    can_execute = (
        (action == "start_step" and step.status == "ready") or
        (action == "complete_step" and step.status == "in_progress")
    )

    reason = None
    if not can_execute:
        if step.status == "locked":
            reason = "locked"
        elif step.status == "complete":
            reason = "already_complete"
        else:
            reason = "wrong_status"

    return ScanVerifyResponse(
        valid=True,
        action=action,
        step_name=payload["step_name"],
        job_name=payload["job_name"],
        step_id=payload["step_id"],
        job_id=payload["job_id"],
        expires_at=payload.get("exp", ""),
        current_step_status=step.status,
        can_execute=can_execute,
        reason=reason,
    )


@router.post(
    "/scan/execute",
    response_model=ScanExecuteResponse,
    tags=["scan"],
    summary="Execute a scan action — start or complete a step (no auth)",
)
def execute_scan(body: ScanExecuteRequest, db: Session = Depends(get_db)):
    from app.models.job_steps import JobStep
    from app.models.job import Job

    # Verify token
    try:
        payload = verify_scan_token(body.token)
    except ValueError as e:
        raise HTTPException(
            status_code=400,
            detail={"error": str(e), "message": "expired" if str(e) == "expired" else "invalid"},
        )

    action    = payload["action"]
    step_id   = payload["step_id"]
    job_id    = payload["job_id"]
    tenant_id = payload["tenant_id"]

    step = _get_step(db, step_id, tenant_id)
    if not step:
        raise HTTPException(status_code=404, detail={"error": "invalid", "message": "Step not found"})

    # Enforce status transitions
    if action == "start_step":
        if step.status != "ready":
            raise HTTPException(
                status_code=422,
                detail={"error": "wrong_status", "message": f"Step is '{step.status}', not ready to start"},
            )
        step.status = "in_progress"
        step.started_at = datetime.now(timezone.utc)

    elif action == "complete_step":
        if step.status != "in_progress":
            raise HTTPException(
                status_code=422,
                detail={"error": "wrong_status", "message": f"Step is '{step.status}', not in progress"},
            )
        step.status = "complete"
        step.updated_at = datetime.now(timezone.utc)

        # Unlock next step
        next_step = (
            db.query(JobStep)
            .filter(
                JobStep.job_id == job_id,
                JobStep.tenant_id == tenant_id,
                JobStep.sequence_no == step.sequence_no + 1,
            )
            .first()
        )
        if next_step and next_step.status == "locked":
            next_step.status = "ready"

    db.commit()
    db.refresh(step)

    # Check if last step → auto-complete job
    all_steps = (
        db.query(JobStep)
        .filter(JobStep.job_id == job_id, JobStep.tenant_id == tenant_id)
        .all()
    )
    all_complete = all(s.status == "complete" for s in all_steps)
    job_completed = False

    if all_complete and action == "complete_step":
        job = db.query(Job).filter(Job.id == job_id, Job.tenant_id == tenant_id).first()
        if job and job.status != "completed":
            job.status = "completed"
            db.commit()
            job_completed = True

    # Next step info
    next_step_after = (
        db.query(JobStep)
        .filter(
            JobStep.job_id == job_id,
            JobStep.tenant_id == tenant_id,
            JobStep.sequence_no == step.sequence_no + 1,
        )
        .first()
    )
    is_last = next_step_after is None

    message = (
        f"Job completed! All steps done." if job_completed
        else f"Next: {next_step_after.name} is now ready" if (next_step_after and action == "complete_step")
        else f"Step started. Scan Done QR when finished."
    )

    return ScanExecuteResponse(
        success=True,
        action=action,
        step_name=payload["step_name"],
        job_name=payload["job_name"],
        step_id=step_id,
        job_id=job_id,
        is_last_step=is_last,
        next_step_name=next_step_after.name if next_step_after else None,
        job_completed=job_completed,
        message=message,
    )
