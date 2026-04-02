"""
```python
"""
backend/app/routers/material_estimate.py

FILE PURPOSE
This FastAPI router provides material consumption estimation for manufacturing jobs by analyzing historical data from completed jobs of the same type. Introduced in v3.9.8 as a prerequisite for the AI Copilot's "how much material do I need?" feature (v3.9.9), it sits in the business logic layer between the frontend job planning interface and the database, calculating estimates that the AI will later narrate to users. The file implements design principle #1: the engine computes, AI only narrates - this router does all the mathematical estimation work so the LLM can focus purely on explaining the results.

WHAT THIS FILE DOES — step by step
1. Defines confidence level calculation functions that categorize estimate reliability based on sample size of historical jobs
2. Implements core estimation logic that calculates average material consumption rates from past completed jobs
3. Provides a GET endpoint that receives a job ID, validates the job exists and belongs to the current user's tenant
4. Queries the database for historical completed jobs of the same job_type, filtering by tenant_id for security
5. Processes raw_materials JSON data from those historical jobs to calculate per-unit consumption rates
6. Scales those rates by the target job's quantity to produce material quantity estimates
7. Returns a comprehensive response including estimates, confidence levels, explanatory notes, and metadata about the jobs used in calculations

KEY FUNCTIONS / CLASSES / COMPONENTS

Name         : _confidence
Type         : function
Purpose      : Determines confidence level string based on the number of historical jobs found. Uses fixed thresholds: 3+ jobs = "high", 2 jobs = "medium", 1 job = "low", 0 jobs = "none". This provides a standardized way to communicate estimate reliability to the frontend and AI Copilot.
Parameters   : sample_size (int) - number of past jobs used for estimation
Returns      : str - one of "high", "medium", "low", or "none" confidence levels
Calls        : None - pure function with no external dependencies
DB/API       : None - performs no database queries or API calls
Side effects : None - pure calculation function

Name         : _confidence_note
Type         : function
Purpose      : Generates human-readable explanatory text about estimate confidence and limitations. Creates context-aware messages that explain to users why an estimate might be unreliable, helping them make informed decisions about the material planning suggestions.
Parameters   : sample_size (int) - number of past jobs found, job_type (str) - the job type being estimated for context
Returns      : str - explanatory message about estimate reliability and sample size limitations
Calls        : None - pure string formatting function
DB/API       : None - performs no database queries or API calls
Side effects : None - pure text generation function

Name         : _estimate_materials
Type         : function
Purpose      : Core estimation algorithm that processes historical job data to calculate material consumption estimates. For each material type found in past jobs, it calculates the average consumption rate per unit of production, then scales that rate by the target job's quantity to predict needed materials.
Parameters   : past_jobs (List[Job]) - list of completed Job model instances with raw_materials data, target_quantity (float) - quantity of units the target job will produce
Returns      : List[dict] - list of material estimates, each dict containing material name, estimated quantity, unit, average rate per unit, and sample size
Calls        : None - processes data structures in memory without external calls
DB/API       : None - works with already-loaded Job model instances
Side effects : None - pure calculation function that doesn't modify input data

Name         : get_material_estimate
Type         : FastAPI endpoint
Purpose      : Main API endpoint that orchestrates the entire material estimation process. Validates user permissions and job access, loads historical data, and coordinates the estimation calculation. Handles multiple error cases gracefully, returning informative responses when estimation isn't possible due to missing job_type or quantity data.
Parameters   : job_id (int) - ID of the job to estimate materials for, db (Session) - SQLAlchemy database session injected by FastAPI, current_user (User) - authenticated user model injected by auth dependency
Returns      : dict - comprehensive estimation response including job metadata, confidence assessment, material estimates array, and list of historical jobs used in calculation
Calls        : _confidence(), _confidence_note(), _estimate_materials(), plus database queries on Job model
DB/API       : Queries Job table twice: once to load target job, once to find historical completed jobs of same job_type within tenant
Side effects : None - read-only operation that doesn't modify any data

WHO CALLS THIS FILE
- frontend/src/api/api_jobs.ts (or similar job API client) - frontend job management interfaces call this endpoint to display material estimates
- backend/app/main.py - registers this router with the FastAPI application under /api/ prefix
- backend/app/services/ai_service.py - AI Copilot likely calls this endpoint internally to get estimation data before narrating results to users
- Future WhatsApp Copilot services in v5-whatsapp branch - will call this endpoint when users ask "how much material do I need?" via WhatsApp

IMPORTS EXPLAINED
- typing.List, Optional - type hints for function parameters and return values, enabling static type checking and IDE support
- fastapi.APIRouter, Depends, HTTPException - core FastAPI components for defining REST endpoints with dependency injection and error handling
- sqlalchemy.orm.Session - database session type for SQLAlchemy ORM queries, injected via dependency system
- app.database.get_db - dependency function that provides database session instances to endpoints
- app.models.job.Job - SQLAlchemy ORM model representing manufacturing jobs, needed to query historical job data
- app.core.dependencies.get_current_user - authentication dependency that validates JWT tokens and provides current User model
- app.models.auth.User - SQLAlchemy ORM model for authenticated users, used for tenant-based access control

INTERN NOTES
- Easiest thing to break: forgetting tenant_id filtering in database queries - this would leak material data between different companies and is a critical security vulnerability
- Non-obvious design decision: the algorithm uses the most recent unit type when materials have inconsistent units across jobs, rather than trying to convert between units, because unit conversion would require external knowledge the system doesn't have
- Most common mistake: assuming all jobs have raw_materials data populated - many jobs might have empty or null raw_materials arrays, so always check for existence and non-empty data before processing
- Design principle implemented: #1 (Engine computes, AI only narrates) - this router performs all mathematical calculations so the AI Copilot can focus on explaining results rather than computing them
- What to check if behaving unexpectedly: verify that historical jobs have populated raw_materials JSON arrays and non-zero quantity values, as empty data will result in "no estimates available" responses even when jobs exist
- Not applicable to v5-whatsapp merge considerations - this file exists in v4-dev and should merge cleanly into v5-whatsapp without conflicts
"""
```
"""

from __future__ import annotations

from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.job import Job
from app.core.dependencies import get_current_user
from app.models.auth import User

router = APIRouter()


# ─── Confidence thresholds ────────────────────────────────────────────────────

def _confidence(sample_size: int) -> str:
    if sample_size >= 3:
        return "high"
    if sample_size == 2:
        return "medium"
    if sample_size == 1:
        return "low"
    return "none"


def _confidence_note(sample_size: int, job_type: str) -> str:
    if sample_size == 0:
        return f"No completed jobs of type '{job_type}' found. Cannot estimate."
    if sample_size == 1:
        return f"Based on 1 completed job. Estimate may not be representative."
    if sample_size == 2:
        return f"Based on {sample_size} completed jobs. Reasonable estimate."
    return f"Based on {sample_size} completed jobs. High confidence estimate."


# ─── Core estimation logic ────────────────────────────────────────────────────

def _estimate_materials(
    past_jobs: List[Job],
    target_quantity: float,
) -> List[dict]:
    """
    For each material that appears in past jobs:
      1. Calculate consumption per unit (material.quantity / job.quantity)
         for each past job that has both values.
      2. Average those rates across all past jobs.
      3. Multiply by target_quantity to get the estimate.

    Returns a list of estimated material dicts.
    """
    # Accumulate: material_name -> list of (quantity_used, unit)
    rates: dict[str, list[tuple[float, str]]] = {}

    for job in past_jobs:
        if not job.quantity or job.quantity <= 0:
            continue
        raw_mats = job.raw_materials or []
        for mat in raw_mats:
            name = mat.get("name", "").strip()
            qty  = mat.get("quantity")
            unit = mat.get("unit", "")
            if not name or qty is None:
                continue
            rate = float(qty) / float(job.quantity)
            rates.setdefault(name, []).append((rate, unit))

    estimates = []
    for mat_name, rate_list in rates.items():
        avg_rate = sum(r for r, _ in rate_list) / len(rate_list)
        unit     = rate_list[-1][1]   # use most recent unit
        estimated_qty = round(avg_rate * target_quantity, 3)
        estimates.append({
            "material":      mat_name,
            "estimated_qty": estimated_qty,
            "unit":          unit,
            "avg_rate_per_unit": round(avg_rate, 4),
            "sample_size":   len(rate_list),
        })

    # Sort by material name for stable output
    estimates.sort(key=lambda x: x["material"])
    return estimates


# ─── Endpoint ─────────────────────────────────────────────────────────────────

@router.get("/jobs/{job_id}/material-estimate")
def get_material_estimate(
    job_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Returns a material consumption estimate for this job based on
    historical data from completed jobs of the same job_type.
    """
    tenant_id = current_user.tenant_id

    # Load target job
    job = db.query(Job).filter(
        Job.id == job_id,
        Job.tenant_id == tenant_id,
    ).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    # Must have job_type to find comparable jobs
    if not job.job_type:
        return {
            "job_id":      job_id,
            "job_name":    job.name,
            "job_type":    None,
            "quantity":    job.quantity,
            "confidence":  "none",
            "note":        "This job has no job_type set. Set a job_type to enable material estimation.",
            "estimates":   [],
            "past_jobs_used": [],
        }

    # Must have quantity to scale the estimate
    if not job.quantity or job.quantity <= 0:
        return {
            "job_id":      job_id,
            "job_name":    job.name,
            "job_type":    job.job_type,
            "quantity":    None,
            "confidence":  "none",
            "note":        "This job has no quantity set. Set a quantity to enable material estimation.",
            "estimates":   [],
            "past_jobs_used": [],
        }

    # Find past completed jobs of the same job_type (exclude current job)
    past_jobs = db.query(Job).filter(
        Job.tenant_id == tenant_id,
        Job.job_type == job.job_type,
        Job.status == "Completed",
        Job.id != job_id,
        Job.quantity > 0,
        Job.raw_materials.isnot(None),
    ).order_by(Job.created_at.desc()).all()

    # Filter to jobs that actually have raw_materials data
    past_jobs = [j for j in past_jobs if j.raw_materials and len(j.raw_materials) > 0]

    sample_size = len(past_jobs)
    estimates   = _estimate_materials(past_jobs, job.quantity)

    return {
        "job_id":     job_id,
        "job_name":   job.name,
        "job_type":   job.job_type,
        "quantity":   job.quantity,
        "confidence": _confidence(sample_size),
        "note":       _confidence_note(sample_size, job.job_type),
        "estimates":  estimates,
        "past_jobs_used": [
            {
                "job_id":   j.id,
                "job_name": j.name,
                "quantity": j.quantity,
            }
            for j in past_jobs
        ],
    }
