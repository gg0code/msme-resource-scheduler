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
