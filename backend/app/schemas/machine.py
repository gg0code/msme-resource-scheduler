"""
```python
"""
FILE PURPOSE
This file defines Pydantic v2 schemas for Machine API requests and responses in the
ZetaOps Copilot workforce scheduling system. It was introduced in the early v4.x
architecture and sits in the API layer, providing type validation and serialization
for all machine-related endpoints. These schemas handle machine equipment data including
operational status, availability percentages, hourly rates for cost calculations,
and skill requirements that determine which employees can operate each machine.

WHAT THIS FILE DOES — step by step
1. Imports Pydantic BaseModel and typing utilities for schema definition
2. Defines MachineSkillReqIn for validating incoming skill requirement data
3. Defines MachineSkillReqOut for serializing skill requirements in API responses
4. Defines MachineCreate for validating new machine creation requests
5. Defines MachineUpdate for validating partial machine update requests
6. Defines MachineOut for serializing complete machine data in API responses
7. Configures Pydantic to work with SQLAlchemy ORM attributes via from_attributes

KEY FUNCTIONS / CLASSES / COMPONENTS

Name         : MachineSkillReqIn
Type         : Pydantic schema class
Purpose      : Validates incoming skill requirement data when creating or updating
               machines. Defines which skills employees need to operate a machine,
               the minimum proficiency level required, and how many employees are needed.
Parameters   : skill_id (int) - foreign key to Skill model, min_skill_level (str) - 
               proficiency level defaulting to "Generic", employees_required (int) - 
               number of employees needed defaulting to 1
Returns      : Validated skill requirement data for machine operations
Calls        : No other files, pure Pydantic validation
DB/API       : No direct DB/API calls, used by router endpoints
Side effects : None, validation only

Name         : MachineSkillReqOut
Type         : Pydantic schema class
Purpose      : Serializes skill requirement data for API responses. Includes the
               database ID field and converts SQLAlchemy ORM objects to JSON-serializable
               format for frontend consumption.
Parameters   : id (int) - database primary key, skill_id (int) - foreign key reference,
               min_skill_level (str) - required proficiency, employees_required (int) - 
               headcount needed
Returns      : JSON-serializable skill requirement data
Calls        : No other files, pure Pydantic serialization
DB/API       : No direct calls, converts ORM data via from_attributes
Side effects : None, serialization only

Name         : MachineCreate
Type         : Pydantic schema class  
Purpose      : Validates complete machine creation requests from frontend. Handles all
               required and optional fields for new machine equipment including operational
               parameters, location data, cost information, and associated skill requirements.
Parameters   : name (str) - machine display name, machine_type (Optional[str]) - equipment
               category, base_availability_pct (float) - operational capacity defaulting to 100%,
               location_bay (Optional[str]) - physical location, status (str) - operational
               status defaulting to "Operational", hourly_rate (Optional[float]) - cost per
               hour for scheduling calculations, skill_requirements (List[MachineSkillReqIn]) - 
               required operator skills defaulting to empty list
Returns      : Validated machine creation data ready for database insertion
Calls        : References MachineSkillReqIn for nested validation
DB/API       : No direct calls, used by machine creation endpoints
Side effects : None, validation only

Name         : MachineUpdate  
Type         : Pydantic schema class
Purpose      : Validates partial machine update requests where all fields are optional.
               Enables PATCH-style updates where clients can modify individual machine
               properties without sending complete object data.
Parameters   : All parameters optional versions of MachineCreate fields - name, machine_type,
               base_availability_pct, location_bay, status, hourly_rate, skill_requirements
Returns      : Validated partial update data for database modification
Calls        : References MachineSkillReqIn for skill requirement validation when provided
DB/API       : No direct calls, used by machine update endpoints  
Side effects : None, validation only

Name         : MachineOut
Type         : Pydantic schema class
Purpose      : Serializes complete machine data for API responses including database ID
               and all associated skill requirements. Converts SQLAlchemy ORM Machine
               objects into JSON format for frontend consumption and external API responses.
Parameters   : id (int) - database primary key, plus all fields from MachineCreate,
               skill_requirements (List[MachineSkillReqOut]) - associated skill data
Returns      : Complete JSON-serializable machine data with relationships
Calls        : References MachineSkillReqOut for nested skill requirement serialization
DB/API       : No direct calls, converts ORM data via from_attributes configuration
Side effects : None, serialization only

WHO CALLS THIS FILE
- backend/app/routers/machine_router.py imports these schemas for endpoint validation
- backend/app/crud/machine.py may reference these types for type hints
- backend/app/services/availability_engine.py imports for machine availability calculations
- backend/app/scheduler/engine.py uses machine data structured by these schemas

IMPORTS EXPLAINED
- BaseModel from pydantic: Core Pydantic class providing validation and serialization
- Optional from typing: Enables optional field definitions for partial updates and nullable database fields  
- List from typing: Defines list type hints for skill requirements collections

INTERN NOTES
- Easiest thing to break: Removing from_attributes config will break ORM serialization causing 500 errors on all machine GET endpoints
- Non-obvious design decision: base_availability_pct defaults to 100.0 because most machines are fully operational when first added, and the scheduler needs this for capacity calculations
- Most common mistake: Forgetting to make fields Optional in MachineUpdate schema, which breaks PATCH endpoints that should allow partial updates
- Design principle #2: This file implements tenant scoping indirectly by validating data that will be filtered by tenant_id in the database layer
- What to check if behaving unexpectedly: Verify skill_requirements validation isn't rejecting valid skill_id foreign keys, and check that hourly_rate accepts null values for cost-optional workflows
- Not applicable to v5-whatsapp: This file exists in both branches with identical structure since machine management is core v4 functionality
"""
```
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
    model_config = {"from_attributes": True}

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
    model_config = {"from_attributes": True}
