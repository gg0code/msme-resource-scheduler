# whatsapp_send.py
# Branch: v5-whatsapp
#
# FILE PURPOSE
# Single source of truth for outbound WhatsApp text sends. Owns the
# three-branch precedence:
#   1. WHATSAPP_MOCK_MODE=True              -> log only, no HTTP
#   2. WHATSAPP_ACCESS_TOKEN
#      + WHATSAPP_PHONE_NUMBER_ID set       -> POST to graph.facebook.com (Meta)
#   3. otherwise                            -> log error, no HTTP
#
# Lives in services/ rather than routers/ so the alert scheduler
# (whatsapp_alerts.py), the FastAPI router, and the team invite path
# can all import it without creating an import cycle.
#
# WHO CALLS THIS FILE
#   app/routers/whatsapp.py              - inbound message reply path
#   app/services/whatsapp_alerts.py      - _send_alert delegates here
#   app/services/team_invite_whatsapp.py - invite welcome (sync->async bridge)
#
# WHAT THIS FILE CALLS
#   app/config.settings  - WHATSAPP_MOCK_MODE,
#                          WHATSAPP_ACCESS_TOKEN, WHATSAPP_PHONE_NUMBER_ID
#   httpx                - async POST to Meta Cloud API

import logging

import httpx

from app.config import settings

logger = logging.getLogger(__name__)


async def _send_whatsapp_message(phone_number: str, message: str) -> None:
    """
    Send a WhatsApp text message via Meta Cloud API.

    Branches on env-var configuration. Precedence:
      1. WHATSAPP_MOCK_MODE=True            -> log only, no HTTP call
      2. WHATSAPP_ACCESS_TOKEN
         + WHATSAPP_PHONE_NUMBER_ID set     -> POST to Meta Cloud API direct
      3. otherwise                          -> log error, no-op

    Args:
        phone_number: E.164 format e.g. +919876543210
        message:      Plain text (already formatted, no markdown).

    Side effects:
        Mock: writes to log. Real: HTTP POST to Meta. Returns None
        on every path, including failure — callers do not branch on success.
    """
    if settings.WHATSAPP_MOCK_MODE:
        logger.info(
            f"[MOCK SEND] To=****{phone_number[-4:]} "
            f"Message='{message[:100]}{'...' if len(message) > 100 else ''}'"
        )
        return

    phone_without_plus = phone_number.lstrip("+")

    if settings.WHATSAPP_ACCESS_TOKEN and settings.WHATSAPP_PHONE_NUMBER_ID:
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"https://graph.facebook.com/v21.0/{settings.WHATSAPP_PHONE_NUMBER_ID}/messages",
                    headers={
                        "Authorization": f"Bearer {settings.WHATSAPP_ACCESS_TOKEN}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "messaging_product": "whatsapp",
                        "to": phone_without_plus,
                        "type": "text",
                        "text": {"body": message},
                    },
                    timeout=10.0,
                )
                if response.status_code // 100 != 2:
                    # Meta error body contains useful debug info, e.g.
                    # "(#190) access token expired", "(#10) recipient not allowlisted".
                    logger.error(
                        f"Meta error {response.status_code} "
                        f"for ****{phone_number[-4:]}: {response.text[:300]}"
                    )
        except httpx.TimeoutException:
            logger.error(f"Meta timeout for ****{phone_number[-4:]}.")
        except Exception as e:
            logger.error(f"Meta send failed for ****{phone_number[-4:]}: {e}")
        return

    logger.error(
        "WhatsApp send unconfigured: set WHATSAPP_ACCESS_TOKEN and "
        "WHATSAPP_PHONE_NUMBER_ID, or set WHATSAPP_MOCK_MODE=True for dev."
    )
