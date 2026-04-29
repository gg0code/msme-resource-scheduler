# app/services/team_service.py - Team & Roles service layer
# Branch: v5-whatsapp
#
# FILE PURPOSE
# Business logic for the v6.3.3 + v6.3.5 /api/team endpoints. Owns the User
# create / role-change / soft-delete operations plus the audit-event
# writes to the events table (migration 028). Routers stay thin -
# permission checks live in dependencies.py, request validation in
# schemas/team.py, business logic here.
#
# WHO CALLS THIS FILE
# - app/routers/team_management.py - all four endpoints
# - tests/test_team_management.py  - service-direct tests for the same paths
# - tests/test_team_invite_v6_3_5.py - v6.3.5 channel routing + status tests
#
# WHAT THIS FILE CALLS
# - app/core/security.hash_password   (invite path)
# - app/models/auth.User, TOP_TIER_ROLES (DB ORM + canonical role set)
# - app/models/event.Event           (audit row writer)
# - app/models/whatsapp.PhoneTenantMap (status enrichment + invite linking)
# - app/services/whatsapp_identity.link_phone_to_tenant (creates the
#       PhoneTenantMap row at WhatsApp-invite time so the recipient's HAAN
#       reply lands on an existing mapping)
# - app/services/team_invite_whatsapp.send_invite_welcome (dispatches the
#       consent-handshake message)
# - secrets.token_urlsafe            (temp password generator)
#
# DESIGN NOTES
# - Soft-delete: delete_member() sets is_active=False, never DELETEs the row.
# - Last-owner protection lives in is_last_owner(), called from BOTH
#   change_member_role() and delete_member().
# - Audit events are emitted in the same transaction as the user mutation.
# - All queries scope by tenant_id.
#
# v6.3.5 ADDITIONS
# - _is_synthesised_email: detects placeholder emails so they can be
#   stripped from API responses (returns None in TeamMemberOut.email).
# - _compute_whatsapp_status: maps PhoneTenantMap state to the four-value
#   status pill enum.
# - list_team_members_with_status: SINGLE-SELECT enriched listing for the
#   v6.3.5 Team & Roles UI (N+1-free per CLAUDE.md rule).
# - invite_member: respects InviteRequest.channel. WhatsApp channel
#   additionally creates PhoneTenantMap + dispatches welcome message.

import re
import secrets
from typing import Optional

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.security import hash_password
from app.models.auth import TOP_TIER_ROLES, Tenant, User
from app.models.event import Event
from app.models.whatsapp import PhoneTenantMap
from app.schemas.team import (
    InviteRequest, RoleChangeRequest, TeamMemberOut, WhatsAppStatus,
)
from app.services.whatsapp_identity import (
    PhoneAlreadyLinkedError, link_phone_to_tenant,
)
from app.services.team_invite_whatsapp import send_invite_welcome


# Roles whose creation requires owner-level authority (handler-level guard
# layered ON TOP of require_top_tier). A factory_manager can invite a
# manager but cannot invite another factory_manager - that takes an owner
# or proprietor. Single-source set so PATCH and POST share the rule.
TOP_TIER_GRANT_ROLES: frozenset = frozenset(("owner", "proprietor"))


# v6.3.5: emails synthesised by the invite-by-phone path or by the legacy
# whatsapp_first signup are placeholders the user never reads. We strip them
# from API responses so the Team & Roles UI can render the "(unnamed)"
# empty state without doing its own pattern-matching. The two patterns
# below cover BOTH historical synthesisers:
#   - team invite path:        invite-<8hex>@invite.zetaops.com
#   - auth_service whatsapp_first: <slug>+nomail@whatsapp.local (legacy)
# Anything ending in @whatsapp.local is treated as synthesised because
# RFC 6761 reserves .local and no real mailbox can live there.
_SYNTHESISED_EMAIL_PATTERNS = (
    re.compile(r"^invite-[0-9a-f]{4,16}@invite\.zetaops\.com$"),
    re.compile(r"@whatsapp\.local$"),
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _is_synthesised_email(email: Optional[str]) -> bool:
    """
    True if `email` matches one of the placeholder patterns the system
    synthesises for users who never supplied a real address.

    Called by: _serialise_member, list_team_members_with_status.
    Calls into: nothing - pure regex.

    Used to decide whether the `email` field of TeamMemberOut should be
    surfaced (real address) or nulled (placeholder). Both v6.3.3 invite
    placeholders and legacy auth_service whatsapp_first placeholders are
    detected.
    """
    if not email:
        return False
    return any(p.search(email) for p in _SYNTHESISED_EMAIL_PATTERNS)


def _compute_whatsapp_status(
    mapping: Optional[PhoneTenantMap],
) -> WhatsAppStatus:
    """
    Map a PhoneTenantMap row (or None) to the four-value status enum.

    Called by: _serialise_member, list_team_members_with_status.
    Calls into: nothing - pure logic.

    Truth table:
        no mapping        -> 'none'         (user has no phone link)
        is_active=False   -> 'disconnected' (owner unlinked their number)
        consent_given=False -> 'invited'    (mapping exists, awaiting HAAN)
        consent_given=True  -> 'active'     (full handshake complete)

    Status drives the v6.3.5 Team & Roles status pill colour - keep this
    function as the single source of truth for that mapping.
    """
    if mapping is None:
        return "none"
    if not mapping.is_active:
        return "disconnected"
    if not mapping.consent_given:
        return "invited"
    return "active"


def _pick_best_mapping(
    mappings: list[PhoneTenantMap],
) -> Optional[PhoneTenantMap]:
    """
    Pick the most relevant PhoneTenantMap row for a user.

    Called by: list_team_members_with_status (after the bulk fetch).
    Calls into: nothing - pure list comparison.

    A user MAY have multiple PhoneTenantMap rows (e.g. they re-linked their
    phone after unlinking). Picks the active row if any, else the row with
    the most recent linked_at. Returns None if the list is empty.
    """
    if not mappings:
        return None
    active = [m for m in mappings if m.is_active]
    pool = active if active else mappings
    return max(pool, key=lambda m: m.linked_at)


def _serialise_member(
    user: User,
    mapping: Optional[PhoneTenantMap],
) -> TeamMemberOut:
    """
    Convert (User, PhoneTenantMap) into a TeamMemberOut with v6.3.5 fields.

    Called by: list_team_members_with_status (per row), invite_member
               (return path), change_member_role (return path),
               team_management.invite (response shaping).
    Calls into: _is_synthesised_email, _compute_whatsapp_status.

    Strips synthesised emails (returns None in the .email field) and
    surfaces PhoneTenantMap.display_name as `name`.
    """
    email_out: Optional[str] = None if _is_synthesised_email(user.email) else user.email
    return TeamMemberOut(
        id=user.id,
        email=email_out,
        phone_e164=user.phone_e164,
        role=user.role,
        is_active=user.is_active,
        is_top_tier=user.is_top_tier,
        created_via=user.created_via,
        whatsapp_status=_compute_whatsapp_status(mapping),
        name=mapping.display_name if mapping else None,
    )


def is_last_owner(tenant_id: int, user_id: int, db: Session) -> bool:
    """
    True if removing or demoting `user_id` would leave the tenant with zero
    active top-tier (owner-equivalent) users.

    Called by: change_member_role() (when new_role is NOT top-tier),
               delete_member().
    Calls into: SQLAlchemy SELECT COUNT(*) on users filtered by tenant
                + role IN TOP_TIER_ROLES + is_active.
    Side effects: none - pure read.
    """
    target = db.query(User).filter(
        User.id == user_id, User.tenant_id == tenant_id
    ).first()
    if target is None:
        return False
    if not target.is_top_tier or not target.is_active:
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

    All team-management events share entity_type='user' and source='web'.
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

    Called by: invite_member().
    Calls into: secrets.token_urlsafe.
    """
    return secrets.token_urlsafe(12)  # ~16 chars after base64


def _classify_email_or_phone(email_or_phone: str) -> tuple[Optional[str], Optional[str]]:
    """
    Split the InviteRequest.email_or_phone freeform field into (email, phone).

    Called by: invite_member().
    Calls into: nothing - pure string check on '@'.
    """
    if "@" in email_or_phone:
        return (email_or_phone, None)
    return (None, email_or_phone)


def _resolve_channel(payload: InviteRequest) -> tuple[str, bool]:
    """
    Decide which channel ('whatsapp' or 'desktop') to use for an invite.

    Called by: invite_member().
    Calls into: nothing - pure logic.

    Returns: (channel, was_explicit).
        was_explicit=True only when payload.channel was non-None. Back-compat
        with v6.3.3 callers depends on this distinction: when the caller did
        NOT set channel, the invite path does NOT create a PhoneTenantMap row,
        does NOT dispatch a welcome handshake, and does NOT enforce
        consent_given. v6.3.5 frontend always sets channel explicitly.

    Rules:
      - explicit payload.channel wins; we still validate that it matches
        the email_or_phone shape (else 400).
      - else infer from email_or_phone shape ('@' -> desktop, else whatsapp).

    Raises HTTPException 400 when an explicit channel contradicts the shape
    of email_or_phone (e.g. channel='whatsapp' with an email address).
    """
    inferred = "desktop" if "@" in payload.email_or_phone else "whatsapp"
    if payload.channel is None:
        return inferred, False
    if payload.channel != inferred:
        raise HTTPException(
            status_code=400,
            detail=(
                f"channel='{payload.channel}' does not match email_or_phone "
                f"shape (looks like a {inferred} contact). Use a phone number "
                f"for WhatsApp invites and an email address for desktop invites."
            ),
        )
    return payload.channel, True


# ---------------------------------------------------------------------------
# Service entry points
# ---------------------------------------------------------------------------

def list_team_members(tenant_id: int, db: Session) -> list[User]:
    """
    Return every active+inactive User in the tenant, ordered by id.

    Called by: tests/test_team_management.py (legacy v6.3.3 callers).
    Calls into: SQLAlchemy SELECT * FROM users WHERE tenant_id = :t.

    v6.3.5 keeps this function as-is so existing test_team_management
    fixtures continue to read raw User rows. The router uses the
    enriched variant below.
    """
    return db.query(User).filter(
        User.tenant_id == tenant_id,
    ).order_by(User.id).all()


def serialise_member_for_response(user: User, db: Session) -> TeamMemberOut:
    """
    One-shot serialiser for a single User -> TeamMemberOut response.

    Called by: routers/team_management (invite + change_role responses).
    Calls into: _pick_best_mapping, _serialise_member, one DB query.

    Does ONE extra SELECT to fetch the user's PhoneTenantMap row(s); cheap
    in absolute terms but worth a comment because it is N+1-shaped if a
    future caller iterates over a list with this. For lists, use
    list_team_members_with_status which fetches all mappings in one query.
    """
    rows = db.execute(
        select(PhoneTenantMap).where(PhoneTenantMap.user_id == user.id)
    ).scalars().all()
    return _serialise_member(user, _pick_best_mapping(list(rows)))


def list_team_members_with_status(
    tenant_id: int, db: Session,
) -> list[TeamMemberOut]:
    """
    Return TeamMemberOut rows enriched with whatsapp_status + display name.

    Called by: routers/team_management.list_team (v6.3.5+).
    Calls into:
      - SELECT users WHERE tenant_id ORDER BY id  (one query)
      - SELECT phone_tenant_map WHERE user_id IN (..)  (one query)
      - _pick_best_mapping per user (in-memory grouping)
      - _serialise_member per user

    This is N+1-safe: TWO total DB queries regardless of team size, then
    in-memory bucketing. Per CLAUDE.md "N+1 Queries Are Forbidden".

    Side effects: none - pure read.
    """
    users = db.query(User).filter(
        User.tenant_id == tenant_id,
    ).order_by(User.id).all()

    if not users:
        return []

    user_ids = [u.id for u in users]
    mapping_rows = db.execute(
        select(PhoneTenantMap).where(PhoneTenantMap.user_id.in_(user_ids))
    ).scalars().all()

    # Group by user_id - O(N) in mapping_rows, no further DB queries.
    by_user: dict[int, list[PhoneTenantMap]] = {}
    for m in mapping_rows:
        by_user.setdefault(m.user_id, []).append(m)

    return [
        _serialise_member(u, _pick_best_mapping(by_user.get(u.id, [])))
        for u in users
    ]


def invite_member(
    tenant_id: int,
    actor_user_id: int,
    actor_role: str,
    payload: InviteRequest,
    db: Session,
) -> tuple[User, Optional[str]]:
    """
    Create a new User in the actor's tenant.

    Returns the legacy v6.3.3 2-tuple (user, temp_password) so existing
    callers (test_team_management) keep working unchanged. The v6.3.5
    router additionally calls _serialise_member after this returns to
    build the enriched TeamMemberOut response.

    Permission rules layered on top of require_top_tier:
      - require_top_tier (in router) gates entry.
      - Only owner/proprietor can invite into TOP_TIER_ROLES.
      - Whatsapp channel: consent_given must be True.

    Called by: routers/team_management.py:invite,
               tests/test_team_management.py,
               tests/test_team_invite_v6_3_5.py.
    Calls into: hash_password, link_phone_to_tenant, send_invite_welcome,
                _emit_event, db.add/db.flush.
    Side effects: INSERT users (+ INSERT phone_tenant_map for whatsapp
                  channel) + INSERT events. Caller commits.

    Returns: (new_user, temp_password). temp_password is a cryptographic
             random string for desktop channel and None for whatsapp
             channel - the recipient authenticates via WhatsApp HAAN.
    Raises:  HTTPException(400) on duplicate / consent missing /
             channel-shape mismatch. HTTPException(403) on permission.
             HTTPException(409) on phone already linked to this tenant.
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

    channel, channel_was_explicit = _resolve_channel(payload)

    # Consent gate fires ONLY for v6.3.5 explicit-channel WhatsApp invites.
    # v6.3.3 callers (channel=None) continue to use the legacy phone-invite
    # path verbatim - no consent field, no PhoneTenantMap, no welcome
    # message. The new InviteMemberModal always sends channel explicitly.
    if channel == "whatsapp" and channel_was_explicit and not payload.consent_given:
        raise HTTPException(
            status_code=400,
            detail=(
                "WhatsApp invites require consent_given=True. The inviter "
                "confirms the recipient agreed to receive WhatsApp messages "
                "from ZetaOps Copilot for factory operations."
            ),
        )

    email, phone = _classify_email_or_phone(payload.email_or_phone)

    # Cross-table uniqueness: email is globally unique in the schema.
    if email and db.query(User).filter(User.email == email).first():
        raise HTTPException(
            status_code=400, detail=f"Email {email} is already registered."
        )
    if phone and db.query(User).filter(User.phone_e164 == phone).first():
        raise HTTPException(
            status_code=400,
            detail=f"Phone {phone} is already in use by another user.",
        )

    # Phone-only invites synthesise a placeholder email so the
    # NOT NULL + UNIQUE constraints on User.email are satisfied. v6.3.5 strips
    # this on the wire (see _is_synthesised_email).
    if email is None:
        email = f"invite-{secrets.token_hex(4)}@invite.zetaops.com"

    # Always generate a temp password for desktop channel; for whatsapp
    # channel the recipient authenticates via the HAAN handshake so the
    # password is never delivered to them. We still hash a random password
    # to keep the column NOT NULL.
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
    db.flush()  # populate new_user.id for the event row + phone link

    # v6.3.5: only the EXPLICIT whatsapp-channel path creates the
    # PhoneTenantMap and dispatches the welcome handshake. v6.3.3 phone
    # invites (channel=None) continue to skip both - mirrors legacy
    # behaviour byte-for-byte.
    if channel == "whatsapp" and channel_was_explicit:
        # Look up tenant_name BEFORE link_phone_to_tenant so the welcome
        # message can address the recipient with their factory's name.
        tenant_row = db.query(Tenant).filter(Tenant.id == tenant_id).first()
        tenant_name = tenant_row.name if tenant_row else "your team"

        try:
            link_phone_to_tenant(
                db,
                tenant_id=tenant_id,
                user_id=new_user.id,
                phone_number=phone,
                phone_role="owner" if payload.role in TOP_TIER_ROLES else "manager",
                display_name=payload.name,
                consent_given=False,  # awaiting HAAN reply
            )
        except PhoneAlreadyLinkedError:
            raise HTTPException(
                status_code=409,
                detail=f"Phone {phone} is already linked to this tenant.",
            )

        # Dispatch the welcome handshake. Mock-mode logs [MOCK ALERT];
        # real-mode POSTs to Interakt. Either way an audit event row
        # for member.invited_whatsapp is staged on the session.
        send_invite_welcome(
            user=new_user,
            phone_e164=phone,
            tenant_name=tenant_name,
            invitee_name=payload.name,
            actor_user_id=actor_user_id,
            db=db,
        )

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
            "channel":  channel,
            "name":     payload.name,
            "actor_id": actor_user_id,
        },
    )

    db.commit()
    db.refresh(new_user)

    # v6.3.5 explicit-whatsapp invites do not surface a password (the
    # invitee authenticates via WhatsApp HAAN). v6.3.3 phone invites
    # (channel inferred) and desktop invites continue to return the
    # temp password as before.
    returned_password = (
        None if (channel == "whatsapp" and channel_was_explicit) else temp_password
    )
    return new_user, returned_password


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

    Called by: routers/team_management.py:change_role
    Calls into: is_last_owner, _emit_event.
    Side effects: UPDATE users + INSERT events. Caller commits.
    """
    target = db.query(User).filter(
        User.id == target_user_id, User.tenant_id == tenant_id
    ).first()
    if target is None:
        raise HTTPException(status_code=404, detail="User not found in this tenant")

    old_role = target.role
    if old_role == payload.role:
        return target

    if payload.role in TOP_TIER_ROLES and actor_role not in TOP_TIER_GRANT_ROLES:
        raise HTTPException(
            status_code=403,
            detail=(
                f"Role '{actor_role}' cannot promote into top-tier roles. "
                f"Only {sorted(TOP_TIER_GRANT_ROLES)} can grant top-tier."
            ),
        )

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

    Called by: routers/team_management.py:delete_member.
    Calls into: is_last_owner, _emit_event.
    Side effects: UPDATE users.is_active = false + INSERT events.
    """
    target = db.query(User).filter(
        User.id == target_user_id, User.tenant_id == tenant_id
    ).first()
    if target is None:
        raise HTTPException(status_code=404, detail="User not found in this tenant")

    if not target.is_active:
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
