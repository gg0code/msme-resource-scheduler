"""
```python
"""
backend/app/routers/schedule_suggestions.py

FILE PURPOSE
This file provides an AI Copilot prerequisite endpoint that analyzes scheduling feasibility 
for manufacturing jobs. Introduced in v3.9.7 as preparation for the AI Copilot "when should 
I schedule this job?" feature (v3.9.9). It sits in the routers layer, calling the availability 
engine to compute scoring, while the AI service will later narrate these results to users in 
plain English.

WHAT THIS FILE DOES — step by step
1. Defines scoring constants (SCAN_DAYS=30, TOP_N=3) for how far ahead to look and how many suggestions to return
2. Creates a _Candidate dataclass to hold start date, end date, score, and reasoning for each potential scheduling window
3. Implements _score_candidate() function that assigns numerical scores based on machine availability, deadline compliance, and buffer time
4. Provides GET /api/jobs/{job_id}/schedule-suggestions endpoint that loads a job and its resource assignments from the database
5. Scans the next 30 days, checking machine and employee availability for each potential start date
6. Scores each candidate window using the scoring function and sorts by score descending
7. Returns the top 3 suggestions with rank, dates, score, and plain-English reasoning

KEY FUNCTIONS / CLASSES / COMPONENTS

Name         : _Candidate
Type         : dataclass
Purpose      : Internal data structure to hold a candidate scheduling window with its computed score and human-readable reasoning. Used only within this module to organize data before converting to API response format.
Parameters   : start (date), end (date), score (int), reasoning (str)
Returns      : N/A (dataclass)
Calls        : None
DB/API       : None
Side effects : None

Name         : _score_candidate
Type         : function
Purpose      : Pure computation function that assigns numerical scores to scheduling windows based on resource availability, deadline compliance, and buffer time. Implements the core scoring algorithm without any database calls or external dependencies. Also generates plain-English reasoning strings explaining why each window received its score.
Parameters   : start (date) - candidate start date, end (date) - candidate end date, deadline (date) - job's required completion date, earliest (Optional[date]) - job's earliest allowed start, latest (Optional[date]) - job's latest allowed end, machines_free (bool) - whether all assigned machines are available, employees_free (bool) - whether all assigned employees are available
Returns      : tuple[int, str] - (score out of 100, reasoning sentence explaining the score)
Calls        : None (pure function)
DB/API       : None
Side effects : None

Name         : get_schedule_suggestions
Type         : FastAPI endpoint
Purpose      : Main API endpoint that finds the top 3 viable start dates for a given job by scanning the next 30 days and scoring each possibility. Loads job data and resource assignments from database, checks availability using the availability engine, and returns ranked suggestions with scores and reasoning. This is the prerequisite data that the AI Copilot will later narrate to users.
Parameters   : job_id (int) - database ID of job to analyze, db (Session) - SQLAlchemy database session from dependency injection, current_user (User) - authenticated user from JWT token dependency
Returns      : dict with job_id, job_name, and suggestions array containing rank, suggested_start, suggested_end, score, and reasoning for each of the top 3 options
Calls        : app.services.availability_engine._is_machine_busy(), app.services.availability_engine._is_employee_busy(), app.services.availability_engine._date_range(), _score_candidate()
DB/API       : Queries Job table filtered by job_id and tenant_id, queries JobAssignment table to get machine_ids and employee_ids for the job
Side effects : None (read-only endpoint)

WHO CALLS THIS FILE
This endpoint is called by frontend API functions in frontend/src/api/ (likely api_scheduler.ts or similar) when users request scheduling suggestions through the UI. The AI Copilot service in backend/app/services/ai_service.py will call this endpoint in v3.9.9 to get data for natural language narration.

IMPORTS EXPLAINED
__future__.annotations - Enables postponed evaluation of type annotations for forward references in Python 3.9+. dataclasses.dataclass - Used to create the _Candidate data structure with automatic __init__ and comparison methods. datetime.date, datetime.timedelta - Date arithmetic for scanning scheduling windows and calculating durations. typing.List, typing.Optional - Type hints for function signatures and better IDE support. fastapi.APIRouter, fastapi.Depends, fastapi.HTTPException - FastAPI framework components for routing, dependency injection, and error handling. sqlalchemy.orm.Session - Database session type for SQLAlchemy ORM queries. app.database.get_db - Dependency that provides database session with proper cleanup. app.models.job.Job, app.models.job.JobAssignment - SQLAlchemy models for job data and resource assignments. app.models.machine.Machine, app.models.employee.Employee - SQLAlchemy models for manufacturing resources (imported but not directly used in queries). app.core.dependencies.get_current_user - Security dependency that extracts user from JWT token and enforces authentication. app.models.auth.User - User model type for current_user parameter. app.services.availability_engine - Contains _is_machine_busy, _is_employee_busy, and _date_range functions for checking resource conflicts.

INTERN NOTES
- Easiest thing to break without realising: Forgetting tenant_id filter on database queries - this would leak scheduling data between different manufacturing companies and create a major security vulnerability
- Non-obvious design decision and why: The scoring function is pure Python with no AI involvement because design principle #1 states "Engine computes, AI only narrates" - this ensures consistent, predictable scoring that AI can explain but never override
- Most common mistake when editing: Changing the scoring weights without updating the reasoning strings, which would make the explanations inconsistent with actual scores and confuse users
- Which design principle (by number) this file implements: Principle #1 (Engine computes, AI only narrates) and principle #2 (Tenant scoping on ALL DB queries)
- What to check if this file behaves unexpectedly: Verify that _is_machine_busy and _is_employee_busy in availability_engine.py are working correctly, check that job.end_date and job.start_date produce sensible duration_days, and confirm JobAssignment records exist for the job
- If v5-whatsapp only: N/A - this file exists in v4-dev and is not WhatsApp-specific functionality
"""
```
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
