"""
```python
"""
FILE PURPOSE
This file defines Pydantic v2 validation schemas for the Availability Override system in 
ZetaOps Copilot. Availability overrides allow tenants to record day-specific availability 
changes for employees (sick leave, vacation, half-days) or machines (scheduled maintenance, 
repairs). This functionality was introduced in v4.0 and sits in the data validation layer 
between the FastAPI availability router and the SQLAlchemy AvailabilityOverride ORM model.

WHAT THIS FILE DOES — step by step
1. Imports Pydantic BaseModel for request/response validation
2. Imports Optional and date/datetime types for flexible field definitions
3. Defines AvailabilityOverrideBase as shared field foundation for all schemas
4. Creates AvailabilityOverrideCreate for validating POST request payloads
5. Creates AvailabilityOverrideUpdate for validating PATCH request payloads with optional fields
6. Creates AvailabilityOverrideOut for serializing database responses to JSON
7. Configures Pydantic to work with SQLAlchemy ORM attributes via from_attributes=True

KEY FUNCTIONS / CLASSES / COMPONENTS

Name         : AvailabilityOverrideBase
Type         : Pydantic BaseModel class
Purpose      : Shared field schema containing all core availability override fields. Serves 
               as the foundation for both creation and response schemas, ensuring consistent 
               field definitions across endpoints.
Parameters   : employee_id (Optional[int]) - target employee ID, mutually exclusive with machine_id
               machine_id (Optional[int]) - target machine ID, mutually exclusive with employee_id  
               date_from (date) - start date of availability override period
               date_to (date) - end date of override period, equals date_from for single-day overrides
               availability_pct (float) - percentage availability (0=unavailable, 50=half-day, 100=full)
               reason (Optional[str]) - human-readable explanation for the override
Returns      : Base schema class for inheritance by other availability schemas
Calls        : No external calls, pure Pydantic validation
DB/API       : No direct database or API interactions
Side effects : Validates that either employee_id OR machine_id is provided, not both

Name         : AvailabilityOverrideCreate
Type         : Pydantic BaseModel class  
Purpose      : Request validation schema for POST /api/availability/ endpoint. Inherits all 
               fields from AvailabilityOverrideBase without modifications, ensuring new override 
               records contain all required information.
Parameters   : Inherits all parameters from AvailabilityOverrideBase
Returns      : Validated create payload ready for database insertion
Calls        : Inherits from AvailabilityOverrideBase
DB/API       : No direct interactions, used by router for DB insertion
Side effects : Validates business rules before database write operations

Name         : AvailabilityOverrideUpdate
Type         : Pydantic BaseModel class
Purpose      : Request validation schema for PATCH /api/availability/{id} endpoint. All fields 
               are optional to support partial updates, allowing clients to modify only specific 
               override attributes without sending the full record.
Parameters   : date_from (Optional[date]) - new start date if being updated
               date_to (Optional[date]) - new end date if being updated  
               availability_pct (Optional[float]) - new availability percentage if being updated
               reason (Optional[str]) - new reason text if being updated
Returns      : Validated partial update payload with only modified fields
Calls        : No external calls, pure Pydantic validation
DB/API       : No direct interactions, used by router for selective DB updates
Side effects : Validates only the fields being updated, leaves others unchanged

Name         : AvailabilityOverrideOut
Type         : Pydantic BaseModel class
Purpose      : Response serialization schema for all availability override endpoints (GET, POST, 
               PATCH). Extends AvailabilityOverrideBase with database-generated fields and 
               configures Pydantic to convert SQLAlchemy ORM objects to JSON responses.
Parameters   : Inherits all parameters from AvailabilityOverrideBase plus:
               id (int) - database primary key assigned by PostgreSQL
               created_at (datetime) - timestamp when override record was first created
Returns      : JSON-serializable representation of complete override record
Calls        : Inherits from AvailabilityOverrideBase, uses Pydantic model_config
DB/API       : Converts SQLAlchemy AvailabilityOverride ORM objects to JSON
Side effects : Serializes database objects for HTTP response transmission

WHO CALLS THIS FILE
- backend/app/routers/availability_router.py imports these schemas for endpoint validation
- backend/app/services/availability_engine.py may reference these types for service logic
- backend/app/crud/availability.py uses these schemas for type hints on CRUD operations
- Any future availability-related services that need standardized data shapes

IMPORTS EXPLAINED
- BaseModel from pydantic: Core class for creating data validation schemas with automatic JSON serialization
- Optional from typing: Allows fields to be None, supporting partial updates and optional attributes  
- date from datetime: Represents calendar dates for override start/end periods without time components
- datetime from datetime: Represents full timestamps with date and time for created_at tracking

INTERN NOTES
- Easiest thing to break: Forgetting that either employee_id OR machine_id must be set, but not both - the router validates this business rule
- Non-obvious design decision: AvailabilityOverrideCreate inherits everything without changes instead of duplicating fields, ensuring schema consistency
- Most common mistake: Setting availability_pct above 100 or below 0, or making date_to earlier than date_from - add validation for these ranges
- Design principle #2: These schemas work with tenant-scoped data but don't enforce tenant_id directly - that's handled at the ORM/router level
- What to check if behaving unexpectedly: Verify model_config from_attributes=True is present on AvailabilityOverrideOut, required for SQLAlchemy conversion
- Not v5-whatsapp specific: This is core v4 functionality used by both web interface and any future WhatsApp availability commands
"""
```
"""

from pydantic import BaseModel
from typing import Optional
from datetime import date, datetime


class AvailabilityOverrideBase(BaseModel):
    """Shared fields used by Create and Out schemas."""
    employee_id: Optional[int] = None    # Set this OR machine_id, not both
    machine_id: Optional[int] = None
    date_from: date
    date_to: date                        # For a single-day override: date_from == date_to
    availability_pct: float = 0.0        # 0 = fully unavailable; 50 = half-day
    reason: Optional[str] = None


class AvailabilityOverrideCreate(AvailabilityOverrideBase):
    """
    Request body for POST /api/availability/.

    Input  : employee_id or machine_id, date range, availability percentage, optional reason.
    Output : Validated payload used by the router to insert a new override row.
    """
    pass


class AvailabilityOverrideUpdate(BaseModel):
    """
    Request body for PATCH /api/availability/{id}.
    All fields are optional for partial updates.

    Input  : Any subset of override fields to modify.
    Output : Validated payload used by the router to apply selective updates.
    """
    date_from: Optional[date] = None
    date_to: Optional[date] = None
    availability_pct: Optional[float] = None
    reason: Optional[str] = None


class AvailabilityOverrideOut(AvailabilityOverrideBase):
    """
    Response schema for all Availability Override endpoints.

    Input  : SQLAlchemy AvailabilityOverride ORM object.
    Output : Full override record including id and created_at timestamp.
    """
    id: int
    created_at: datetime

    model_config = {"from_attributes": True}
