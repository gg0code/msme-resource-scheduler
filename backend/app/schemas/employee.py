"""
schemas/employee.py
-------------------
Pydantic schemas for Employee API validation.
Includes hourly_rate and overtime_rate fields.
"""

from pydantic import BaseModel
from typing import Optional, List
from datetime import date


class EmployeeSkillIn(BaseModel):
    skill_id: int
    skill_level: str = "Generic"

class EmployeeSkillOut(BaseModel):
    id: int
    skill_id: int
    skill_level: str
    class Config: from_attributes = True

class EmployeeCreate(BaseModel):
    full_name: str
    department: Optional[str] = None
    employment_type: str = "Full-time"
    base_availability_pct: float = 100.0
    status: str = "Active"
    contact_number: Optional[str] = None
    join_date: Optional[date] = None
    hourly_rate: Optional[float] = None
    overtime_rate: Optional[float] = None
    skills: List[EmployeeSkillIn] = []

class EmployeeUpdate(BaseModel):
    full_name: Optional[str] = None
    department: Optional[str] = None
    employment_type: Optional[str] = None
    base_availability_pct: Optional[float] = None
    status: Optional[str] = None
    contact_number: Optional[str] = None
    join_date: Optional[date] = None
    hourly_rate: Optional[float] = None
    overtime_rate: Optional[float] = None
    skills: Optional[List[EmployeeSkillIn]] = None

class EmployeeOut(BaseModel):
    id: int
    full_name: str
    department: Optional[str]
    employment_type: str
    base_availability_pct: float
    status: str
    contact_number: Optional[str]
    join_date: Optional[date]
    hourly_rate: Optional[float]
    overtime_rate: Optional[float]
    skills: List[EmployeeSkillOut] = []
    class Config: from_attributes = True
