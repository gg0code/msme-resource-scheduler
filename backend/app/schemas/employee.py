# schemas/employee.py - Version 1.1
# Branch: both
#
# FILE PURPOSE
# Pydantic V2 schemas for Employee API request validation and response shaping.
#
# WHO CALLS THIS FILE
#   app/routers/employees.py - uses EmployeeCreate, EmployeeUpdate, EmployeeOut
#   app/routers/auth.py      - indirectly via UserResponse
#
# WHAT THIS FILE CALLS
#   app/models/employee.py - VALID_SOURCE_VALUES, VALID_WORKER_TYPE_VALUES
#
# KEY DESIGN DECISIONS (v1.1 changes)
#   - Added source and worker_type to Create/Update/Out (v5.16).
#   - Fixed class Config to model_config = ConfigDict(from_attributes=True)
#     per Pydantic V2. class Config was deprecated in V2.0.
#   - source defaults to 'manual' in Create - the Day 1 table always creates
#     records manually. Only the whatsapp pipeline sets 'whatsapp'.
#   - worker_type defaults to 'permanent'. Contractor flag set explicitly.

from datetime import date
from typing import Optional, List

from pydantic import BaseModel, ConfigDict

from app.models.employee import VALID_SOURCE_VALUES, VALID_WORKER_TYPE_VALUES


class EmployeeSkillIn(BaseModel):
    """Skill assignment input — skill_id + level."""
    skill_id:    int
    skill_level: str = "Generic"


class EmployeeSkillOut(BaseModel):
    """Skill assignment output — includes DB id."""
    id:          int
    skill_id:    int
    skill_level: str
    model_config = ConfigDict(from_attributes=True)


class EmployeeCreate(BaseModel):
    """
    Input schema for POST /api/employees/.
    source defaults to 'manual' - Day 1 table always creates manually.
    worker_type defaults to 'permanent'.
    """
    full_name:             str
    department:            Optional[str]   = None
    employment_type:       str             = "Full-time"
    base_availability_pct: float           = 100.0
    status:                str             = "Active"
    contact_number:        Optional[str]   = None
    join_date:             Optional[date]  = None
    hourly_rate:           Optional[float] = None
    overtime_rate:         Optional[float] = None
    source:                str             = "manual"
    worker_type:           str             = "permanent"
    skills:                List[EmployeeSkillIn] = []


class EmployeeUpdate(BaseModel):
    """
    Input schema for PATCH /api/employees/{id}.
    All fields optional - only provided fields are updated.
    """
    full_name:             Optional[str]   = None
    department:            Optional[str]   = None
    employment_type:       Optional[str]   = None
    base_availability_pct: Optional[float] = None
    status:                Optional[str]   = None
    contact_number:        Optional[str]   = None
    join_date:             Optional[date]  = None
    hourly_rate:           Optional[float] = None
    overtime_rate:         Optional[float] = None
    source:                Optional[str]   = None
    worker_type:           Optional[str]   = None
    skills:                Optional[List[EmployeeSkillIn]] = None


class EmployeeOut(BaseModel):
    """
    Output schema for GET /api/employees/ and GET /api/employees/{id}.
    Includes source and worker_type so frontend can distinguish record origin.
    """
    id:                    int
    full_name:             str
    department:            Optional[str]
    employment_type:       str
    base_availability_pct: float
    status:                str
    contact_number:        Optional[str]
    join_date:             Optional[date]
    hourly_rate:           Optional[float]
    overtime_rate:         Optional[float]
    source:                str
    worker_type:           str
    skills:                List[EmployeeSkillOut] = []
    model_config = ConfigDict(from_attributes=True)
