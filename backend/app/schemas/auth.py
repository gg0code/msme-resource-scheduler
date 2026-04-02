"""
```python
"""
FILE PURPOSE
This file defines Pydantic v2 request and response schemas for all authentication-related
API endpoints in the ZetaOps Copilot application. It was introduced in v4.0.1 to add
industry_type support to user registration, and sits in the data validation layer between
FastAPI route handlers and the business logic, ensuring all auth data is properly validated
before reaching the database or authentication services.

WHAT THIS FILE DOES — step by step
1. Defines VALID_INDUSTRY_TYPES constant containing the five supported manufacturing industries
2. Creates RegisterRequest schema with validation for email, password strength, company slug format, and industry type
3. Creates LoginRequest schema for simple email/password authentication
4. Creates TokenResponse schema for JWT token API responses
5. Creates UserResponse schema for returning user data with tenant industry information
6. Creates MessageResponse schema for generic success/error messages from auth endpoints
7. Implements custom field validators for password complexity, slug format compliance, and industry type restrictions

KEY FUNCTIONS / CLASSES / COMPONENTS

Name         : VALID_INDUSTRY_TYPES
Type         : constant set
Purpose      : Defines the exhaustive list of manufacturing industry types that tenants can
               select during registration. This directly maps to the industry-specific features
               and UI customizations throughout the application.
Parameters   : N/A (constant)
Returns      : N/A (constant)
Calls        : N/A
DB/API       : N/A
Side effects : None

Name         : RegisterRequest
Type         : Pydantic BaseModel class
Purpose      : Validates all data required for new tenant registration including user account
               creation and tenant setup. Enforces business rules for password security, company
               slug uniqueness format, and industry type selection. This schema ensures data
               integrity before tenant and user records are created in the database.
Parameters   : email (EmailStr) - user's email address, must be valid email format
               password (str) - user's chosen password, validated for minimum complexity
               company_name (str) - display name for the tenant organization
               slug (str) - URL-safe tenant identifier, validated for format compliance
               industry_type (str) - manufacturing industry, defaults to "printing"
Returns      : Validated RegisterRequest instance ready for tenant creation service
Calls        : Built-in re module for slug pattern validation
DB/API       : None directly (used by registration endpoints that create DB records)
Side effects : Raises ValueError exceptions for invalid field values during validation

Name         : RegisterRequest.password_strength
Type         : Pydantic field validator classmethod
Purpose      : Ensures password meets minimum security requirements before user account creation.
               Currently enforces 8+ character minimum but could be extended for complexity rules.
Parameters   : cls (class reference) - Pydantic validator pattern requirement
               v (str) - password string to validate
Returns      : Original password string if valid
Calls        : Python built-in len() function
DB/API       : None
Side effects : Raises ValueError if password too short, blocking registration

Name         : RegisterRequest.slug_valid
Type         : Pydantic field validator classmethod
Purpose      : Validates tenant slug format to ensure URL safety and consistency across the
               application. Slug becomes part of tenant identification and potentially URL routing.
Parameters   : cls (class reference) - Pydantic validator pattern requirement
               v (str) - slug string to validate against regex pattern
Returns      : Original slug string if format is valid
Calls        : re.match() with lowercase alphanumeric and hyphen pattern
DB/API       : None
Side effects : Raises ValueError if slug contains invalid characters, blocking registration

Name         : RegisterRequest.industry_valid
Type         : Pydantic field validator classmethod
Purpose      : Ensures selected industry type is supported by the application's feature set and
               UI customizations. Invalid industry types would cause undefined behavior in
               industry-specific features throughout the system.
Parameters   : cls (class reference) - Pydantic validator pattern requirement
               v (str) - industry_type string to validate against allowed values
Returns      : Original industry_type string if valid
Calls        : Set membership check against VALID_INDUSTRY_TYPES constant
DB/API       : None
Side effects : Raises ValueError with helpful message listing valid options if invalid industry selected

Name         : LoginRequest
Type         : Pydantic BaseModel class
Purpose      : Validates user credentials for authentication endpoints. Simple schema that ensures
               email format validity and password presence before attempting database user lookup
               and password verification.
Parameters   : email (EmailStr) - user's email address for account lookup
               password (str) - user's password for verification
Returns      : Validated LoginRequest instance ready for authentication service
Calls        : EmailStr validation from Pydantic
DB/API       : None directly (used by login endpoints that query user table)
Side effects : None

Name         : TokenResponse
Type         : Pydantic BaseModel class
Purpose      : Standardizes JWT token response format from authentication endpoints. Ensures
               consistent token delivery to frontend clients and provides token_type field for
               future authentication method extensibility.
Parameters   : access_token (str) - JWT access token string for API authentication
               token_type (str) - authentication scheme, defaults to "bearer"
Returns      : TokenResponse instance for JSON serialization in API responses
Calls        : None
DB/API       : None
Side effects : None

Name         : UserResponse
Type         : Pydantic BaseModel class
Purpose      : Serializes user data for API responses while excluding sensitive information like
               password hashes. Includes tenant context and industry information needed by frontend
               for role-based access control and industry-specific UI rendering.
Parameters   : id (int) - user's unique identifier
               email (str) - user's email address
               role (str) - user's role within tenant (affects permissions)
               tenant_id (int) - tenant foreign key for multi-tenancy
               is_active (bool) - user account status flag
               industry_type (str) - tenant's industry, defaults to "printing"
Returns      : UserResponse instance for JSON serialization in API responses
Calls        : SQLAlchemy model attribute mapping via from_attributes config
DB/API       : None directly (populated from User model queries)
Side effects : None

Name         : MessageResponse
Type         : Pydantic BaseModel class
Purpose      : Provides consistent schema for simple success or error messages from authentication
               endpoints. Used for operations like password reset, email verification, or logout
               confirmations where only a text message needs to be returned.
Parameters   : message (str) - human-readable message text for frontend display
Returns      : MessageResponse instance for JSON serialization in API responses
Calls        : None
DB/API       : None
Side effects : None

WHO CALLS THIS FILE
- backend/app/routers/auth.py imports all schemas for request/response validation on authentication endpoints
- backend/app/services/auth_service.py may import these schemas for type hints in authentication business logic
- Any FastAPI endpoint that handles user registration, login, or user data responses uses these schemas

IMPORTS EXPLAINED
- re: Regular expression module needed for slug format validation using pattern matching
- typing.Optional: Type hint for optional fields, though not currently used in this file
- pydantic.BaseModel: Base class for all request/response schemas providing validation and serialization
- pydantic.EmailStr: Specialized string type that validates email address format automatically
- pydantic.field_validator: Decorator for creating custom field validation logic on model fields

INTERN NOTES
- Easiest thing to break: Adding new industry types to VALID_INDUSTRY_TYPES without updating corresponding UI and feature logic throughout the application
- Non-obvious design decision: Slug validation uses strict alphanumeric+hyphen pattern because slugs may be used in URLs and must be universally safe across web contexts
"""

import re
from typing import Optional
from pydantic import BaseModel, EmailStr, field_validator

VALID_INDUSTRY_TYPES = {
    "printing", "manufacturing", "fabrication", "chemical", "field_service"
}

class RegisterRequest(BaseModel):
    email: EmailStr
    password: str
    company_name: str
    slug: str
    industry_type: str = "printing"

    @field_validator("password")
    @classmethod
    def password_strength(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters")
        return v

    @field_validator("slug")
    @classmethod
    def slug_valid(cls, v: str) -> str:
        if not re.match(r"^[a-z0-9-]+$", v):
            raise ValueError("Slug must contain only lowercase letters, numbers, and hyphens")
        return v

    @field_validator("industry_type")
    @classmethod
    def industry_valid(cls, v: str) -> str:
        if v not in VALID_INDUSTRY_TYPES:
            raise ValueError(f"industry_type must be one of: {', '.join(VALID_INDUSTRY_TYPES)}")
        return v


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserResponse(BaseModel):
    id:            int
    email:         str
    role:          str
    tenant_id:     int
    is_active:     bool
    industry_type: str = "printing"   # v4.0.2 — from tenant
    model_config = {"from_attributes": True}


class MessageResponse(BaseModel):
    message: str
