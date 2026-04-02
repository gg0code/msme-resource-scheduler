"""
```python
"""
backend/app/schemas/resource_availability.py

FILE PURPOSE
This file defines Pydantic v2 response schemas for the GET /api/jobs/{job_id}/resource-availability 
endpoint, which computes and returns employee and machine availability for a specific job's date 
range. It was introduced in v3.9.4 to support the frontend's resource availability checking feature, 
sitting in the API layer between the availability computation engine and the React frontend that 
displays resource conflicts to users.

WHAT THIS FILE DOES — step by step
1. Imports Pydantic BaseModel, typing utilities, and datetime.date for schema validation
2. Defines BlockingJob schema to describe jobs that are consuming resource capacity
3. Defines DateRange schema to represent the job's start/end date window
4. Defines EmployeeAvailability schema with percentage-based capacity calculations
5. Defines MachineAvailability schema with binary availability status
6. Defines ResourceAvailabilityResponse as the top-level API response wrapper
7. Pre-allocates empty materials list for future v3.9.5 inventory tracking feature

KEY FUNCTIONS / CLASSES / COMPONENTS

Name         : BlockingJob
Type         : Pydantic schema class
Purpose      : Represents a job that is blocking a resource (employee or machine) during the 
               checked job's date range. Used to show users which specific jobs are causing 
               resource conflicts. Contains job identification and overlap details.
Parameters   : job_id (int) - database ID of blocking job, job_name (str) - display name, 
               allocation_pct (Optional[int]) - percentage allocation for employee conflicts, 
               start_date/end_date (Optional[date]) - date window for machine conflicts
Returns      : Validated schema instance for API serialization
Calls        : None (pure data schema)
DB/API       : None (populated by availability engine, not this schema)
Side effects : None

Name         : DateRange
Type         : Pydantic schema class
Purpose      : Represents the start and end date of the job being checked for resource 
               availability. Provides the time window for all availability calculations.
Parameters   : start (date) - job start date, end (date) - job end date
Returns      : Validated date range for API response
Calls        : None (pure data schema)
DB/API       : None (dates come from Job model via availability service)
Side effects : None

Name         : EmployeeAvailability
Type         : Pydantic schema class
Purpose      : Computed availability status for one employee during the job's date range. 
               Calculates percentage-based capacity using base availability minus existing 
               allocations. Shows what capacity remains available for the job being checked.
Parameters   : employee_id (int) - database ID, name (str) - display name, base_pct (float) - 
               configured availability percentage, allocated_pct (float) - sum of existing 
               allocations, free_pct (float) - remaining capacity, status (str) - availability 
               status, blocking_jobs (List[BlockingJob]) - conflicting job assignments
Returns      : Employee availability data for frontend display
Calls        : None (pure data schema)
DB/API       : None (populated by availability_engine.py computations)
Side effects : None

Name         : MachineAvailability
Type         : Pydantic schema class
Purpose      : Computed availability status for one machine during the job's date range. 
               Uses binary availability since machines can only work on one job at a time. 
               Shows whether machine is free or busy with specific blocking job details.
Parameters   : machine_id (int) - database ID, name (str) - display name, is_free (bool) - 
               availability flag, status (str) - 'free' or 'busy', blocking_jobs 
               (List[BlockingJob]) - jobs using this machine in the date range
Returns      : Machine availability data for frontend conflict display
Calls        : None (pure data schema)
DB/API       : None (populated by availability_engine.py binary checks)
Side effects : None

Name         : ResourceAvailabilityResponse
Type         : Pydantic schema class
Purpose      : Top-level response wrapper for the resource availability endpoint. Combines 
               job date range, employee availability list, machine availability list, and 
               error states into a single API response. Includes placeholder for future 
               materials tracking to avoid breaking frontend contract in v3.9.5.
Parameters   : job_id (int) - target job ID, date_range (Optional[DateRange]) - job dates, 
               employees (List[EmployeeAvailability]) - employee availability data, 
               machines (List[MachineAvailability]) - machine availability data, 
               materials (List) - empty placeholder for inventory, error (Optional[str]) - 
               error state like 'no_dates'
Returns      : Complete resource availability response for API serialization
Calls        : None (pure data schema)
DB/API       : None (aggregates data from availability computations)
Side effects : None

WHO CALLS THIS FILE
- backend/app/routers/scheduler_router.py imports these schemas for GET /api/jobs/{job_id}/resource-availability endpoint response typing
- backend/app/services/availability_engine.py imports these schemas to structure its computed availability data into API-ready format
- FastAPI automatically uses these schemas for response validation and OpenAPI documentation generation

IMPORTS EXPLAINED
- from __future__ import annotations: Enables forward reference annotations for Python 3.9+ compatibility with optional typing
- from pydantic import BaseModel: Core Pydantic class for creating validated data schemas with automatic serialization
- from typing import List, Optional: Type hints for list collections and nullable fields in schema definitions
- from datetime import date: Python date type for start_date/end_date fields in job date ranges

INTERN NOTES
- Easiest thing to break: Adding required fields to existing schemas will break frontend API contract - always use Optional for new fields or coordinate frontend updates
- Non-obvious design decision: Materials list is intentionally empty to avoid frontend changes when inventory tracking is added in v3.9.5, maintaining API stability
- Most common mistake: Forgetting that BlockingJob uses different fields for employees (allocation_pct) vs machines (start_date/end_date) based on conflict type
- Design principle implemented: Principle #1 - Engine computes, AI only narrates - these schemas only shape computed data, never perform availability calculations
- What to check if unexpected behavior: Verify availability_engine.py is populating schema fields correctly and check that frontend is handling optional fields properly
- Version context: This is v4-dev stable code with forward compatibility design for v3.9.5 inventory features, no WhatsApp-specific considerations
"""
```
"""

from __future__ import annotations
from pydantic import BaseModel
from typing import List, Optional
from datetime import date


# ---------------------------------------------------------------------------
# Shared sub-models
# ---------------------------------------------------------------------------

class BlockingJob(BaseModel):
    """
    Describes a job that is blocking a resource (employee or machine)
    on the dates of the job being checked.
    allocation_pct is only relevant for employees (machines are binary).
    start_date / end_date are only relevant for machines (to show the blocking window).
    """
    job_id: int
    job_name: str
    allocation_pct: Optional[int] = None   # employee overlap only
    start_date: Optional[date] = None      # machine overlap only
    end_date: Optional[date] = None        # machine overlap only


class DateRange(BaseModel):
    """
    The start and end date of the job being checked.
    Null when the job has no dates set yet.
    """
    start: date
    end: date


# ---------------------------------------------------------------------------
# Employee availability
# ---------------------------------------------------------------------------

class EmployeeAvailability(BaseModel):
    """
    Computed availability for one employee on the job's specific date range.

    base_pct     — the employee's configured base availability (e.g. 100)
    allocated_pct — sum of allocation_pct from other overlapping job assignments
    free_pct     — base_pct minus allocated_pct (what is left for this job)
    status       — 'free' | 'partial' | 'unavailable'
    blocking_jobs — list of other jobs consuming this employee's capacity on these dates
    """
    employee_id: int
    name: str
    base_pct: float
    allocated_pct: float
    free_pct: float
    status: str          # free | partial | unavailable
    blocking_jobs: List[BlockingJob]


# ---------------------------------------------------------------------------
# Machine availability
# ---------------------------------------------------------------------------

class MachineAvailability(BaseModel):
    """
    Computed availability for one machine on the job's specific date range.
    Machines are exclusive — they can only be on one job at a time.

    is_free      — True if no other job is using this machine on these dates
    status       — 'free' | 'busy'
    blocking_jobs — the job(s) that have this machine booked on overlapping dates
    """
    machine_id: int
    name: str
    is_free: bool
    status: str          # free | busy
    blocking_jobs: List[BlockingJob]


# ---------------------------------------------------------------------------
# Top-level response
# ---------------------------------------------------------------------------

class ResourceAvailabilityResponse(BaseModel):
    """
    Full response for GET /api/jobs/{job_id}/resource-availability.

    date_range   — the job's start/end dates used for the availability computation
    employees    — list of EmployeeAvailability for each employee assigned to this job
    machines     — list of MachineAvailability for each machine assigned to this job
    materials    — always empty list in v3.9.4, populated in v3.9.5 when stock tracking is added
    error        — 'no_dates' when the job has no start/end date set, None otherwise
    """
    job_id: int
    date_range: Optional[DateRange] = None
    employees: List[EmployeeAvailability] = []
    machines: List[MachineAvailability] = []
    materials: List = []                   # reserved for v3.9.5 stock tracking
    error: Optional[str] = None
