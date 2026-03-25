"""
backend/app/routers/schedule_suggestions.py — v3.9.7

GET /api/jobs/{job_id}/schedule-suggestions

Returns the top 3 viable start dates for a job with a score and plain-English
reasoning for each. Prerequisite for AI Copilot "when should I schedule this
job?" feature (v3.9.9).

Scoring (pure Python, no AI):
  +40  all assigned machines are free on candidate window
  +30  job completes on or before deadline (end_date)
  +20  candidate start falls within job's earliest/latest date window
  +10  buffer days before deadline (scaled, max 10)

Engine does the computation. AI only narrates (v3.9.9).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.job import Job, JobAssignment
from app.models.machine import Machine
from app.models.employee import Employee
from app.core.dependencies import get_current_user
from app.models.auth import User
from app.services.availability_engine import (
    _is_machine_busy,
    _is_employee_busy,
    _date_range,
)

router = APIRouter()

# ─── How many days ahead to scan ─────────────────────────────────────────────
SCAN_DAYS    = 30
TOP_N        = 3


# ─── Internal scored candidate ────────────────────────────────────────────────

@dataclass
class _Candidate:
    start:     date
    end:       date
    score:     int
    reasoning: str


# ─── Scorer ───────────────────────────────────────────────────────────────────

def _score_candidate(
    start:        date,
    end:          date,
    deadline:     date,
    earliest:     Optional[date],
    latest:       Optional[date],
    machines_free: bool,
    employees_free: bool,
) -> tuple[int, str]:
    """
    Score a candidate window and produce a one-sentence reason.
    Returns (score, reasoning).
    """
    score = 0
    notes = []

    # +40 — machines free
    if machines_free:
        score += 40
    else:
        notes.append("some machines are busy")

    # +20 — employees free (separate from machines, lower weight)
    if employees_free:
        score += 20
    else:
        notes.append("some people are allocated elsewhere")

    # +30 — completes before or on deadline
    if end <= deadline:
        score += 30
        buffer = (deadline - end).days
        # +10 — buffer days before deadline (scaled, max 10)
        buffer_pts = min(buffer, 10)
        score += buffer_pts
        if buffer > 0:
            notes.append(f"finishes {buffer} day{'s' if buffer != 1 else ''} before deadline")
        else:
            notes.append("finishes exactly on deadline")
    else:
        overrun = (end - deadline).days
        notes.append(f"finishes {overrun} day{'s' if overrun != 1 else ''} after deadline")

    # +0 — date window check (informational only, no score impact)
    if earliest and start < earliest:
        notes.append(f"starts before earliest allowed date {earliest}")
    if latest and end > latest:
        notes.append(f"ends after latest allowed date {latest}")

    # Build reasoning sentence
    if score >= 80:
        prefix = "Good slot"
    elif score >= 50:
        prefix = "Viable slot"
    else:
        prefix = "Tight slot"

    if notes:
        reasoning = f"{prefix}: {'; '.join(notes)}."
    else:
        reasoning = f"{prefix}: all resources free and job completes on time."

    return score, reasoning


# ─── Endpoint ─────────────────────────────────────────────────────────────────

@router.get("/jobs/{job_id}/schedule-suggestions")
def get_schedule_suggestions(
    job_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Scan the next 30 days and return the top 3 start dates for this job,
    each with a score out of 100 and a plain-English reasoning string.
    """
    tenant_id = current_user.tenant_id

    # Load job
    job = db.query(Job).filter(
        Job.id == job_id,
        Job.tenant_id == tenant_id,
    ).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    # Job duration in days
    duration_days = (job.end_date - job.start_date).days
    if duration_days < 0:
        duration_days = 0

    deadline  = job.end_date
    earliest  = job.earliest_date
    latest    = job.latest_date

    # Assigned machines and employees for this job
    assignments = db.query(JobAssignment).filter(
        JobAssignment.job_id == job_id,
        JobAssignment.tenant_id == tenant_id,
    ).all()

    machine_ids  = [a.machine_id  for a in assignments if a.machine_id]
    employee_ids = [a.employee_id for a in assignments if a.employee_id]

    # Scan window: today → today + SCAN_DAYS
    today      = date.today()
    scan_start = earliest if (earliest and earliest >= today) else today
    candidates: List[_Candidate] = []

    for offset in range(SCAN_DAYS):
        candidate_start = scan_start + timedelta(days=offset)
        candidate_end   = candidate_start + timedelta(days=duration_days)
        window          = _date_range(candidate_start, candidate_end)

        # Check machines
        machines_free = all(
            not _is_machine_busy(db, mid, job_id, window, tenant_id)
            for mid in machine_ids
        ) if machine_ids else True

        # Check employees
        employees_free = all(
            not _is_employee_busy(db, eid, job_id, window, tenant_id)
            for eid in employee_ids
        ) if employee_ids else True

        score, reasoning = _score_candidate(
            start=candidate_start,
            end=candidate_end,
            deadline=deadline,
            earliest=earliest,
            latest=latest,
            machines_free=machines_free,
            employees_free=employees_free,
        )

        candidates.append(_Candidate(
            start=candidate_start,
            end=candidate_end,
            score=score,
            reasoning=reasoning,
        ))

    # Sort by score descending, take top N
    candidates.sort(key=lambda c: -c.score)
    top = candidates[:TOP_N]

    return {
        "job_id":   job_id,
        "job_name": job.name,
        "suggestions": [
            {
                "rank":            i + 1,
                "suggested_start": str(c.start),
                "suggested_end":   str(c.end),
                "score":           c.score,
                "reasoning":       c.reasoning,
            }
            for i, c in enumerate(top)
        ],
    }
