"""
FILE PURPOSE
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
This file defines Pydantic v2 schemas for validating Employee API requests and responses in the ZetaOps Copilot workforce scheduling system. It exists to provide type safety and data validation for all employee-related operations including creating, updating, and retrieving employee records with their skills and cost information. This file was part of the original v4.0 architecture and sits in the schema validation layer between the FastAPI routers and the SQLAlchemy ORM models, ensuring all employee data conforms to expected formats before database operations.

WHAT THIS FILE DOES — step by step
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
1. Imports Pydantic BaseModel, Optional/List types, and date for schema validation
2. Defines EmployeeSkillIn schema for validating skill assignments when creating/updating employees
3. Defines EmployeeSkillOut schema for returning skill data with database IDs in API responses
4. Defines EmployeeCreate schema for validating new employee creation requests with all required and optional fields
5. Defines EmployeeUpdate schema for validating partial employee updates using optional fields
6. Defines EmployeeOut schema for serializing complete employee data including skills for API responses

KEY FUNCTIONS / CLASSES / COMPONENTS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Name         : EmployeeSkillIn
Type         : Pydantic schema class
Purpose      : Validates skill assignment data when adding skills to employees during create/update operations. Ensures skill_id references a valid skill and skill_level has a default value.
Parameters   : skill_id (int) - foreign key reference to a Skill record; skill_level (str) - proficiency level defaulting to "Generic"
Returns      : Validated skill assignment data as a Pydantic model instance
Calls        : No other files - pure Pydantic validation
DB/API       : No direct database calls, but skill_id must reference existing Skill records
Side effects : None - validation only

Name         : EmployeeSkillOut
Type         : Pydantic schema class  
Purpose      : Serializes employee skill data for API responses, including the database-generated ID. Uses from_attributes config to automatically convert SQLAlchemy model instances to Pydantic models.
Parameters   : id (int) - database primary key; skill_id (int) - foreign key to Skill; skill_level (str) - proficiency level
Returns      : Serialized skill data for JSON responses
Calls        : No other files - pure Pydantic serialization
DB/API       : No direct calls, but receives data from SQLAlchemy ORM queries
Side effects : None - serialization only

Name         : EmployeeCreate
Type         : Pydantic schema class
Purpose      : Validates complete employee creation requests from API clients. Includes all employee fields with sensible defaults and embedded skills list. Used by employee creation endpoints to ensure data integrity.
Parameters   : full_name (str) - required employee name; department (Optional[str]) - organizational unit; employment_type (str) - defaults to "Full-time"; base_availability_pct (float) - capacity percentage defaulting to 100.0; status (str) - employment status defaulting to "Active"; contact_number (Optional[str]) - phone contact; join_date (Optional[date]) - employment start date; hourly_rate (Optional[float]) - cost per hour; overtime_rate (Optional[float]) - overtime cost multiplier; skills (List[EmployeeSkillIn]) - embedded skill assignments defaulting to empty list
Returns      : Validated employee creation data as Pydantic model
Calls        : References EmployeeSkillIn for skills validation
DB/API       : No direct calls - validation layer only
Side effects : None - validation only

Name         : EmployeeUpdate  
Type         : Pydantic schema class
Purpose      : Validates partial employee update requests where all fields are optional. Supports PATCH-style updates where clients only send changed fields. Null/None values indicate fields should remain unchanged.
Parameters   : All parameters are Optional versions of EmployeeCreate fields - full_name, department, employment_type, base_availability_pct, status, contact_number, join_date, hourly_rate, overtime_rate, skills
Returns      : Validated partial update data as Pydantic model
Calls        : References EmployeeSkillIn for skills validation when skills are provided
DB/API       : No direct calls - validation layer only  
Side effects : None - validation only

Name         : EmployeeOut
Type         : Pydantic schema class
Purpose      : Serializes complete employee data for API responses including all fields and embedded skills. Uses from_attributes to automatically convert SQLAlchemy Employee models with joined Skill relationships into JSON-serializable format.
Parameters   : id (int) - database primary key; full_name (str) - employee name; department (Optional[str]) - organizational unit; employment_type (str) - employment category; base_availability_pct (float) - capacity percentage; status (str) - current employment status; contact_number (Optional[str]) - phone contact; join_date (Optional[date]) - employment start date; hourly_rate (Optional[float]) - cost per hour; overtime_rate (Optional[float]) - overtime cost; skills (List[EmployeeSkillOut]) - associated skills with proficiency levels
Returns      : Complete serialized employee data for JSON API responses
Calls        : References EmployeeSkillOut for skills serialization
DB/API       : No direct calls - receives data from SQLAlchemy queries via from_attributes
Side effects : None - serialization only

WHO CALLS THIS FILE
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
- backend/app/routers/employee_router.py - imports all schemas for FastAPI endpoint validation and response serialization
- backend/app/crud/employee_crud.py - imports EmployeeCreate and EmployeeUpdate for database operation parameter validation
- backend/app/services/availability_engine.py - imports EmployeeOut for type hints when working with employee availability calculations
- backend/app/routers/scheduler_router.py - imports EmployeeOut for employee data in scheduling responses

IMPORTS EXPLAINED
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
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
    model_config = {"from_attributes": True}

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
    model_config = {"from_attributes": True}
