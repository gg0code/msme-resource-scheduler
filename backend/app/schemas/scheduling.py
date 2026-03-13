"""
app/schemas/scheduling.py — Prompt 1 Pydantic schemas

Computed field on StepResponse:
  is_setup_active: True when step_type=setup AND reserve_machine_id is set
"""

from __future__ import annotations

from datetime import datetime, time
from typing import List, Optional

from pydantic import BaseModel, Field, model_validator, computed_field

from app.models.scheduling import (
    ResourceType, SchedJobPriority, SchedJobShift,
    SchedJobStatus, StepStatus, StepType,
)


# ─────────────────────────────────────────────────────────────────────────────
# Resource schemas
# ─────────────────────────────────────────────────────────────────────────────

class ResourceCreate(BaseModel):
    name:        str          = Field(..., min_length=1, max_length=150)
    type:        ResourceType
    shift_start: time         = time(8, 0)
    shift_end:   time         = time(16, 0)

    @model_validator(mode="after")
    def check_shift(self) -> "ResourceCreate":
        if self.shift_start >= self.shift_end:
            raise ValueError("shift_start must be earlier than shift_end")
        return self


class ResourceUpdate(BaseModel):
    name:        Optional[str]  = None
    shift_start: Optional[time] = None
    shift_end:   Optional[time] = None

    @model_validator(mode="after")
    def check_shift(self) -> "ResourceUpdate":
        s, e = self.shift_start, self.shift_end
        if s is not None and e is not None and s >= e:
            raise ValueError("shift_start must be earlier than shift_end")
        return self


class ResourceResponse(BaseModel):
    id:          int
    tenant_id:   int
    name:        str
    type:        ResourceType
    shift_start: time
    shift_end:   time
    created_at:  datetime

    model_config = {"from_attributes": True}


# ─────────────────────────────────────────────────────────────────────────────
# Step schemas
# ─────────────────────────────────────────────────────────────────────────────

class StepCreate(BaseModel):
    step_type:           StepType          = StepType.regular
    duration_minutes:    int               = Field(..., ge=1)
    required_machine_ids: List[int]        = Field(default_factory=list)
    required_helper_ids:  List[int]        = Field(default_factory=list)
    reserve_machine_id:   Optional[int]    = None

    @model_validator(mode="after")
    def validate_step_type_rules(self) -> "StepCreate":
        if self.step_type == StepType.setup:
            if self.required_machine_ids:
                raise ValueError(
                    "Setup steps cannot have required_machine_ids. "
                    "Use reserve_machine_id to block a machine without running it."
                )
        else:  # regular
            if self.reserve_machine_id is not None:
                raise ValueError(
                    "reserve_machine_id is only valid for setup steps."
                )
        return self


class StepUpdate(BaseModel):
    step_type:            Optional[StepType]   = None
    duration_minutes:     Optional[int]        = Field(default=None, ge=1)
    required_machine_ids: Optional[List[int]]  = None
    required_helper_ids:  Optional[List[int]]  = None
    reserve_machine_id:   Optional[int]        = None

    @model_validator(mode="after")
    def validate_step_type_rules(self) -> "StepUpdate":
        if self.step_type == StepType.setup and self.required_machine_ids:
            raise ValueError("Setup steps cannot have required_machine_ids.")
        if self.step_type == StepType.regular and self.reserve_machine_id is not None:
            raise ValueError("reserve_machine_id is only valid for setup steps.")
        return self


class StepStatusUpdate(BaseModel):
    status: StepStatus


class StepResponse(BaseModel):
    id:                   int
    job_id:               int
    sequence_order:       int
    step_type:            StepType
    duration_minutes:     int
    status:               StepStatus
    required_machine_ids: List[int]
    required_helper_ids:  List[int]
    reserve_machine_id:   Optional[int]
    created_at:           datetime
    updated_at:           datetime

    # Computed: True when step is setup AND a machine is reserved
    @computed_field  # type: ignore[misc]
    @property
    def is_setup_active(self) -> bool:
        return self.step_type == StepType.setup and self.reserve_machine_id is not None

    model_config = {"from_attributes": True}

    @classmethod
    def from_orm(cls, step) -> "StepResponse":
        return cls(
            id=step.id,
            job_id=step.job_id,
            sequence_order=step.sequence_order,
            step_type=step.step_type,
            duration_minutes=step.duration_minutes,
            status=step.status,
            required_machine_ids=[m.resource_id for m in step.machine_links],
            required_helper_ids=[h.resource_id for h in step.helper_links],
            reserve_machine_id=step.reserve_machine_id,
            created_at=step.created_at,
            updated_at=step.updated_at,
        )


# ─────────────────────────────────────────────────────────────────────────────
# Job schemas
# ─────────────────────────────────────────────────────────────────────────────

class JobCreate(BaseModel):
    name:            str                  = Field(..., min_length=1, max_length=200)
    priority:        SchedJobPriority     = SchedJobPriority.low
    expected_profit: Optional[float]      = Field(default=None, ge=0)
    deadline:        datetime
    shift:           SchedJobShift        = SchedJobShift.morning
    lock_status:     bool                 = False


class JobUpdate(BaseModel):
    name:            Optional[str]             = None
    priority:        Optional[SchedJobPriority] = None
    expected_profit: Optional[float]           = Field(default=None, ge=0)
    deadline:        Optional[datetime]        = None
    shift:           Optional[SchedJobShift]   = None
    lock_status:     Optional[bool]            = None
    status:          Optional[SchedJobStatus]  = None


class JobResponse(BaseModel):
    id:              int
    tenant_id:       int
    name:            str
    priority:        SchedJobPriority
    expected_profit: Optional[float]
    deadline:        datetime
    shift:           SchedJobShift
    lock_status:     bool
    status:          SchedJobStatus
    steps:           List[StepResponse] = []
    created_at:      datetime
    updated_at:      datetime

    model_config = {"from_attributes": True}
