"""
FILE:    whatsapp.py
PATH:    backend/app/routers/whatsapp.py
PURPOSE: FastAPI router — the entry point for all WhatsApp messages.

         Three endpoints:
           GET  /api/v1/whatsapp/webhook  — Meta webhook verification handshake.
                                            Called once by Meta when you register
                                            your webhook URL in the developer dashboard.

           POST /api/v1/whatsapp/webhook  — Receives inbound WhatsApp messages
                                            from Meta via Interakt. Verifies signature,
                                            resolves identity, loads session, calls AI,
                                            formats response, sends back to owner.

           POST /api/v1/whatsapp/simulate — Development only. Simulates a full inbound
                                            message without real WhatsApp. Used for all
                                            testing through v5.0-v5.4. Disabled when
                                            WHATSAPP_MOCK_MODE=False.

         Message flow for POST /webhook:
           1. Verify Meta signature (security)
           2. Extract message from payload
           3. Resolve phone to tenant identity
           4. Check for pending confirmation (write action state machine)
           5. Load conversation session from Redis
           6. Add new message to session
           7. Call AI via whatsapp_bridge.active_bridge
           8. Add AI response to session
           9. Format response for WhatsApp (strip markdown)
           10. Send response via Interakt (or log in mock mode)
           11. Log conversation if consent given

BRANCH:  v5-whatsapp
VERSION: v5.0
CREATED: 2026-03

DEPENDENCIES:
  app/services/whatsapp_identity.py  — resolve_identity(), record_consent()
  app/services/whatsapp_session.py   — add_message_to_session(), get_ai_history()
  app/services/whatsapp_bridge.py    — active_bridge.process_message()
  app/services/whatsapp_formatter.py — format_for_whatsapp(), detect_language()
  app/services/whatsapp_actions.py   — confirmation state machine functions
  app/models/whatsapp.py             — WhatsAppConversation for logging
  app/database.py                    — SessionLocal for sync DB sessions
  app/config.py                      — settings (WHATSAPP_MOCK_MODE etc.)

NOTES:
  - Uses sync SessionLocal directly (not Depends(get_db)) because the app
    uses synchronous SQLAlchemy sessions throughout. get_db() is a sync
    generator which does not work cleanly with async FastAPI routes.
  - Always return 200 OK to Meta even on errors. Meta retries on non-200
    responses which causes the owner to receive duplicate messages.
  - /simulate is only available when WHATSAPP_MOCK_MODE=True.
"""

import hashlib
import hmac
import json
import logging

import httpx
from fastapi import APIRouter, HTTPException, Request, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.config import settings
from app.database import SessionLocal
from app.services.whatsapp_identity import resolve_identity, record_consent
from app.services.whatsapp_session import (
    add_message_to_session, get_ai_history, clear_session
)
from app.services.whatsapp_bridge import active_bridge
from app.services.whatsapp_formatter import format_for_whatsapp, detect_language
from app.services.whatsapp_actions import (
    is_confirmation, is_cancellation,
    get_pending_action, execute_action,
    clear_pending_action, build_confirmation_prompt,
    ActionType
)
from app.models.whatsapp import WhatsAppConversation

# ---------------------------------------------------------------------------
# Module logger
# ---------------------------------------------------------------------------
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Router — all endpoints prefixed with /api/v1/whatsapp
# ---------------------------------------------------------------------------
router = APIRouter(
    prefix="/api/v1/whatsapp",
    tags=["whatsapp"]
)

# ---------------------------------------------------------------------------
# CONSTANTS
# ---------------------------------------------------------------------------

# Word owner must send to give consent for conversation logging
CONSENT_TRIGGER = "haan"

# Sent to phones not registered in phone_tenant_map
WELCOME_UNREGISTERED = (
    "Namaste! Ye number ZetaOps mein registered nahi hai.\n"
    "Apna number link karne ke liye ZetaOps web app mein "
    "jaayein aur WhatsApp Link karein."
)

# Sent on first message from a registered phone — asks for consent
CONSENT_REQUEST = (
    "ZetaOps Copilot mein aapka swagat hai!\n\n"
    "Behtar service ke liye, kya hum aapki conversations "
    "improve karne ke liye use kar sakte hain?\n\n"
    "Reply karein:\n"
    "HAAN — agree karne ke liye\n"
    "NAHI — decline karne ke liye\n\n"
    "Aap bina consent ke bhi ZetaOps use kar sakte hain."
)


# ---------------------------------------------------------------------------
# PYDANTIC MODELS
# ---------------------------------------------------------------------------

class SimulateRequest(BaseModel):
    """
    Request body for POST /simulate.
    Simulates an inbound WhatsApp message for development testing.
    """
    phone: str           # E.164 format e.g. +919876543210
    message: str         # Message text to simulate
    type: str = "text"   # 'text' or 'voice'


class SimulateResponse(BaseModel):
    """Response from POST /simulate."""
    response: str
    tenant_id: int | None = None
    language: str = "english"
    formatted: bool = True


# ---------------------------------------------------------------------------
# ENDPOINT 1 — GET /webhook (Meta verification handshake)
# ---------------------------------------------------------------------------

@router.get("/webhook")
async def verify_webhook(
    hub_mode: str = Query(None, alias="hub.mode"),
    hub_verify_token: str = Query(None, alias="hub.verify_token"),
    hub_challenge: str = Query(None, alias="hub.challenge")
):
    """
    Handle Meta's one-time webhook verification handshake.

    Meta sends this GET request when you register your webhook URL
    in the Meta developer dashboard. We echo back hub.challenge if
    the verify token matches WHATSAPP_VERIFY_TOKEN in .env.

    Returns hub_challenge if verified, 403 if token mismatch.
    """
    if hub_mode == "subscribe" and hub_verify_token == settings.WHATSAPP_VERIFY_TOKEN:
        logger.info("Meta webhook verification successful.")
        return int(hub_challenge)

    logger.warning(
        f"Meta webhook verification failed. "
        f"Received token: '{hub_verify_token}', "
        f"Expected: '{settings.WHATSAPP_VERIFY_TOKEN}'. "
        f"Check WHATSAPP_VERIFY_TOKEN in .env."
    )
    raise HTTPException(status_code=403, detail="Webhook verification failed.")


# ---------------------------------------------------------------------------
# ENDPOINT 2 — POST /webhook (inbound messages)
# ---------------------------------------------------------------------------

@router.post("/webhook")
async def receive_webhook(request: Request):
    """
    Receive and process inbound WhatsApp messages from Meta via Interakt.

    Called every time a factory owner sends a WhatsApp message.
    Always returns 200 OK — Meta retries on non-200 causing duplicates.

    Uses SessionLocal directly (sync session) because the app uses
    synchronous SQLAlchemy throughout.
    """
    # Read raw body before parsing — needed for signature verification
    raw_body = await request.body()

    # Verify Meta signature in production mode only
    if not settings.WHATSAPP_MOCK_MODE:
        signature_valid = _verify_meta_signature(
            raw_body=raw_body,
            signature_header=request.headers.get("X-Hub-Signature-256", "")
        )
        if not signature_valid:
            logger.warning("Webhook signature verification failed — ignoring request.")
            return {"status": "ok"}

    # Parse JSON payload
    try:
        payload = json.loads(raw_body)
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse webhook payload: {e}")
        return {"status": "ok"}

    # Extract message from Meta's nested payload structure
    message_event = _extract_message_from_payload(payload)
    if message_event is None:
        # Normal — Meta sends status updates and read receipts too
        return {"status": "ok"}

    phone_number = message_event.get("phone_number")
    message_text = message_event.get("text", "")
    message_type = message_event.get("type", "text")

    logger.info(
        f"Inbound message from ****{phone_number[-4:]} — "
        f"type={message_type}, length={len(message_text)}"
    )

    # Process message using sync session
    db = SessionLocal()
    try:
        response_text = await _process_inbound_message(
            phone_number=phone_number,
            message_text=message_text,
            message_type=message_type,
            db=db
        )
    finally:
        db.close()

    # Send response back to owner
    if response_text:
        await _send_whatsapp_message(
            phone_number=phone_number,
            message=response_text
        )

    return {"status": "ok"}


# ---------------------------------------------------------------------------
# ENDPOINT 3 — POST /simulate (development only)
# ---------------------------------------------------------------------------

@router.post("/simulate", response_model=SimulateResponse)
async def simulate_message(body: SimulateRequest):
    """
    Simulate an inbound WhatsApp message without real WhatsApp.

    Development only — blocked when WHATSAPP_MOCK_MODE=False.
    Tests the full pipeline without Interakt or a real phone number.

    Returns 403 if called in production mode.
    """
    if not settings.WHATSAPP_MOCK_MODE:
        raise HTTPException(
            status_code=403,
            detail=(
                "Simulate endpoint disabled in production. "
                "Set WHATSAPP_MOCK_MODE=True in .env to enable."
            )
        )

    logger.info(
        f"Simulate: phone={body.phone}, "
        f"message='{body.message[:50]}', type={body.type}"
    )

    # Detect language of the message
    language = detect_language(body.message)

    # Process through full pipeline using sync session
    db = SessionLocal()
    try:
        response_text = await _process_inbound_message(
            phone_number=body.phone,
            message_text=body.message,
            message_type=body.type,
            db=db
        )

        # Get tenant_id for response metadata
        identity = await resolve_identity(
            phone_number=body.phone,
            db=db
        )
    finally:
        db.close()

    return SimulateResponse(
        response=response_text or "No response generated.",
        tenant_id=identity.tenant_id if identity else None,
        language=language,
        formatted=True
    )


# ---------------------------------------------------------------------------
# CORE PROCESSING PIPELINE
# ---------------------------------------------------------------------------

async def _process_inbound_message(
    phone_number: str,
    message_text: str,
    message_type: str,
    db: Session
) -> str | None:
    """
    Core message processing pipeline — shared by webhook and simulate endpoints.

    Runs the full flow:
      identity resolution → consent → confirmation state machine
      → session → AI call → format → log

    Args:
        phone_number:  E.164 format phone number.
        message_text:  Message text (transcribed if voice).
        message_type:  'text' or 'voice'.
        db:            Sync SQLAlchemy Session from SessionLocal.

    Returns:
        Formatted response string to send to owner, or None to ignore.
    """

    # Step 1: Resolve phone to tenant identity
    identity = await resolve_identity(phone_number=phone_number, db=db)

    if identity is None:
        # Phone not registered — send instructions
        return WELCOME_UNREGISTERED

    # Step 2: Handle consent on first message
    if not identity.consent_given:
        if message_text.lower().strip() == CONSENT_TRIGGER:
            # Owner replied HAAN — record consent
            await record_consent(phone_number=phone_number, db=db)
            return (
                "Shukriya! Aapki consent record ho gayi.\n"
                "Ab aap ZetaOps Copilot use kar sakte hain.\n\n"
                "Poochein: 'aaj ka schedule kya hai'"
            )
        else:
            # First message — ask for consent
            return CONSENT_REQUEST

    # Step 3: Check confirmation state machine
    # If there is a pending write action, handle confirmation/cancellation first
    pending_action = await get_pending_action(phone_number=phone_number)

    if pending_action:
        if is_confirmation(message_text):
            # Owner confirmed — execute the DB write
            success, result_message = await execute_action(
                pending_action=pending_action,
                db=db,
                tenant_id=identity.tenant_id
            )
            await clear_pending_action(phone_number=phone_number)
            return result_message

        elif is_cancellation(message_text):
            # Owner cancelled
            await clear_pending_action(phone_number=phone_number)
            return "Theek hai, action cancel kar diya. Kuch aur poochein?"

        else:
            # Something else sent while action pending — remind owner
            return (
                f"Ek action abhi bhi pending hai:\n\n"
                f"{build_confirmation_prompt(ActionType(pending_action['action_type']), pending_action['action_params'])}"
            )

    # Step 4: Handle session reset commands
    if message_text.lower().strip() in ("reset", "naya", "clear", "start over"):
        await clear_session(phone_number=phone_number)
        return (
            "Session reset ho gaya. Fresh start!\n"
            "Poochein: 'aaj ka schedule kya hai'"
        )

    # Step 5: Detect language for AI response style
    language = detect_language(message_text)

    # Step 6: Add user message to Redis session
    # Prefix voice messages so AI knows they were originally spoken
    content_for_session = (
        f"[Voice] {message_text}" if message_type == "voice"
        else message_text
    )
    await add_message_to_session(
        phone_number=phone_number,
        role="user",
        content=content_for_session
    )

    # Step 7: Get conversation history formatted for Groq
    # get_ai_history() strips timestamps — returns only role + content
    ai_history = await get_ai_history(phone_number=phone_number)

    # Step 8: Call AI via bridge
    # active_bridge.process_message() handles the sync/async mismatch internally
    try:
        raw_ai_response = await active_bridge.process_message(
            messages=ai_history,
            db=db,
            tenant_id=identity.tenant_id,
            industry_type=identity.industry_type,
            language=language
        )
    except Exception as e:
        logger.error(
            f"AI processing failed for ****{phone_number[-4:]}: {e}. "
            f"Sending fallback error message."
        )
        return (
            "Maafi kijiye, abhi AI service available nahi hai. "
            "Thodi der baad try karein."
        )

    # Step 9: Format AI response for WhatsApp (strip markdown)
    formatted_response = format_for_whatsapp(raw_ai_response)

    # Step 10: Save AI response to session
    await add_message_to_session(
        phone_number=phone_number,
        role="assistant",
        content=formatted_response
    )

    # Step 11: Log conversation to DB if owner gave consent
    # This builds the Factory GPT training dataset
    if identity.consent_given:
        _log_conversation(
            phone_number=phone_number,
            tenant_id=identity.tenant_id,
            industry_type=identity.industry_type,
            role="user",
            content=content_for_session,
            content_type=message_type,
            language=language,
            db=db
        )
        _log_conversation(
            phone_number=phone_number,
            tenant_id=identity.tenant_id,
            industry_type=identity.industry_type,
            role="assistant",
            content=formatted_response,
            content_type="text",
            language=language,
            db=db
        )

    return formatted_response


# ---------------------------------------------------------------------------
# PRIVATE HELPERS
# ---------------------------------------------------------------------------

def _verify_meta_signature(raw_body: bytes, signature_header: str) -> bool:
    """
    Verify webhook request was signed by Meta using HMAC-SHA256.

    Args:
        raw_body:         Raw request bytes — must be unmodified.
        signature_header: X-Hub-Signature-256 header value from Meta.
                          Format: "sha256=<hex_digest>"

    Returns:
        True if valid, False if missing, malformed, or mismatch.
    """
    if not signature_header or not signature_header.startswith("sha256="):
        logger.warning("Missing or malformed X-Hub-Signature-256 header.")
        return False

    if not settings.WHATSAPP_APP_SECRET:
        logger.error("WHATSAPP_APP_SECRET not set in .env — cannot verify signature.")
        return False

    # Remove "sha256=" prefix to get just the hex digest
    received_signature = signature_header[7:]

    # Compute expected signature using our app secret
    expected_signature = hmac.new(
        key=settings.WHATSAPP_APP_SECRET.encode("utf-8"),
        msg=raw_body,
        digestmod=hashlib.sha256
    ).hexdigest()

    # compare_digest prevents timing attacks — always takes same time
    is_valid = hmac.compare_digest(received_signature, expected_signature)

    if not is_valid:
        logger.warning("Webhook signature mismatch — possible spoofed request.")

    return is_valid


def _extract_message_from_payload(payload: dict) -> dict | None:
    """
    Extract message data from Meta's deeply nested webhook payload.

    Meta payload structure:
      entry[0] -> changes[0] -> value -> messages[0] -> from + type + text.body

    Args:
        payload: Parsed JSON from Meta/Interakt webhook POST.

    Returns:
        Dict with phone_number, text, type — or None if no message found.
    """
    try:
        entry    = payload.get("entry", [{}])[0]
        changes  = entry.get("changes", [{}])[0]
        value    = changes.get("value", {})
        messages = value.get("messages", [])

        if not messages:
            # Normal — Meta sends status updates and read receipts too
            return None

        message      = messages[0]
        message_type = message.get("type", "text")
        phone_number = message.get("from", "")

        if message_type == "text":
            text = message.get("text", {}).get("body", "")
        elif message_type == "audio":
            # Voice note — full transcription added in v5.2
            text = "[Voice message — transcription coming in v5.2]"
            message_type = "voice"
        else:
            # Unsupported type (image, video, document) — ignore
            logger.info(f"Unsupported message type '{message_type}' — ignoring.")
            return None

        if not phone_number or not text:
            return None

        return {"phone_number": phone_number, "text": text, "type": message_type}

    except (IndexError, KeyError, TypeError) as e:
        logger.error(f"Failed to extract message from payload: {e}")
        return None


async def _send_whatsapp_message(phone_number: str, message: str) -> None:
    """
    Send WhatsApp message via Interakt API (or log in mock mode).

    Args:
        phone_number: E.164 format e.g. +919876543210
        message:      Formatted plain text — no markdown.

    Side effects:
        Mock mode: logs to console.
        Production: HTTP POST to Interakt API.
    """
    if settings.WHATSAPP_MOCK_MODE:
        logger.info(
            f"[MOCK SEND] To=****{phone_number[-4:]} "
            f"Message='{message[:100]}{'...' if len(message) > 100 else ''}'"
        )
        return

    if not settings.INTERAKT_API_KEY:
        logger.error("INTERAKT_API_KEY not set — cannot send message.")
        return

    # Interakt expects number without + prefix
    phone_without_plus = phone_number.lstrip("+")

    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                "https://api.interakt.ai/v1/public/message/",
                headers={
                    "Authorization": f"Basic {settings.INTERAKT_API_KEY}",
                    "Content-Type": "application/json"
                },
                json={
                    "countryCode": "91",
                    "phoneNumber": phone_without_plus,
                    "type": "Text",
                    "data": {"message": message}
                },
                timeout=10.0
            )
            if response.status_code != 200:
                logger.error(
                    f"Interakt error {response.status_code} "
                    f"for ****{phone_number[-4:]}: {response.text[:200]}"
                )
    except httpx.TimeoutException:
        logger.error(f"Interakt timeout for ****{phone_number[-4:]}.")
    except Exception as e:
        logger.error(f"Interakt send failed for ****{phone_number[-4:]}: {e}")


def _log_conversation(
    phone_number: str,
    tenant_id: int,
    industry_type: str,
    role: str,
    content: str,
    content_type: str,
    language: str,
    db: Session
) -> None:
    """
    Log one conversation message to whatsapp_conversations table.

    Sync function — uses the same Session as the caller.
    Only called when identity.consent_given is True.
    Builds the Factory GPT training dataset.

    Args:
        phone_number:  E.164 phone number.
        tenant_id:     Multi-tenant isolation.
        industry_type: Cached for training data filtering.
        role:          'user' or 'assistant'.
        content:       Message text.
        content_type:  'text', 'voice', or 'alert'.
        language:      'hindi', 'hinglish', or 'english'.
        db:            Sync SQLAlchemy Session.

    Side effects:
        Inserts one row into whatsapp_conversations.
        Errors are logged but never block the main message flow.
    """
    try:
        log_entry = WhatsAppConversation(
            tenant_id=tenant_id,
            phone_number=phone_number,
            role=role,
            content=content,
            content_type=content_type,
            language=language,
            industry_type=industry_type,
            consent_given=True
        )
        db.add(log_entry)
        db.commit()

    except Exception as e:
        logger.error(
            f"Conversation log failed for ****{phone_number[-4:]}: {e}. "
            f"Message was sent. Only logging failed."
        )
