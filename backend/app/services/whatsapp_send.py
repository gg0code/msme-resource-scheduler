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
#   app/services/promotion/promoter.py   - confirmation send (v6.3.15 rev)
#
# WHAT THIS FILE CALLS
#   app/config.settings  - WHATSAPP_MOCK_MODE,
#                          WHATSAPP_ACCESS_TOKEN, WHATSAPP_PHONE_NUMBER_ID
#   httpx                - async POST to Meta Cloud API
#   uuid                 - synthetic wamid generation in mock mode
#
# RETURN-TYPE NOTE (v6.3.15 revised)
#   The function used to return None on every branch. As of v6.3.15
#   (revised) it returns Optional[str] — the WhatsApp message id
#   (wamid) on success, or None on failure. v6.3.15's confirmation
#   audit trail uses this id to link the outbound proposal to the
#   inbound reply via WhatsApp's context.id quote-reference. Existing
#   callers that ignored the return value continue to work — None has
#   become a strict subset of the new return type.
#
#   In mock mode we return a synthetic id of the form
#   "mock_wamid_<uuid_hex_16>" so dev/test code paths still have a
#   non-empty id to record. Real-mode callers parse messages[0].id
#   from the Meta response.

import logging
import uuid
from typing import Optional

import httpx

from app.config import settings

logger = logging.getLogger(__name__)


async def _send_whatsapp_message(phone_number: str, message: str) -> Optional[str]:
    """
    Send a WhatsApp text message via Meta Cloud API.

    Branches on env-var configuration. Precedence:
      1. WHATSAPP_MOCK_MODE=True            -> log only, no HTTP call;
                                               returns synthetic wamid
      2. WHATSAPP_ACCESS_TOKEN
         + WHATSAPP_PHONE_NUMBER_ID set     -> POST to Meta Cloud API
                                               direct; returns the wamid
                                               from messages[0].id, or
                                               None on failure
      3. otherwise                          -> log error, returns None

    Args:
        phone_number: E.164 format e.g. +919876543210
        message:      Plain text (already formatted, no markdown).

    Returns:
        The WhatsApp message id (wamid) on successful send, or a
        synthetic "mock_wamid_..." string in mock mode. None on any
        send failure (timeout, non-2xx, missing config). Callers may
        ignore the return value — they did before v6.3.15 and the
        widening from None -> Optional[str] is backwards-compatible.

    Side effects:
        Mock: writes to log. Real: HTTP POST to Meta.
    """
    if settings.WHATSAPP_MOCK_MODE:
        # Synthetic wamid lets v6.3.15's audit trail (and future
        # context.id-based reply matching) operate identically in
        # dev / test. Format chosen to be visually distinct from a
        # real Meta wamid (which starts "wamid.").
        synthetic_id = f"mock_wamid_{uuid.uuid4().hex[:16]}"
        logger.info(
            f"[MOCK SEND] To=****{phone_number[-4:]} "
            f"Message='{message[:100]}{'...' if len(message) > 100 else ''}' "
            f"wamid={synthetic_id}"
        )
        return synthetic_id

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
                    return None
                # 2xx body shape:
                #   {"messaging_product":"whatsapp","contacts":[...],
                #    "messages":[{"id":"wamid.HBg..."}]}
                try:
                    payload = response.json()
                    messages = payload.get("messages") or []
                    if messages and isinstance(messages[0], dict):
                        wamid = messages[0].get("id")
                        if wamid:
                            return str(wamid)
                except (ValueError, KeyError, TypeError) as parse_err:
                    logger.warning(
                        f"Meta 2xx but wamid parse failed for "
                        f"****{phone_number[-4:]}: {parse_err}"
                    )
                return None
        except httpx.TimeoutException:
            logger.error(f"Meta timeout for ****{phone_number[-4:]}.")
            return None
        except Exception as e:
            logger.error(f"Meta send failed for ****{phone_number[-4:]}: {e}")
            return None

    logger.error(
        "WhatsApp send unconfigured: set WHATSAPP_ACCESS_TOKEN and "
        "WHATSAPP_PHONE_NUMBER_ID, or set WHATSAPP_MOCK_MODE=True for dev."
    )
    return None
