"""
schemas/skill.py
----------------
Pydantic schemas that define the shape of HTTP request bodies and response payloads
for the Skills API. Keeps validation logic separate from the ORM layer.
Three schema variants follow the standard pattern: Create (input), Update (partial input), Out (response).
"""

from pydantic import BaseModel
from typing import Optional
from datetime import datetime


class SkillBase(BaseModel):
    """Shared fields used by both Create and Out schemas."""
    name: str
    category: str           # "generic" | "premium"
    is_premium: bool = False
    description: Optional[str] = None


class SkillCreate(SkillBase):
    """
    Request body for POST /api/skills/.

    Input  : name, category, is_premium (optional), description (optional).
    Output : Used by the router to validate incoming JSON before DB insert.
    """
    pass


class SkillUpdate(BaseModel):
    """
    Request body for PATCH /api/skills/{id}.
    All fields are optional — only provided fields are updated (partial update).

    Input  : Any subset of skill fields.
    Output : Used by the router to apply selective updates to the ORM object.
    """
    name: Optional[str] = None
    category: Optional[str] = None
    is_premium: Optional[bool] = None
    description: Optional[str] = None
    is_active: Optional[bool] = None


class SkillOut(SkillBase):
    """
    Response schema returned by all Skill endpoints.

    Input  : SQLAlchemy Skill ORM object (from_attributes=True enables ORM mode).
    Output : Serialised JSON with all skill fields including id and timestamps.
    """
    id: int
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
