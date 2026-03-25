"""app/schemas/auth.py — v4.0.1
Added: industry_type to RegisterRequest
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
    id: int
    email: str
    role: str
    tenant_id: int
    is_active: bool
    model_config = {"from_attributes": True}


class MessageResponse(BaseModel):
    message: str
