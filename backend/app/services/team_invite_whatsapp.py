# app/services/team_invite_whatsapp.py - WhatsApp invite welcome handshake
# Branch: v5-whatsapp
# Iteration: v6.3.5
#
# FILE PURPOSE
# Sync helper that dispatches the welcome WhatsApp message asking a freshly
# invited team member to reply HAAN/YES to confirm consent. Wired into the
# v6.3.5 invite flow so the entire team-management codepath stays sync (the
# async _send_alert in whatsapp_alerts.py is for APScheduler jobs that own
# their own event loop - request-thread invite handling cannot piggyback on
# that without an awkward run_until_complete).
#
# WHO CALLS THIS FILE
# - app/services/team_service.invite_member  (when channel == 'whatsapp')
# - tests/test_team_invite_v6_3_5.py         (assertions on mock-mode log
#                                              + event row emission)
#
# WHAT THIS FILE CALLS
# - app/config.settings (WHATSAPP_MOCK_MODE, INTERAKT_API_KEY)
# - app/models/event.Event (writes member.invited_whatsapp event row)
# - httpx.Client (sync) for the Interakt POST in production mode
# - logging for the [MOCK ALERT] line in mock mode
#
# DESIGN NOTES
# - send_invite_welcome is SYNC. The team_service.invite_member route runs
#   inside FastAPI's sync request thread. Going async here would propagate
#   async through the entire team service layer for one HTTP call - not
#   worth the churn. We use httpx.Client (sync) for production sends.
# - Mock-mode log format MIRRORS whatsapp_alerts._send_alert exactly:
#       [MOCK ALERT] Type=invite_welcome To=****1234 Message='...'
#   Tests grep for this exact prefix - keep the format stable.
# - Decision Q7 (v6.3.5): we emit a member.invited_whatsapp event row on
#   EVERY dispatch (mock or real, success or skipped). Audit consistency
#   with v6.3.3 user.invited / v6.3.4 briefing.* event rows. Event row
#   payload distinguishes mock vs sent so the audit trail stays accurate.
# - The caller (team_service.invite_member) commits the transaction. We
#   only db.add() the event row here - never commit.

import logging
from typing import Optional, Tuple

from sqlalchemy.orm import Session

from app.config import settings
from app.models.auth import User
from app.models.event import Event


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
    returns (True, message). In production mode: POSTs to Interakt via
    sync httpx.Client and returns (success_bool, message). Either way an
    Event row of type 'member.invited_whatsapp' is staged on the session
    so the audit trail records the dispatch even when the network send fails.

    Called by: team_service.invite_member (channel='whatsapp' branch).
    Calls into: _build_welcome_message, settings, httpx.Client (production
                only), db.add (Event).
    Side effects:
        - Mock mode: writes one log line.
        - Real mode: makes one HTTP POST to api.interakt.ai. 10s timeout.
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
        (sent_ok, message_text). sent_ok is True for mock (always), True
        for real-mode 200 OK, False for any production failure path.
    """
    message = _build_welcome_message(
        invitee_name=invitee_name,
        tenant_name=tenant_name,
    )

    sent_ok: bool
    dispatch_mode: str  # 'mock' | 'sent' | 'skipped_no_key' | 'failed'

    if settings.WHATSAPP_MOCK_MODE:
        # Format MUST match whatsapp_alerts._send_alert so log-grep tests
        # share the same matcher. Truncate at 150 chars to mirror that
        # function exactly.
        logger.info(
            f"[MOCK ALERT] Type=invite_welcome "
            f"To=****{phone_e164[-4:]} "
            f"Message='{message[:150]}...'"
        )
        sent_ok = True
        dispatch_mode = "mock"
    elif not settings.INTERAKT_API_KEY:
        logger.error(
            "INTERAKT_API_KEY not set in .env but WHATSAPP_MOCK_MODE=False. "
            "Cannot send invite welcome. Set INTERAKT_API_KEY in .env or set "
            "WHATSAPP_MOCK_MODE=True for development."
        )
        sent_ok = False
        dispatch_mode = "skipped_no_key"
    else:
        sent_ok, dispatch_mode = _post_to_interakt(phone_e164, message)

    # Always emit the audit row - even on failed sends - so the dashboard
    # can surface "n invites stalled" if Interakt is down. The payload
    # carries dispatch_mode so post-mortem queries can filter accordingly.
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
            "sent_ok":       sent_ok,
        },
    ))

    return sent_ok, message


def _post_to_interakt(phone_e164: str, message: str) -> Tuple[bool, str]:
    """
    Sync HTTP POST to Interakt's /v1/public/message/ endpoint.

    Called by: send_invite_welcome (this file, production mode only).
    Calls into: httpx.Client (sync). Imported lazily so test envs that
                stub WHATSAPP_MOCK_MODE=True do not pay the import cost.

    Returns: (sent_ok, dispatch_mode_string). dispatch_mode is 'sent' on
             HTTP 200, 'failed' otherwise. Errors are logged - never raised
             - so a transient Interakt outage never 500s the invite endpoint.
    """
    try:
        import httpx

        phone_without_plus = phone_e164.lstrip("+")

        with httpx.Client() as client:
            response = client.post(
                "https://api.interakt.ai/v1/public/message/",
                headers={
                    "Authorization": f"Basic {settings.INTERAKT_API_KEY}",
                    "Content-Type":  "application/json",
                },
                json={
                    "countryCode": "91",
                    "phoneNumber": phone_without_plus,
                    "type":        "Text",
                    "data":        {"message": message},
                },
                timeout=10.0,
            )

        if response.status_code == 200:
            logger.info(
                f"Invite welcome sent via Interakt. "
                f"To=****{phone_e164[-4:]}"
            )
            return True, "sent"

        logger.error(
            f"Interakt API error {response.status_code} sending invite "
            f"welcome to ****{phone_e164[-4:]}: {response.text[:200]}"
        )
        return False, "failed"

    except Exception as exc:
        logger.exception(
            f"Failed to send invite welcome to ****{phone_e164[-4:]}: {exc}"
        )
        return False, "failed"
