# schemas/machine.py - Version 1.1
# Branch: both
#
# FILE PURPOSE
# Pydantic V2 schemas for Machine API request validation and response shaping.
#
# WHO CALLS THIS FILE
#   app/routers/machines.py - uses MachineCreate, MachineUpdate, MachineOut
#
# WHAT THIS FILE CALLS
#   app/models/employee.py - VALID_SOURCE_VALUES (shared constant)
#
# KEY DESIGN DECISIONS (v1.1 changes)
#   - Added source to Create/Update/Out (v5.16).
#   - Fixed class Config to model_config = ConfigDict(from_attributes=True)
#     per Pydantic V2. class Config was deprecated in V2.0.
#   - source defaults to 'manual' - Day 1 table always creates records manually.

from typing import Optional, List

from pydantic import BaseModel, ConfigDict

from app.models.employee import VALID_SOURCE_VALUES


class MachineSkillReqIn(BaseModel):
    """Skill requirement input for a machine."""
    skill_id:           int
    min_skill_level:    str = "Generic"
    employees_required: int = 1


class MachineSkillReqOut(BaseModel):
    """Skill requirement output — includes DB id."""
    id:                 int
    skill_id:           int
    min_skill_level:    str
    employees_required: int
    model_config = ConfigDict(from_attributes=True)


class MachineCreate(BaseModel):
    """
    Input schema for POST /api/machines/.
    source defaults to 'manual' - Day 1 table always creates manually.
    """
    name:                  str
    machine_type:          Optional[str]   = None
    base_availability_pct: float           = 100.0
    location_bay:          Optional[str]   = None
    status:                str             = "Operational"
    hourly_rate:           Optional[float] = None
    source:                str             = "manual"
    skill_requirements:    List[MachineSkillReqIn] = []


class MachineUpdate(BaseModel):
    """
    Input schema for PATCH /api/machines/{id}.
    All fields optional - only provided fields are updated.
    """
    name:                  Optional[str]   = None
    machine_type:          Optional[str]   = None
    base_availability_pct: Optional[float] = None
    location_bay:          Optional[str]   = None
    status:                Optional[str]   = None
    hourly_rate:           Optional[float] = None
    source:                Optional[str]   = None
    skill_requirements:    Optional[List[MachineSkillReqIn]] = None


class MachineOut(BaseModel):
    """
    Output schema for GET /api/machines/ and GET /api/machines/{id}.
    Includes source so frontend can distinguish record origin.
    """
    id:                    int
    name:                  str
    machine_type:          Optional[str]
    base_availability_pct: float
    location_bay:          Optional[str]
    status:                str
    hourly_rate:           Optional[float]
    source:                str
    skill_requirements:    List[MachineSkillReqOut] = []
    model_config = ConfigDict(from_attributes=True)
