"""
schemas/availability.py
-----------------------
Pydantic schemas for Availability Override endpoints.
Overrides record day-specific availability percentages for employees (leave, half-days)
or machines (scheduled maintenance). Either employee_id or machine_id must be set.
"""

from pydantic import BaseModel
from typing import Optional
from datetime import date, datetime


class AvailabilityOverrideBase(BaseModel):
    """Shared fields used by Create and Out schemas."""
    employee_id: Optional[int] = None    # Set this OR machine_id, not both
    machine_id: Optional[int] = None
    date_from: date
    date_to: date                        # For a single-day override: date_from == date_to
    availability_pct: float = 0.0        # 0 = fully unavailable; 50 = half-day
    reason: Optional[str] = None


class AvailabilityOverrideCreate(AvailabilityOverrideBase):
    """
    Request body for POST /api/availability/.

    Input  : employee_id or machine_id, date range, availability percentage, optional reason.
    Output : Validated payload used by the router to insert a new override row.
    """
    pass


class AvailabilityOverrideUpdate(BaseModel):
    """
    Request body for PATCH /api/availability/{id}.
    All fields are optional for partial updates.

    Input  : Any subset of override fields to modify.
    Output : Validated payload used by the router to apply selective updates.
    """
    date_from: Optional[date] = None
    date_to: Optional[date] = None
    availability_pct: Optional[float] = None
    reason: Optional[str] = None


class AvailabilityOverrideOut(AvailabilityOverrideBase):
    """
    Response schema for all Availability Override endpoints.

    Input  : SQLAlchemy AvailabilityOverride ORM object.
    Output : Full override record including id and created_at timestamp.
    """
    id: int
    created_at: datetime

    model_config = {"from_attributes": True}
