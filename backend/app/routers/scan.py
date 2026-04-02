"""
FILE PURPOSE
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
This file implements the QR code scanning system for ZetaOps Copilot, allowing factory floor workers to start and complete job steps by scanning QR codes without needing to log in. Introduced in v3.7 on the v4-dev branch, it sits in the FastAPI router layer and handles both authenticated token generation (for managers printing QR cards) and unauthenticated token verification/execution (for workers scanning codes). This enables hands-free job step tracking in manufacturing environments where workers may have dirty hands or limited device access.

WHAT THIS FILE DOES — step by step
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
1. Defines Pydantic schemas for QR token generation, verification, and execution requests/responses
2. Provides helper functions to safely query Jobs and JobSteps with tenant_id filtering
3. Exposes a POST endpoint for authenticated users to generate start/complete token pairs for all steps in a job
4. Exposes a GET endpoint for unauthenticated token verification (returns step metadata without executing)
5. Exposes a POST endpoint for unauthenticated token execution (actually starts or completes the step)
6. Implements step status transitions (ready → in_progress → complete) with automatic next-step unlocking
7. Detects job completion when all steps are complete and updates the parent Job status
8. Returns rich response data including next step information and user-friendly messages

KEY FUNCTIONS / CLASSES / COMPONENTS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

StepTokenPair
    Type         : Pydantic BaseModel class
    Purpose      : Response schema representing a single job step with its associated start and complete QR tokens. Contains all metadata needed to print a QR card for a step including timing, status, and the actual token strings.
    Parameters   : step_id (int), sequence_no (int), step_name (str), step_type (str), duration_minutes (int), status (str), start_token (str), complete_token (str), expires_at (str)
    Returns      : N/A (data class)
    Calls        : None
    DB/API       : None
    Side effects : None

JobTokensResponse
    Type         : Pydantic BaseModel class
    Purpose      : Response schema for the token generation endpoint. Contains job-level metadata and a list of all step token pairs for printing QR cards.
    Parameters   : job_id (int), job_name (str), expires_at (str), steps (List[StepTokenPair])
    Returns      : N/A (data class)
    Calls        : None
    DB/API       : None
    Side effects : None

ScanExecuteRequest
    Type         : Pydantic BaseModel class
    Purpose      : Request schema for executing a QR scan. Contains only the scanned token string that workers provide.
    Parameters   : token (str)
    Returns      : N/A (data class)
    Calls        : None
    DB/API       : None
    Side effects : None

ScanExecuteResponse
    Type         : Pydantic BaseModel class
    Purpose      : Response schema for scan execution results. Provides comprehensive feedback to the worker including success status, what happened, and what to do next.
    Parameters   : success (bool), action (str), step_name (str), job_name (str), step_id (int), job_id (int), is_last_step (bool), next_step_name (str | None), job_completed (bool), message (str)
    Returns      : N/A (data class)
    Calls        : None
    DB/API       : None
    Side effects : None

ScanVerifyResponse
    Type         : Pydantic BaseModel class
    Purpose      : Response schema for token verification. Allows UIs to show step information and determine if a scan can be executed before actually doing it.
    Parameters   : valid (bool), action (str), step_name (str), job_name (str), step_id (int), job_id (int), expires_at (str), current_step_status (str), can_execute (bool), reason (str | None)
    Returns      : N/A (data class)
    Calls        : None
    DB/API       : None
    Side effects : None

_get_job
    Type         : Helper function
    Purpose      : Safely retrieves a Job by ID with tenant_id filtering to prevent cross-tenant data access. Raises 404 if job doesn't exist or doesn't belong to the tenant.
    Parameters   : db (Session) - SQLAlchemy database session, job_id (int) - job primary key, tenant_id (int) - tenant isolation filter
    Returns      : Job model instance if found
    Calls        : SQLAlchemy Job model query
    DB/API       : Queries Job table with tenant_id filter
    Side effects : Raises HTTPException(404) if job not found

_get_step
    Type         : Helper function
    Purpose      : Safely retrieves a JobStep by ID with tenant_id filtering. Returns None instead of raising an exception, allowing callers to handle missing steps gracefully.
    Parameters   : db (Session) - SQLAlchemy database session, step_id (int) - step primary key, tenant_id (int) - tenant isolation filter
    Returns      : JobStep model instance if found, None otherwise
    Calls        : SQLAlchemy JobStep model query
    DB/API       : Queries JobStep table with tenant_id filter
    Side effects : None

generate_job_tokens
    Type         : FastAPI POST endpoint
    Purpose      : Authenticated endpoint that generates start and complete QR tokens for all steps in a job. Managers use this to print QR cards. Feature-flagged by qr_scan setting, returning a warm message if disabled.
    Parameters   : job_id (int) - URL path parameter, db (Session) - injected database session, current_user - injected authenticated user
    Returns      : JobTokensResponse containing job metadata and token pairs for all steps
    Calls        : require_feature(), _get_job(), create_scan_token() from token_service
    DB/API       : Queries JobStep table to get all steps for the job, ordered by sequence_no
    Side effects : None (read-only operation)

verify_token
    Type         : FastAPI GET endpoint
    Purpose      : Unauthenticated endpoint that verifies a Q
"""

from datetime import datetime, timezone
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.core.dependencies import get_current_user
from app.services.token_service import create_scan_token, verify_scan_token
from app.utils.feature_guard import require_feature

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
    # V3.7 — feature flag guard (token generation only — execute/verify always allowed)
    guard = require_feature("qr_scan")
    if guard:
        return guard

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
    # NOTE: No feature guard here — a printed QR card must always be verifiable
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
    # NOTE: No feature guard here — a printed QR card must always be executable
    from app.models.job_steps import JobStep
    from app.models.job import Job

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
        "Job completed! All steps done." if job_completed
        else f"Next: {next_step_after.name} is now ready" if (next_step_after and action == "complete_step")
        else "Step started. Scan Done QR when finished."
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
