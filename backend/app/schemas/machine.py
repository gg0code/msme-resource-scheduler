"""
schemas/machine.py
------------------
Pydantic schemas for Machine API. Includes hourly_rate for running costs.
"""

from pydantic import BaseModel
from typing import Optional, List

class MachineSkillReqIn(BaseModel):
    skill_id: int
    min_skill_level: str = "Generic"
    employees_required: int = 1

class MachineSkillReqOut(BaseModel):
    id: int
    skill_id: int
    min_skill_level: str
    employees_required: int
    class Config: from_attributes = True

class MachineCreate(BaseModel):
    name: str
    machine_type: Optional[str] = None
    base_availability_pct: float = 100.0
    location_bay: Optional[str] = None
    status: str = "Operational"
    hourly_rate: Optional[float] = None
    skill_requirements: List[MachineSkillReqIn] = []

class MachineUpdate(BaseModel):
    name: Optional[str] = None
    machine_type: Optional[str] = None
    base_availability_pct: Optional[float] = None
    location_bay: Optional[str] = None
    status: Optional[str] = None
    hourly_rate: Optional[float] = None
    skill_requirements: Optional[List[MachineSkillReqIn]] = None

class MachineOut(BaseModel):
    id: int
    name: str
    machine_type: Optional[str]
    base_availability_pct: float
    location_bay: Optional[str]
    status: str
    hourly_rate: Optional[float]
    skill_requirements: List[MachineSkillReqOut] = []
    class Config: from_attributes = True
