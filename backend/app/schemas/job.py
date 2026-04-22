"""
schemas/job.py
--------------
Pydantic schemas for the Job API, including the nested JobSkillRequirement schema.
Jobs carry the most complex payload — date ranges, profit figures, priority, status
lifecycle, embedded skill requirements, and a list of required machine IDs.
"""

from pydantic import BaseModel
from typing import Optional, List
from datetime import date, datetime


class JobSkillReqIn(BaseModel):
    """
    Nested schema for one skill requirement when creating or updating a job.

    Input  : skill_id, min_skill_level (Generic/Intermediate/Premium),
             employees_required (how many workers with that skill are needed).
    Output : Used inside JobCreate / JobUpdate payloads.
    """
    skill_id: int
    min_skill_level: str = "Generic"
    employees_required: int = 1


class JobSkillReqOut(JobSkillReqIn):
    """
    Nested skill requirement returned in job responses.

    Input  : SQLAlchemy JobSkillRequirement ORM object.
    Output : Includes the DB-assigned id and an optional denormalised skill_name.
    """
    id: int
    skill_name: Optional[str] = None
    model_config = {"from_attributes": True}


class JobBase(BaseModel):
    """Shared core fields for Create and Out schemas."""
    name: str
    customer: Optional[str] = None
    description: Optional[str] = None
    start_date: date
    end_date: date
    estimated_hours_per_day: float = 8.0
    tentative_profit: Optional[float] = None     # INR
    job_type: Optional[str] = None
    quantity: Optional[float] = None
    priority: str = "Medium"                      # Low/Medium/High/Critical
    status: str = "Draft"
    notes: Optional[str] = None


class JobCreate(JobBase):
    """
    Request body for POST /api/jobs/.

    Input  : All job fields, an optional list of skill requirements, and an
             optional list of machine_ids that this job will use.
    Output : Validated payload passed to the router for DB insert + skill req sync.
    """
    skill_requirements: List[JobSkillReqIn] = []
    machine_ids: List[int] = []


class JobUpdate(BaseModel):
    """
    Request body for PATCH /api/jobs/{id}.
    All fields are optional for partial updates.

    Input  : Any subset of job fields; if skill_requirements is provided,
             existing requirements are fully replaced.
    Output : Validated payload used by the router to apply selective updates.
    """
    name: Optional[str] = None
    customer: Optional[str] = None
    description: Optional[str] = None
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    estimated_hours_per_day: Optional[float] = None
    tentative_profit: Optional[float] = None
    job_type: Optional[str] = None
    quantity: Optional[float] = None
    priority: Optional[str] = None
    status: Optional[str] = None
    notes: Optional[str] = None
    skill_requirements: Optional[List[JobSkillReqIn]] = None
    machine_ids: Optional[List[int]] = None


class JobOut(JobBase):
    """
    Response schema for all Job endpoints.

    Input  : SQLAlchemy Job ORM object with loaded skill_requirements relationship.
    Output : Full job record with nested skill requirement list and timestamps.
    """
    id: int
    skill_requirements: List[JobSkillReqOut] = []
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
