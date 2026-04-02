"""
```python
"""
FILE PURPOSE
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
This file defines Pydantic v2 schemas for the Job domain model, which represents manufacturing work orders in the ZetaOps Copilot system. Jobs are the core entity that gets scheduled by the scheduling engine, carrying complex data including skill requirements, machine assignments, profit calculations, priority levels, and date constraints. This file was part of the original v4 architecture and exists in both v4-dev and v5-whatsapp branches. It sits in the schemas layer, providing data validation and serialization between the FastAPI routers and the frontend API clients.

WHAT THIS FILE DOES — step by step
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
1. Imports Pydantic BaseModel and typing utilities to define data validation schemas
2. Defines JobSkillReqIn schema for input skill requirement data (skill_id, min_skill_level, employees_required)
3. Extends JobSkillReqIn with JobSkillReqOut to include database-assigned id and optional skill_name for responses
4. Creates JobBase schema containing shared fields used by both creation and response schemas
5. Defines JobCreate schema for POST requests, including nested skill requirements and machine ID lists
6. Creates JobUpdate schema for PATCH requests with all optional fields for partial updates
7. Defines JobOut schema for API responses, combining JobBase with database metadata and nested skill requirements

KEY FUNCTIONS / CLASSES / COMPONENTS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Name         : JobSkillReqIn
Type         : Pydantic BaseModel class
Purpose      : Validates input data for skill requirements when creating or updating jobs. Represents the minimum skill level needed and how many employees with that skill are required for the job.
Parameters   : skill_id (int) - foreign key to Skill table, min_skill_level (str) - defaults to "Generic", can be "Intermediate" or "Premium", employees_required (int) - defaults to 1, number of workers needed
Returns      : Validated skill requirement object used in job creation/update payloads
Calls        : No other functions (pure data schema)
DB/API       : No direct database calls (used by routers that do DB operations)
Side effects : None (validation only)

Name         : JobSkillReqOut
Type         : Pydantic BaseModel class (inherits JobSkillReqIn)
Purpose      : Extends JobSkillReqIn for API responses, adding database-assigned fields. Includes the primary key id and an optional denormalized skill_name for frontend display without additional API calls.
Parameters   : Inherits all JobSkillReqIn fields plus id (int) - database primary key, skill_name (Optional[str]) - denormalized skill name for display
Returns      : Complete skill requirement object for API responses
Calls        : No other functions (pure data schema)
DB/API       : Uses from_attributes=True to populate from SQLAlchemy ORM objects
Side effects : None (serialization only)

Name         : JobBase
Type         : Pydantic BaseModel class
Purpose      : Contains shared core fields used by both job creation and response schemas. Includes business-critical fields like dates, profit estimates, priority levels, and status tracking.
Parameters   : name (str) - job title, customer (Optional[str]) - client name, description (Optional[str]) - job details, start_date/end_date (date) - scheduling boundaries, estimated_hours_per_day (float) - defaults to 8.0 for capacity planning, tentative_profit (Optional[float]) - expected revenue in INR, priority (str) - defaults to "Medium", can be Low/High/Critical, status (str) - defaults to "Draft", notes (Optional[str]) - additional information
Returns      : Base job data structure for inheritance
Calls        : No other functions (pure data schema)
DB/API       : No direct database operations
Side effects : None (data structure definition only)

Name         : JobCreate
Type         : Pydantic BaseModel class (inherits JobBase)
Purpose      : Validates request body for POST /api/jobs/ endpoint. Combines core job fields with nested skill requirements and machine assignments. Used by the job router to create new jobs with all their dependencies.
Parameters   : Inherits all JobBase fields plus skill_requirements (List[JobSkillReqIn]) - defaults to empty list, machine_ids (List[int]) - defaults to empty list, machine foreign keys
Returns      : Validated job creation payload ready for database insertion
Calls        : No other functions (used by job router)
DB/API       : No direct database calls (consumed by router that does DB operations)
Side effects : None (validation only)

Name         : JobUpdate
Type         : Pydantic BaseModel class
Purpose      : Validates request body for PATCH /api/jobs/{id} endpoint. All fields are optional to support partial updates. When skill_requirements is provided, it completely replaces existing requirements rather than merging.
Parameters   : All JobBase fields as optional, plus skill_requirements (Optional[List[JobSkillReqIn]]) - if provided, replaces all existing requirements, machine_ids (Optional[List[int]]) - if provided, replaces all machine assignments
Returns      : Validated partial update payload for selective field updates
Calls        : No other functions (used by job router)
DB/API       : No direct database calls (consumed by router that does DB operations)
Side effects : None (validation only)

Name         : JobOut
Type         : Pydantic BaseModel class (inherits JobBase)
Purpose      : Serializes complete job records for all API responses. Includes database metadata like timestamps and primary keys, plus fully populated nested skill requirements for frontend consumption.
Parameters   : Inherits all JobBase fields plus id (int) - database primary key, skill_requirements (List[JobSkillReqOut]) - defaults to empty list, nested skill data with IDs, created_at/updated_at (datetime) - audit timestamps
Returns      : Complete job record ready for JSON serialization to frontend
Calls        : No other functions (used by job router)
DB/API       : Uses from_attributes=True to serialize from SQLAlchemy Job ORM objects with loaded relationships
Side effects : None (serialization only)

WHO CALLS THIS FILE
━━━━━━━━━━━━━━━━━━━
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
