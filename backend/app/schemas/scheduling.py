"""
```python
"""
backend/app/schemas/scheduling.py

FILE PURPOSE
This file defines all Pydantic v2 request/response schemas for the scheduling system in ZetaOps Copilot.
It exists to provide type-safe data validation and serialization for resources (machines/helpers), job steps,
and scheduled jobs that flow between the FastAPI backend and React frontend. This file was introduced in
early v4.x development and sits in the data validation layer between HTTP requests and SQLAlchemy models.

WHAT THIS FILE DOES — step by step
1. Imports Pydantic BaseModel, Field validators, and custom validation decorators
2. Imports enums (ResourceType, SchedJobPriority, etc.) from app.models.scheduling
3. Defines ResourceCreate/Update/Response schemas for machines and helper resources
4. Validates shift times to ensure shift_start comes before shift_end
5. Defines StepCreate/Update/Response schemas for individual job steps
6. Enforces business rules: setup steps use reserve_machine_id, regular steps use required_machine_ids
7. Provides StepStatusUpdate for updating step completion status
8. Adds computed field is_setup_active to determine if a setup step is actively reserving a machine
9. Defines JobCreate/Update/Response schemas for scheduled jobs with priority, deadline, and profit
10. Configures all Response schemas with from_attributes=True for SQLAlchemy ORM compatibility

KEY FUNCTIONS / CLASSES / COMPONENTS

Name         : ResourceCreate
Type         : Pydantic schema class
Purpose      : Validates incoming data when creating new resources (machines or helpers). Enforces name length limits and validates that shift_start occurs before shift_end to prevent invalid work schedules.
Parameters   : name (str, 1-150 chars), type (ResourceType enum), shift_start (time, default 8:00), shift_end (time, default 16:00)
Returns      : Validated ResourceCreate instance ready for database insertion
Calls        : Built-in Pydantic validation, no external files
DB/API       : No direct calls, used by CRUD operations
Side effects : Raises ValueError if shift times are invalid

Name         : ResourceUpdate
Type         : Pydantic schema class
Purpose      : Validates partial updates to existing resources. All fields are optional to support PATCH-style updates. Validates shift times only when both are provided to avoid false positives during partial updates.
Parameters   : name (Optional[str]), shift_start (Optional[time]), shift_end (Optional[time])
Returns      : Validated ResourceUpdate instance for database updates
Calls        : Built-in Pydantic validation, no external files
DB/API       : No direct calls, used by CRUD operations
Side effects : Raises ValueError if both shift times provided and invalid

Name         : ResourceResponse
Type         : Pydantic schema class
Purpose      : Serializes database Resource models into JSON responses for the frontend. Includes all resource fields plus metadata like created_at for audit trails.
Parameters   : Auto-populated from SQLAlchemy model attributes
Returns      : JSON-serializable dict when converted
Calls        : No external calls, pure data container
DB/API       : Reads from database via from_attributes=True
Side effects : None, read-only response schema

Name         : StepCreate
Type         : Pydantic schema class
Purpose      : Validates new job step creation with complex business logic. Enforces that setup steps cannot have required_machine_ids (they use reserve_machine_id instead) and regular steps cannot reserve machines. This separation allows setup steps to block machines without actually running them.
Parameters   : step_type (StepType enum), duration_minutes (int ≥1), required_machine_ids (List[int]), required_helper_ids (List[int]), reserve_machine_id (Optional[int])
Returns      : Validated StepCreate instance with enforced business rules
Calls        : Built-in Pydantic validation, no external files
DB/API       : No direct calls, used by CRUD operations
Side effects : Raises ValueError if step type rules are violated

Name         : StepUpdate
Type         : Pydantic schema class
Purpose      : Validates partial updates to job steps while maintaining the same business rules as StepCreate. All fields optional for PATCH updates, but still enforces setup vs regular step constraints when step_type is being changed.
Parameters   : All StepCreate fields as Optional types
Returns      : Validated StepUpdate instance for database updates
Calls        : Built-in Pydantic validation, no external files
DB/API       : No direct calls, used by CRUD operations
Side effects : Raises ValueError if step type rules are violated

Name         : StepStatusUpdate
Type         : Pydantic schema class
Purpose      : Simple schema for updating only the status field of a job step. Used by job execution endpoints to mark steps as started, completed, or failed without touching other step data.
Parameters   : status (StepStatus enum)
Returns      : Validated status update for database
Calls        : No external calls
DB/API       : No direct calls, used by CRUD operations
Side effects : None

Name         : StepResponse
Type         : Pydantic schema class
Purpose      : Serializes database JobStep models into JSON responses with a computed field. The is_setup_active computed property helps the frontend quickly identify which setup steps are actively reserving machines for visual indicators and scheduling logic.
Parameters   : Auto-populated from SQLAlchemy model attributes
Returns      : JSON response with computed is_setup_active boolean
Calls        : No external calls, computed field uses self attributes
DB/API       : Reads from database via from_attributes=True
Side effects : None, read-only response schema

Name         : JobCreate
Type         : Pydantic schema class
Purpose      : Validates creation of new scheduled jobs with business constraints. Enforces positive expected_profit values and name length limits. Provides sensible defaults for priority (low) and shift (morning) while requiring explicit deadlines.
Parameters   : name (str, 1-200 chars), priority (SchedJobPriority), expected_profit (Optional[float] ≥0), deadline (datetime), shift (SchedJobShift), lock_status (bool, default False)
Returns      : Validated JobCreate instance for database insertion
Calls        : Built-in Pydantic validation, no external files
DB/API       : No direct calls, used by CRUD operations
Side effects : None

Name         : JobUpdate
Type         : Pydantic schema class
Purpose      : Validates partial updates to scheduled jobs with all optional fields. Allows updating job status, priority changes, deadline extensions, and profit adjustments. Maintains same validation rules as JobCreate for non-null values.
Parameters   : All JobCreate fields as Optional, plus status (Optional[SchedJobStatus])
Returns      : Validated JobUpdate instance for database updates
Calls        : Built-in Pydantic validation, no external files
DB/API       : No direct calls, used by CRUD operations
Side effects : None

Name         : JobResponse
Type         : Pydantic schema class
Purpose      : Serializes complete scheduled jobs with their associated steps for frontend display. Includes nested StepResponse objects to provide full job hierarchy in a single API response, reducing frontend API calls.
Parameters   : Auto-populated from SQLAlchemy model attributes, steps as List[StepResponse]
Returns      : Complete job data with nested steps for frontend
Calls        : StepResponse schema for nested steps
DB/API       : Reads from database via from_attributes=True, includes relationship data
Side effects : None, read-only response schema

WHO CALLS THIS FILE
- backend/app/routers/scheduler_router.py imports these schemas for FastAPI endpoint type hints
- backend/app/crud/scheduling.py uses these schemas in database
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
