# app/schemas/team.py - Pydantic schemas for /api/team endpoints
# Branch: v5-whatsapp
#
# FILE PURPOSE
# Pydantic v2 request/response models for the v6.3.3 + v6.3.5 Team & Roles UI:
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
# - pydantic v2: BaseModel, ConfigDict, field_validator
# - app.services.role_helpers: VALID_USER_ROLES (canonical role list)
# - re for E.164 phone format validation (same pattern as schemas/auth.py)
# - typing.Literal for the v6.3.5 channel + whatsapp_status enums
#
# v6.3.5 ADDITIONS (decision Q4: option a, back-compat extension)
# - InviteRequest.channel: Optional['whatsapp', 'desktop']
#       When None, the service infers from email_or_phone shape - this
#       preserves every v6.3.3 caller verbatim. When explicit, the service
#       enforces the shape matches (whatsapp -> phone, desktop -> email).
# - InviteRequest.consent_given: bool = False
#       Required True when channel='whatsapp'. The WhatsApp welcome message
#       handshake then asks the recipient to reply HAAN/YES; the inviter's
#       consent_given flag is ONLY about the invitation contract.
# - InviteRequest.name: Optional[str]
#       Stored on PhoneTenantMap.display_name (whatsapp channel only) so
#       inbound message logs and the team table can address invited members
#       by name without a User-table migration.
# - TeamMemberOut.email: Optional[str]
#       v6.3.3 returned the synthesised invite-XXX@invite.zetaops.com placeholder
#       to the UI; v6.3.5 strips it (returns None) so the UI can render the
#       "(unnamed)" / "(invited)" empty states without pattern-matching.
# - TeamMemberOut.whatsapp_status: Literal['active','invited','disconnected','none']
#       Sourced from PhoneTenantMap.is_active + consent_given. See
#       team_service._compute_whatsapp_status for the truth table.
# - TeamMemberOut.name: Optional[str]
#       Surfaced from PhoneTenantMap.display_name when present. v6.5+ adds
#       a User.full_name column to remove this indirection.
#
# DESIGN NOTES
# - email_or_phone is preserved as a single freeform field on InviteRequest
#   for back-compat. The handler inspects it: email shape -> User.email path,
#   E.164 -> phone path with synthesised placeholder email. v6.3.5 adds the
#   `channel` field as a HINT - the schema does not split into separate
#   email/phone_e164 fields until the v6.5+ migration sweep (Q4 decision).
# - role is validated against VALID_USER_ROLES (single source of truth in
#   role_helpers.py). Future role additions flow through automatically.

import re
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, field_validator

from app.services.role_helpers import VALID_USER_ROLES


# E.164 phone format - same regex as schemas/auth.py to keep contract
# parity between /auth/register and /api/team/invite.
_E164_PATTERN = re.compile(r"^\+[1-9]\d{1,14}$")
# Simple email shape check. Full RFC validation lives in EmailStr where used;
# here we only need a "looks like email vs looks like phone" discriminator
# for the freeform email_or_phone field.
_EMAIL_SHAPE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


# v6.3.5 channel + status enums. Kept here (not in a separate module) because
# they are exclusively used by the team-management surface and no other layer
# should be defining their own copies (Lesson 22 - one source of truth).
InviteChannel = Literal["whatsapp", "desktop"]
WhatsAppStatus = Literal["active", "invited", "disconnected", "none"]


class InviteRequest(BaseModel):
    """
    Body for POST /api/team/invite.

    `email_or_phone` accepts either an email address or an E.164 phone string.
    The handler decides which field of the new User row to populate. `role`
    must be one of role_helpers.VALID_USER_ROLES.

    v6.3.5 fields (all optional for back-compat with v6.3.3 callers):
      - channel: explicit 'whatsapp' / 'desktop' hint. None means infer
        from email_or_phone shape.
      - consent_given: required True when channel == 'whatsapp'. The
        service raises 400 otherwise.
      - name: optional display name. Stored on PhoneTenantMap.display_name
        for whatsapp invites; ignored on desktop invites until v6.5+.
    """

    email_or_phone: str
    role: str
    # v6.3.5 additions - all optional so v6.3.3 callers continue to work.
    channel: Optional[InviteChannel] = None
    consent_given: bool = False
    name: Optional[str] = None

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

    @field_validator("name")
    @classmethod
    def name_strip_or_none(cls, v: Optional[str]) -> Optional[str]:
        # Trim whitespace and treat empty string as None so the service layer
        # can do `if payload.name:` cleanly.
        if v is None:
            return None
        v = v.strip()
        return v if v else None


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

    v6.3.5 changes:
      - `email` is now Optional - returns None for users created via WhatsApp
        invite whose stored email is the synthesised invite-*@invite.zetaops.com
        placeholder. The frontend renders the empty state instead of leaking
        the placeholder.
      - `whatsapp_status` is computed from the user's PhoneTenantMap row in
        the service layer; values map to the Team & Roles status pill colours
        (active=green, invited=amber, disconnected=red, none=subtle grey).
      - `name` surfaces PhoneTenantMap.display_name when present so the UI
        can render "(unnamed)" italic for unnamed members without a separate
        round-trip.
    """

    id: int
    email: Optional[str] = None
    phone_e164: Optional[str] = None
    role: str
    is_active: bool
    is_top_tier: bool
    created_via: str
    # v6.3.5 additions.
    whatsapp_status: WhatsAppStatus = "none"
    name: Optional[str] = None

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
