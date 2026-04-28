# app/schemas/auth.py - Pydantic schemas for auth endpoints
# Branch: v5-whatsapp
#
# FILE PURPOSE
# Pydantic v2 request/response models for the /auth/* endpoints.
# v6.3.2 extends RegisterRequest with team_size, phone_e164, and conditional
# email/password requirements that drive the v6.4 entry-gate (whatsapp_first
# vs hybrid vs desktop_first signup flow). See SRS v6.4 Section 6.28 Feature 1.
#
# WHO CALLS THIS FILE
# - app/routers/auth.py - request bodies for /auth/register, /auth/login
# - app/services/auth_service.py - reads validated payload fields
#
# WHAT THIS FILE CALLS
# - pydantic v2: BaseModel, EmailStr, field_validator, model_validator
# - re for E.164 phone format validation

import re
from typing import Literal, Optional
from pydantic import BaseModel, EmailStr, field_validator, model_validator


# E.164 phone format: leading +, 1-9 first digit, then 1-14 more digits.
# Used by v6.4 signup to validate phone_e164 from the entry-gate flow.
_E164_PATTERN = re.compile(r"^\+[1-9]\d{1,14}$")


class RegisterRequest(BaseModel):
    # Existing v6.3.1-and-earlier fields. Email/password become conditional
    # in v6.3.2 — see model_validator below.
    email: Optional[EmailStr] = None
    password: Optional[str] = None
    company_name: str
    slug: str
    industry_type: Literal["printing", "manufacturing", "fabrication", "field_service"] = "printing"

    # v6.3.2 entry-gate fields (SRS v6.4 Section 6.28).
    # team_size drives Tenant.entry_mode and Tenant.size_segment via
    # auth_service.determine_entry_mode_and_segment(). Required — Option A
    # backward-compat decision (see v6.3.2 handoff). All five existing callers
    # were updated in the same change set.
    #
    # Mapping (team_size -> entry_mode / size_segment):
    #   '1-15'  -> whatsapp_first / small
    #   '16-50' -> hybrid          / medium
    #   '51+'   -> desktop_first   / large
    team_size: Literal["1-15", "16-50", "51+"]

    # WhatsApp number in E.164 format. Required when team_size != '51+';
    # optional for desktop_first signups (large factories that begin
    # exclusively on the web app).
    phone_e164: Optional[str] = None

    @field_validator("password")
    @classmethod
    def password_strength(cls, v: Optional[str]) -> Optional[str]:
        # Only check length when a password was provided; whatsapp_first
        # signups may legitimately omit the password (validated below in
        # the model_validator that knows team_size).
        if v is not None and len(v) < 8:
            raise ValueError("Password must be at least 8 characters")
        return v

    @field_validator("slug")
    @classmethod
    def slug_valid(cls, v: str) -> str:
        if not re.match(r"^[a-z0-9-]+$", v):
            raise ValueError("Slug must contain only lowercase letters, numbers, and hyphens")
        return v

    @field_validator("phone_e164")
    @classmethod
    def phone_e164_format(cls, v: Optional[str]) -> Optional[str]:
        # Empty string and None both mean "not provided" at this stage.
        # The model_validator below decides whether absence is acceptable
        # given the chosen team_size.
        if v is None or v == "":
            return None
        if not _E164_PATTERN.match(v):
            raise ValueError(
                "phone_e164 must be in E.164 format, e.g. +919876543210 "
                "(leading +, country code, 1-15 digits total)"
            )
        return v

    @model_validator(mode="after")
    def conditional_email_password_phone(self):
        # team_size drives which fields are required:
        #   '1-15'  (whatsapp_first): phone required, email/password optional
        #   '16-50' (hybrid):         phone required, email + password required
        #   '51+'   (desktop_first):  phone optional, email + password required
        #
        # Validation lives here, not in the service layer (per v6.3.2 prompt).
        # Service layer trusts that any RegisterRequest it receives is already
        # consistent with the team_size contract.
        if self.team_size in ("1-15", "16-50") and not self.phone_e164:
            raise ValueError(
                "phone_e164 is required for team sizes 1-15 and 16-50 "
                "(WhatsApp-first or hybrid signup)."
            )

        if self.team_size in ("16-50", "51+"):
            if not self.email:
                raise ValueError(
                    "email is required for team sizes 16-50 and 51+."
                )
            if not self.password:
                raise ValueError(
                    "password is required for team sizes 16-50 and 51+."
                )

        return self


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    # v6.3.2: post-signup routing hint. Frontend reads this to decide whether
    # to land the new tenant on /dashboard (desktop_first) or /connect-whatsapp
    # (whatsapp_first or hybrid). None for /login and /refresh — those flows
    # do not change the user's destination. Existing clients that ignore the
    # field continue to work unchanged.
    next_step: Optional[str] = None


class UserResponse(BaseModel):
    id: int
    email: str
    role: str
    tenant_id: int
    is_active: bool
    industry_type: str | None = None  # BUG-5: populated from Tenant row by /auth/me
    model_config = {"from_attributes": True}


class MessageResponse(BaseModel):
    message: str
