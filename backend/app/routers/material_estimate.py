"""
backend/app/routers/material_estimate.py — v3.9.8

GET /api/jobs/{job_id}/material-estimate

Finds all past completed jobs of the same job_type, calculates average
material consumption per unit, and returns an estimate for the current
job based on its quantity.

Prerequisite for AI Copilot "how much material do I need?" feature (v3.9.9).
Engine does the computation. AI only narrates.

Confidence levels:
  high    — 3 or more past jobs found
  medium  — exactly 2 past jobs found
  low     — only 1 past job found
  none    — no past jobs found (returns empty estimate)
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
