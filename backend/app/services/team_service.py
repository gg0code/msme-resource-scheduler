# app/services/team_service.py - Team & Roles service layer
# Branch: v5-whatsapp
#
# FILE PURPOSE
# Business logic for the v6.3.3 /api/team endpoints. Owns the User
# create / role-change / soft-delete operations plus the audit-event
# writes to the events table (migration 028). Routers stay thin -
# permission checks live in dependencies.py, request validation in
# schemas/team.py, business logic here.
#
# WHO CALLS THIS FILE
# - app/routers/team_management.py - all four endpoints
# - tests/test_team_management.py  - service-direct tests for the same paths
#
# WHAT THIS FILE CALLS
# - app/core/security.hash_password   (invite path)
# - app/models/auth.User, TOP_TIER_ROLES (DB ORM + canonical role set)
# - app/models/event.Event           (audit row writer)
# - secrets.token_urlsafe            (temp password generator)
#
# DESIGN NOTES
# - Soft-delete: delete_member() sets is_active=False, never DELETEs the row.
#   The events table joins back to the User on actor_user_id; a hard delete
#   would NULL that FK (per the SET NULL we configured) but also break the
#   "list all users in tenant" view. Soft delete preserves both.
# - Last-owner protection lives in is_last_owner(), called from BOTH
#   change_member_role() (when demoting) and delete_member(). Single
#   helper, single source of truth, single test coverage point.
# - Audit events are emitted in the same transaction as the user mutation.
#   Caller commits. If the commit fails, both the user change and the
#   audit row roll back together - we never end up with a logged event
#   for an action that did not happen.
# - All queries scope by tenant_id. Cross-tenant lookups raise 404 from
#   the router so an attacker cannot probe other tenants' user IDs.

import secrets
from typing import Optional

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.security import hash_password
from app.models.auth import TOP_TIER_ROLES, User
from app.models.event import Event
from app.schemas.team import InviteRequest, RoleChangeRequest


# Roles whose creation requires owner-level authority (handler-level guard
# layered ON TOP of require_top_tier). A factory_manager can invite a
# manager but cannot invite another factory_manager - that takes an owner
# or proprietor. Single-source set so PATCH and POST share the rule.
TOP_TIER_GRANT_ROLES: frozenset = frozenset(("owner", "proprietor"))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def is_last_owner(tenant_id: int, user_id: int, db: Session) -> bool:
    """
    True if removing or demoting `user_id` would leave the tenant with zero
    active top-tier (owner-equivalent) users.

    Called by: change_member_role() (when new_role is NOT top-tier),
               delete_member().
    Calls into: SQLAlchemy SELECT COUNT(*) on users filtered by tenant
                + role IN TOP_TIER_ROLES + is_active.
    Side effects: none - pure read.

    The check counts ACTIVE top-tier users only; an inactive owner still
    in the table does not satisfy the "tenant has at least one owner"
    invariant, so they do not count toward avoiding lockout.
    """
    target = db.query(User).filter(
        User.id == user_id, User.tenant_id == tenant_id
    ).first()
    if target is None:
        return False
    if not target.is_top_tier or not target.is_active:
        # Removing a non-top-tier or already-inactive user can never
        # reduce the active top-tier count, so they cannot be "the last".
        return False

    active_top_tier_count = db.execute(
        select(func.count(User.id)).where(
            User.tenant_id == tenant_id,
            User.role.in_(TOP_TIER_ROLES),
            User.is_active == True,  # noqa: E712 (SQLAlchemy comparison idiom)
        )
    ).scalar_one()

    return active_top_tier_count <= 1


def _emit_event(
    db: Session,
    *,
    tenant_id: int,
    actor_user_id: int,
    event_type: str,
    entity_id: int,
    payload: dict,
) -> None:
    """
    Append a row to the events table. Caller owns the transaction commit.

    Called by: invite_member(), change_member_role(), delete_member().
    Calls into: db.add() - flushes on next query / commit.
    Side effects: stages an INSERT on events. Visible to the same session
                  immediately after flush; durable after commit.

    All team-management events share entity_type='user' and source='web'
    (the router serves only the desktop UI today; v6.3.5+ may add a
    'whatsapp' source for invite-via-WA flows).
    """
    db.add(Event(
        tenant_id=tenant_id,
        event_type=event_type,
        entity_type="user",
        entity_id=entity_id,
        actor_user_id=actor_user_id,
        source="web",
        payload=payload,
    ))


def _generate_temp_password() -> str:
    """
    Generate a cryptographically random temp password the inviter delivers
    out-of-band to the new user.

    16 url-safe base64 characters - approx 96 bits of entropy. The user
    is expected to change it on first login. We do not enforce that
    expectation in v6.3.3 - it lands when the password-reset flow ships
    in v6.3.4+.

    Called by: invite_member().
    Calls into: secrets.token_urlsafe (PEP 506 / Python stdlib).
    """
    return secrets.token_urlsafe(12)  # ~16 chars after base64


def _classify_email_or_phone(email_or_phone: str) -> tuple[Optional[str], Optional[str]]:
    """
    Split the InviteRequest.email_or_phone freeform field into (email, phone).

    Schema-level validation guarantees the value matches one of the two
    patterns; here we just route. Returns (email, None) for an email
    string and (None, phone) for an E.164 string.

    Called by: invite_member().
    Calls into: nothing - pure string check on '@'.
    """
    if "@" in email_or_phone:
        return (email_or_phone, None)
    return (None, email_or_phone)


# ---------------------------------------------------------------------------
# Service entry points
# ---------------------------------------------------------------------------

def list_team_members(tenant_id: int, db: Session) -> list[User]:
    """
    Return every active+inactive User in the tenant, ordered by id.

    Called by: routers/team_management.py:list_team
    Calls into: SQLAlchemy SELECT * FROM users WHERE tenant_id = :t.
    Side effects: none - pure read.
    """
    return db.query(User).filter(
        User.tenant_id == tenant_id,
    ).order_by(User.id).all()


def invite_member(
    tenant_id: int,
    actor_user_id: int,
    actor_role: str,
    payload: InviteRequest,
    db: Session,
) -> tuple[User, Optional[str]]:
    """
    Create a new User in the actor's tenant. Generate + return a temp
    password the inviter must deliver to the new user.

    Permission rules layered on top of require_top_tier:
      - require_top_tier (in router) gates entry.
      - This service additionally enforces: only owner/proprietor can
        invite into TOP_TIER_ROLES. factory_manager and co_owner can
        invite manager / scheduler / viewer but not into top-tier.

    Called by: routers/team_management.py:invite
    Calls into: hash_password, _emit_event, db.add/db.flush.
    Side effects: INSERT users + INSERT events. Caller commits.

    Returns: (new_user, temp_password). temp_password is None when the
             invitee was created via the phone path (whatsapp_first
             invite - no password, authenticates via WhatsApp).
    Raises:  HTTPException(400) on duplicate email / phone or rule violation.
    """
    # Handler-level guard: granting top-tier requires owner-level authority.
    if payload.role in TOP_TIER_ROLES and actor_role not in TOP_TIER_GRANT_ROLES:
        raise HTTPException(
            status_code=403,
            detail=(
                f"Role '{actor_role}' cannot invite into top-tier roles. "
                f"Only {sorted(TOP_TIER_GRANT_ROLES)} can grant top-tier."
            ),
        )

    email, phone = _classify_email_or_phone(payload.email_or_phone)

    # Cross-table uniqueness: email is globally unique in the schema.
    if email and db.query(User).filter(User.email == email).first():
        raise HTTPException(
            status_code=400, detail=f"Email {email} is already registered."
        )
    # Phone is also globally unique in PhoneTenantMap, but a phone-only
    # invite does not yet write to PhoneTenantMap (that happens on
    # whatsapp link). The User.phone_e164 column is non-unique, so a
    # collision check here is a courtesy only.
    if phone and db.query(User).filter(User.phone_e164 == phone).first():
        raise HTTPException(
            status_code=400, detail=f"Phone {phone} is already in use by another user."
        )

    # Phone-only invites synthesise a placeholder email so the
    # NOT NULL + UNIQUE constraints on User.email are satisfied until
    # the invitee adds a real email later. Unlike whatsapp_first signup
    # users (who never log in by password), team-management invitees
    # DO log in via /auth/login with this email + a temp password,
    # so the synthesised string MUST pass Pydantic's EmailStr validator.
    #
    # email-validator (which backs Pydantic EmailStr) rejects:
    #   - local parts starting with '+'        (e.g. '+invite-XXX@...')
    #   - reserved-name TLDs per RFC 6761       (.local, .invalid, .test,
    #                                             .example, .localhost)
    # We pick `invite-<8hex>@invite.zetaops.com` - real TLD, recognisable
    # subdomain prefix, no real mailbox required (no email is ever sent
    # to this address; it is purely a unique key in the users table).
    # auth_service still uses `@whatsapp.local` because those users never
    # touch the password-login validator.
    if email is None:
        email = f"invite-{secrets.token_hex(4)}@invite.zetaops.com"

    # Always generate a temp password the inviter delivers out-of-band -
    # for both email and phone invites. The phone-only case originally
    # stored an empty hash on the assumption the user would authenticate
    # via the WhatsApp HAAN flow, but that flow does not ship until
    # v6.3.5; without a password the invitee was unreachable. Issuing a
    # password gives them a working credential today; when HAAN lands
    # they gain WhatsApp as a second auth channel.
    temp_password = _generate_temp_password()
    hashed = hash_password(temp_password)

    new_user = User(
        tenant_id=tenant_id,
        email=email,
        hashed_password=hashed,
        role=payload.role,
        phone_e164=phone,
        created_via="web_invite",
    )
    db.add(new_user)
    db.flush()  # populate new_user.id for the event row

    _emit_event(
        db,
        tenant_id=tenant_id,
        actor_user_id=actor_user_id,
        event_type="user.invited",
        entity_id=new_user.id,
        payload={
            "user_id":  new_user.id,
            "email":    email,
            "phone":    phone,
            "role":     payload.role,
            "actor_id": actor_user_id,
        },
    )

    db.commit()
    db.refresh(new_user)
    return new_user, temp_password


def change_member_role(
    tenant_id: int,
    target_user_id: int,
    actor_user_id: int,
    actor_role: str,
    payload: RoleChangeRequest,
    db: Session,
) -> User:
    """
    Update target_user_id's role within the actor's tenant.

    Permission rules layered on top of require_top_tier:
      - Granting top-tier requires owner-level authority (same as invite).
      - Demoting OUT of top-tier triggers the last-owner check; if the
        target is the only active top-tier user, refuse with 400.

    Called by: routers/team_management.py:change_role
    Calls into: is_last_owner, _emit_event.
    Side effects: UPDATE users + INSERT events. Caller commits.

    Returns: the updated User. Raises 400/403/404 on rule violation /
             cross-tenant access / missing user.
    """
    target = db.query(User).filter(
        User.id == target_user_id, User.tenant_id == tenant_id
    ).first()
    if target is None:
        raise HTTPException(status_code=404, detail="User not found in this tenant")

    old_role = target.role
    if old_role == payload.role:
        # No-op. Avoid emitting a noise event for an unchanged role.
        return target

    # Granting top-tier requires owner-level authority.
    if payload.role in TOP_TIER_ROLES and actor_role not in TOP_TIER_GRANT_ROLES:
        raise HTTPException(
            status_code=403,
            detail=(
                f"Role '{actor_role}' cannot promote into top-tier roles. "
                f"Only {sorted(TOP_TIER_GRANT_ROLES)} can grant top-tier."
            ),
        )

    # Demotion out of top-tier: enforce last-owner protection.
    if (
        old_role in TOP_TIER_ROLES
        and payload.role not in TOP_TIER_ROLES
        and is_last_owner(tenant_id, target_user_id, db)
    ):
        raise HTTPException(
            status_code=400,
            detail="Cannot demote the last top-tier user. Promote another member first.",
        )

    target.role = payload.role
    db.flush()

    _emit_event(
        db,
        tenant_id=tenant_id,
        actor_user_id=actor_user_id,
        event_type="user.role_changed",
        entity_id=target_user_id,
        payload={
            "user_id":   target_user_id,
            "old_role":  old_role,
            "new_role":  payload.role,
            "actor_id":  actor_user_id,
        },
    )

    db.commit()
    db.refresh(target)
    return target


def delete_member(
    tenant_id: int,
    target_user_id: int,
    actor_user_id: int,
    db: Session,
) -> None:
    """
    Soft-delete target_user_id from the actor's tenant (sets is_active=False).

    Last-owner protection: if the target is the sole active top-tier user
    in the tenant, refuse with 400 - the inviter must promote someone
    else first or transfer ownership.

    Called by: routers/team_management.py:delete_member (require_role
               'proprietor', 'owner' gates entry).
    Calls into: is_last_owner, _emit_event.
    Side effects: UPDATE users.is_active = false + INSERT events.
                  Caller commits.

    Why soft-delete: hard delete would NULL actor_user_id on every event
    the user produced (per the FK SET NULL on events.actor_user_id) and
    drop them from the team list view. Soft delete keeps both intact and
    matches how login already gates on is_active.
    """
    target = db.query(User).filter(
        User.id == target_user_id, User.tenant_id == tenant_id
    ).first()
    if target is None:
        raise HTTPException(status_code=404, detail="User not found in this tenant")

    if not target.is_active:
        # Already deactivated - idempotent.
        return

    if is_last_owner(tenant_id, target_user_id, db):
        raise HTTPException(
            status_code=400,
            detail="Cannot remove the last owner. Transfer ownership first.",
        )

    target.is_active = False
    db.flush()

    _emit_event(
        db,
        tenant_id=tenant_id,
        actor_user_id=actor_user_id,
        event_type="user.deactivated",
        entity_id=target_user_id,
        payload={
            "user_id":  target_user_id,
            "old_role": target.role,
            "actor_id": actor_user_id,
        },
    )

    db.commit()
