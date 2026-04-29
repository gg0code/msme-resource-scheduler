# app/schemas/team.py - Pydantic schemas for /api/team endpoints
# Branch: v5-whatsapp
#
# FILE PURPOSE
# Pydantic v2 request/response models for the v6.3.3 Team & Roles UI:
#   - InviteRequest    : POST  /api/team/invite body
#   - RoleChangeRequest: PATCH /api/team/{user_id}/role body
#   - TeamMemberOut    : GET   /api/team list element + invite/PATCH response
#   - InviteResponse   : POST  /api/team/invite response (member + temp_password)
#
# WHO CALLS THIS FILE
# - app/routers/team_management.py (request bodies, response models)
# - app/services/team_service.py    (reads validated payload fields)
#
# WHAT THIS FILE CALLS
# - pydantic v2: BaseModel, ConfigDict, EmailStr, field_validator
# - app.services.role_helpers: VALID_USER_ROLES (canonical role list)
# - re for E.164 phone format validation (same pattern as schemas/auth.py)
#
# DESIGN NOTES
# - email_or_phone is a single freeform field on InviteRequest. The handler
#   inspects it: if it parses as an email, the new User row gets that email
#   and a synthesized "no-phone" placeholder; if it parses as E.164, the
#   row gets the phone and a synthesized "+slug+nomail@whatsapp.local"
#   email (same pattern as auth_service.register_tenant_and_user for
#   whatsapp_first signups). One contract for both invite paths means the
#   frontend can keep a single input field, not two.
# - role is validated against VALID_USER_ROLES (single source of truth in
#   role_helpers.py). Future role additions flow through automatically.

import re
from typing import Optional
from pydantic import BaseModel, ConfigDict, field_validator

from app.services.role_helpers import VALID_USER_ROLES


# E.164 phone format - same regex as schemas/auth.py to keep contract
# parity between /auth/register and /api/team/invite.
_E164_PATTERN = re.compile(r"^\+[1-9]\d{1,14}$")
# Simple email shape check. Full RFC validation lives in EmailStr where used;
# here we only need a "looks like email vs looks like phone" discriminator
# for the freeform email_or_phone field.
_EMAIL_SHAPE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class InviteRequest(BaseModel):
    """
    Body for POST /api/team/invite.

    `email_or_phone` accepts either an email address or an E.164 phone string.
    The handler decides which field of the new User row to populate. `role`
    must be one of role_helpers.VALID_USER_ROLES.
    """

    email_or_phone: str
    role: str

    @field_validator("email_or_phone")
    @classmethod
    def email_or_phone_format(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("email_or_phone is required")
        # Accept either shape; the handler classifies it.
        if _EMAIL_SHAPE.match(v) or _E164_PATTERN.match(v):
            return v
        raise ValueError(
            "email_or_phone must be either an email address (a@b.c) or an "
            "E.164 phone number (+919876543210)"
        )

    @field_validator("role")
    @classmethod
    def role_in_valid_set(cls, v: str) -> str:
        if v not in VALID_USER_ROLES:
            raise ValueError(
                f"role must be one of {list(VALID_USER_ROLES)}, got {v!r}"
            )
        return v


class RoleChangeRequest(BaseModel):
    """Body for PATCH /api/team/{user_id}/role. Only the role field changes."""

    role: str

    @field_validator("role")
    @classmethod
    def role_in_valid_set(cls, v: str) -> str:
        if v not in VALID_USER_ROLES:
            raise ValueError(
                f"role must be one of {list(VALID_USER_ROLES)}, got {v!r}"
            )
        return v


class TeamMemberOut(BaseModel):
    """
    Single-user response shape for GET /api/team and the success body of
    invite / PATCH. Mirrors the columns the Team & Roles UI renders.
    """

    id: int
    email: str
    phone_e164: Optional[str] = None
    role: str
    is_active: bool
    is_top_tier: bool
    created_via: str

    model_config = ConfigDict(from_attributes=True)


class InviteResponse(BaseModel):
    """
    Response body for POST /api/team/invite.

    `temp_password` is the one-time generated password the inviter must
    deliver to the new user (out-of-band - email delivery lands in v6.3.4+).
    None when the invitee was created via WhatsApp-first invite (no
    password required, they will authenticate via WhatsApp identity).
    """

    member: TeamMemberOut
    temp_password: Optional[str] = None
