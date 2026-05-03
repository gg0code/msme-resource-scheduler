# app/services/team_invite_whatsapp.py - WhatsApp invite welcome handshake
# Branch: v5-whatsapp
# Iteration: v6.3.5 (routed through _send_whatsapp_message)
#
# FILE PURPOSE
# Sync helper that dispatches the welcome WhatsApp message asking a freshly
# invited team member to reply HAAN/YES to confirm consent. Wired into the
# v6.3.5 invite flow so the entire team-management codepath stays sync.
#
# WHO CALLS THIS FILE
# - app/services/team_service.invite_member (when channel == 'whatsapp')
# - tests/test_team_invite_v6_3_5.py        (assertions on mock-mode log
#                                             + event row emission)
#
# WHAT THIS FILE CALLS
# - app/config.settings (WHATSAPP_MOCK_MODE)
# - app/models/event.Event (writes member.invited_whatsapp event row)
# - app/services.whatsapp_send._send_whatsapp_message (async helper bridged
#   here via asyncio.run because the team service request thread is sync)
#
# DESIGN NOTES
# - send_invite_welcome is SYNC. The team_service.invite_member route runs
#   inside FastAPI's sync request threadpool. We bridge the async send
#   helper via asyncio.run() - the threadpool thread has no live event
#   loop so that's safe and avoids propagating async through team service.
# - Mock-mode log format MIRRORS whatsapp_alerts._send_alert exactly:
#       [MOCK ALERT] Type=invite_welcome To=****1234 Message='...'
#   Tests grep for this exact prefix - keep the format stable.
# - Decision Q7 (v6.3.5): we emit a member.invited_whatsapp event row on
#   EVERY dispatch (mock or real). Audit consistency with v6.3.3
#   user.invited / v6.3.4 briefing.* event rows. _send_whatsapp_message
#   swallows transport errors and never raises, so sent_ok is always True
#   from this layer's perspective; dispatch_mode distinguishes mock vs
#   real attempts for post-mortem queries.
# - The caller (team_service.invite_member) commits the transaction. We
#   only db.add() the event row here - never commit.

import asyncio
import logging
from typing import Optional, Tuple

from sqlalchemy.orm import Session

from app.config import settings
from app.models.auth import User
from app.models.event import Event
from app.services.whatsapp_send import _send_whatsapp_message


logger = logging.getLogger(__name__)


# Welcome message text. Mirrors the bilingual style of WELCOME_REGISTERED in
# routers/whatsapp.py so a recipient who has interacted with ZetaOps before
# (e.g. linked another tenant's number) sees a consistent voice. ASCII only
# (Lesson 16 / 36) - no Devanagari, no smart quotes.
INVITE_WELCOME_TEMPLATE = (
    "Namaste{name_part}! Aapko {tenant_name} team mein "
    "ZetaOps Copilot ka access mila hai.\n\n"
    "Reply karein:\n"
    "HAAN - confirm karne ke liye\n"
    "NAHI - decline karne ke liye\n\n"
    "Aapki consent ke baad aap factory updates WhatsApp pe seedhe "
    "yahan se manage kar sakte hain."
)


def _build_welcome_message(
    *,
    invitee_name: Optional[str],
    tenant_name: str,
) -> str:
    """
    Format the welcome message body.

    Called by: send_invite_welcome (this file).
    Calls into: nothing - pure string formatting.

    Args:
        invitee_name: optional display name from PhoneTenantMap.display_name.
                      Renders as ", <name>" suffix when present, else empty.
        tenant_name:  Tenant.name for "Aapko <Tenant> team mein..." line.

    Returns: complete message text, ASCII-only, no leading/trailing whitespace.
    """
    name_part = f", {invitee_name}" if invitee_name else ""
    return INVITE_WELCOME_TEMPLATE.format(
        name_part=name_part,
        tenant_name=tenant_name,
    )


def send_invite_welcome(
    *,
    user: User,
    phone_e164: str,
    tenant_name: str,
    invitee_name: Optional[str],
    actor_user_id: int,
    db: Session,
) -> Tuple[bool, str]:
    """
    Dispatch the WhatsApp consent-handshake welcome to a newly invited member.

    In mock mode (WHATSAPP_MOCK_MODE=True): logs '[MOCK ALERT] ...' and
    delegates to _send_whatsapp_message which short-circuits with
    '[MOCK SEND]'. In production mode: delegates straight to
    _send_whatsapp_message which POSTs to Meta Cloud API. Either way an
    Event row of type 'member.invited_whatsapp' is staged on the session
    so the audit trail records the dispatch.

    Called by: team_service.invite_member (channel='whatsapp' branch).
    Calls into: _build_welcome_message, settings, asyncio.run wrapping
                _send_whatsapp_message, db.add (Event).
    Side effects:
        - Mock mode: writes [MOCK ALERT] + [MOCK SEND] log lines.
        - Real mode: makes one HTTP POST via _send_whatsapp_message.
        - Always: stages one INSERT into events. Caller commits.

    Args:
        user:         the freshly created invitee User row. Used for event
                      payload (user_id) and as the entity_id of the event.
        phone_e164:   E.164 phone string the welcome message goes to. Must
                      already be linked in PhoneTenantMap before calling.
        tenant_name:  inviter's tenant name, woven into the message body.
        invitee_name: optional display name (PhoneTenantMap.display_name).
        actor_user_id: who clicked "Send WhatsApp invite" - goes into the
                       event row's actor_user_id column for audit.
        db:           sync SQLAlchemy session owned by the caller.

    Returns:
        (sent_ok, message_text). sent_ok is True; _send_whatsapp_message
        logs transport errors but never raises, so this layer cannot
        observe HTTP failures synchronously.
    """
    message = _build_welcome_message(
        invitee_name=invitee_name,
        tenant_name=tenant_name,
    )

    if settings.WHATSAPP_MOCK_MODE:
        # Format MUST match whatsapp_alerts._send_alert so log-grep tests
        # share the same matcher. Truncate at 150 chars to mirror that
        # function exactly.
        logger.info(
            f"[MOCK ALERT] Type=invite_welcome "
            f"To=****{phone_e164[-4:]} "
            f"Message='{message[:150]}{'...' if len(message) > 150 else ''}'"
        )
        dispatch_mode = "mock"
    else:
        logger.info(
            f"Dispatching invite welcome. To=****{phone_e164[-4:]}"
        )
        dispatch_mode = "dispatched"

    # Bridge sync->async. The team service runs in FastAPI's sync request
    # threadpool, which has no live event loop, so asyncio.run is safe.
    asyncio.run(_send_whatsapp_message(phone_e164, message))

    # Always emit the audit row so the dashboard can surface "n invites
    # dispatched" alongside v6.3.3 user.invited rows. dispatch_mode
    # distinguishes mock from real attempts for post-mortem queries.
    db.add(Event(
        tenant_id=user.tenant_id,
        event_type="member.invited_whatsapp",
        entity_type="user",
        entity_id=user.id,
        actor_user_id=actor_user_id,
        source="web",
        payload={
            "user_id":       user.id,
            "phone":         phone_e164,
            "dispatch_mode": dispatch_mode,
            "sent_ok":       True,
        },
    ))

    return True, message
