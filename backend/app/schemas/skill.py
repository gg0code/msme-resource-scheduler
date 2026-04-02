"""
FILE PURPOSE:
This file defines Pydantic v2 schemas for the Skills API endpoints in the ZetaOps Copilot workforce scheduling system. It exists to validate HTTP request bodies and serialize response payloads for skill management operations, keeping data validation logic separate from the SQLAlchemy ORM models. Introduced in early v4 development on the v4-dev branch, this file sits in the validation layer between the FastAPI routers and the database models, ensuring type safety and consistent data shapes across the Skills API.

WHAT THIS FILE DOES — step by step:
1. Imports Pydantic BaseModel, Optional typing, and datetime for schema definitions
2. Defines SkillBase as a shared foundation containing common skill fields (name, category, premium flags, description)
3. Creates SkillCreate schema that inherits from SkillBase for validating POST request bodies when creating new skills
4. Defines SkillUpdate schema with all optional fields for PATCH operations, enabling partial updates to existing skills
5. Establishes SkillOut response schema that extends SkillBase with database-generated fields (id, timestamps, is_active)
6. Configures Pydantic model settings to enable automatic conversion from SQLAlchemy ORM objects to JSON responses

KEY FUNCTIONS / CLASSES / COMPONENTS:

Name         : SkillBase
Type         : Pydantic BaseModel class
Purpose      : Serves as the foundation schema containing shared fields used by both input and output schemas. Defines the core skill attributes that are common across create and response operations. Acts as a DRY (Don't Repeat Yourself) base to avoid field duplication between schemas.
Parameters   : name (str) - human-readable skill name, category (str) - classification like "generic" or "premium", is_premium (bool) - whether skill requires premium plan access, is_generic_role (bool) - whether this represents a generic role vs specific skill, description (Optional[str]) - optional detailed description
Returns      : N/A (base class)
Calls        : None
DB/API       : None
Side effects : None

Name         : SkillCreate
Type         : Pydantic BaseModel class
Purpose      : Validates incoming JSON data when creating new skills via POST /api/skills/. Inherits all validation rules from SkillBase without adding additional fields. Used by FastAPI to automatically parse and validate request bodies before they reach the router handler function.
Parameters   : Inherits all SkillBase parameters: name, category, is_premium, is_generic_role, description
Returns      : Validated skill creation data as Pydantic model instance
Calls        : None directly (used by FastAPI validation system)
DB/API       : None
Side effects : Raises Pydantic ValidationError if incoming JSON doesn't match schema requirements

Name         : SkillUpdate
Type         : Pydantic BaseModel class
Purpose      : Validates partial update requests for PATCH /api/skills/{id} operations. All fields are optional to support selective updates where only provided fields are modified. Includes is_active field for soft deletion operations that isn't present in create operations.
Parameters   : name (Optional[str]) - updated skill name, category (Optional[str]) - updated category, is_premium (Optional[bool]) - updated premium status, is_generic_role (Optional[bool]) - updated generic role flag, description (Optional[str]) - updated description, is_active (Optional[bool]) - soft deletion flag
Returns      : Validated partial update data as Pydantic model instance
Calls        : None directly (used by FastAPI validation system)
DB/API       : None
Side effects : Raises Pydantic ValidationError if provided fields don't match expected types

Name         : SkillOut
Type         : Pydantic BaseModel class
Purpose      : Serializes database skill records into JSON responses for all skill API endpoints. Inherits shared fields from SkillBase and adds database-generated metadata like id and timestamps. Configured with from_attributes=True to automatically convert SQLAlchemy ORM objects into JSON without manual field mapping.
Parameters   : Inherits SkillBase fields plus id (int) - database primary key, is_active (bool) - soft deletion status, created_at (datetime) - record creation timestamp, updated_at (datetime) - last modification timestamp
Returns      : JSON-serializable skill data for HTTP responses
Calls        : None directly (used by FastAPI response serialization)
DB/API       : None
Side effects : None (read-only serialization)

WHO CALLS THIS FILE:
- backend/app/routers/skills_router.py imports these schemas for endpoint request/response validation
- backend/app/crud/skill.py may reference these schemas for type hints in CRUD operations
- Any FastAPI endpoint that handles skill-related operations will use these schemas for automatic validation

IMPORTS EXPLAINED:
- BaseModel from pydantic: Core Pydantic class that provides data validation, serialization, and documentation features for API schemas
- Optional from typing: Enables fields that can be None, crucial for partial updates and optional description fields
- datetime: Required for typed timestamp fields (created_at, updated_at) that track record lifecycle in database responses

INTERN NOTES:
- Easiest thing to break: Changing field types without updating the corresponding SQLAlchemy model will cause runtime errors when from_attributes tries to convert ORM objects
- Non-obvious design decision: SkillUpdate includes is_active field for soft deletion but SkillCreate doesn't, because new records are always active by default
- Most common mistake: Forgetting to make fields Optional in SkillUpdate schema, which would require all fields in PATCH requests instead of allowing partial updates
- Design principle: Implements principle #2 (tenant scoping) indirectly by providing schemas that routers use with tenant-filtered database operations
- What to check if behaving unexpectedly: Verify the SQLAlchemy Skill model in backend/app/models/ has matching field names and types, and check that from_attributes=True is present in SkillOut
- v5-whatsapp consideration: This file is pure v4 functionality, but if v5 adds WhatsApp skill matching features, new optional fields may be added to support conversational skill queries
"""

from pydantic import BaseModel
from typing import Optional
from datetime import datetime


class SkillBase(BaseModel):
    """Shared fields used by both Create and Out schemas."""
    name: str
    category: str           # "generic" | "premium"
    is_premium: bool = False
    is_generic_role: bool = False
    description: Optional[str] = None


class SkillCreate(SkillBase):
    """
    Request body for POST /api/skills/.

    Input  : name, category, is_premium (optional), description (optional).
    Output : Used by the router to validate incoming JSON before DB insert.
    """
    pass


class SkillUpdate(BaseModel):
    """
    Request body for PATCH /api/skills/{id}.
    All fields are optional — only provided fields are updated (partial update).

    Input  : Any subset of skill fields.
    Output : Used by the router to apply selective updates to the ORM object.
    """
    name: Optional[str] = None
    category: Optional[str] = None
    is_premium: Optional[bool] = None
    is_generic_role: Optional[bool] = None
    description: Optional[str] = None
    is_active: Optional[bool] = None


class SkillOut(SkillBase):
    """
    Response schema returned by all Skill endpoints.

    Input  : SQLAlchemy Skill ORM object (from_attributes=True enables ORM mode).
    Output : Serialised JSON with all skill fields including id and timestamps.
    """
    id: int
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
