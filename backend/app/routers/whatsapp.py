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
  app/services/whatsapp_actions.py   — is_confirmation(), is_cancellation(),
                                       get_pending_action(), execute_action(),
                                       clear_pending_action(), build_confirmation_prompt()
  app/models/whatsapp.py             — WhatsAppConversation for logging
  app/database.py                    — get_db() dependency, SessionLocal
  app/config.py                      — settings (WHATSAPP_MOCK_MODE, APP_SECRET etc.)

NOTES:
  - Always return 200 OK to Meta even on errors. Meta retries on non-200
    responses which causes the owner to receive duplicate messages.
  - Signature verification must happen before any business logic.
  - /simulate is only available when WHATSAPP_MOCK_MODE=True.
"""

import hashlib
import hmac
import json
import logging

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session


from app.config import settings
from app.database import get_db, SessionLocal
from app.services.whatsapp_identity import resolve_identity, record_consent
from app.services.whatsapp_session import add_message_to_session, get_ai_history, clear_session
from app.services.whatsapp_bridge import active_bridge
from app.services.whatsapp_formatter import format_for_whatsapp, detect_language
from app.services.whatsapp_actions import (
    is_confirmation, is_cancellation,
    get_pending_action, execute_action,
    clear_pending_action, build_confirmation_prompt,
    ActionType, store_pending_action
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
# CONSENT TRIGGER WORDS
# ---------------------------------------------------------------------------
# When owner sends one of these as their FIRST message, we send consent prompt.
# When owner replies HAAN to consent prompt, we call record_consent().
CONSENT_TRIGGER = "haan"   # Owner replies this to give consent

# First message welcome text — sent to unregistered phones
WELCOME_UNREGISTERED = (
    "Namaste! Ye number ZetaOps mein registered nahi hai.\n"
    "Apna number link karne ke liye ZetaOps web app mein "
    "jaayein aur WhatsApp Link karein."
)

# Consent request — sent on first message from a registered phone
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
# PYDANTIC MODELS — request/response schemas
# ---------------------------------------------------------------------------

class SimulateRequest(BaseModel):
    """
    Request body for the /simulate endpoint.

    Simulates an inbound WhatsApp message without real WhatsApp.
    Used during development (v5.0-v5.4) to test the full pipeline.
    """
    phone: str    # E.164 format e.g. +919876543210
    message: str  # The message text to simulate
    type: str = "text"  # 'text' or 'voice' (voice not implemented until v5.2)


class SimulateResponse(BaseModel):
    """Response from the /simulate endpoint."""
    response: str        # The AI response formatted for WhatsApp
    tenant_id: int | None = None  # Which tenant was resolved
    language: str = "english"     # Detected language of the input
    formatted: bool = True        # Always True — response is always formatted


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
    Handle Meta's webhook verification handshake.

    When you register your webhook URL in the Meta developer dashboard,
    Meta sends a GET request with these three query parameters to verify
    you own the server. We must return hub.challenge if the verify token matches.

    This endpoint is called ONCE during setup — not on every message.

    Args:
        hub_mode:         Always 'subscribe' from Meta.
        hub_verify_token: The token you set in Meta dashboard.
                          Must match WHATSAPP_VERIFY_TOKEN in .env.
        hub_challenge:    A random string Meta wants us to echo back.

    Returns:
        hub_challenge string if verification passes.
        403 if token does not match.
    """

    # Verify the token matches what we set in Meta dashboard
    if hub_mode == "subscribe" and hub_verify_token == settings.WHATSAPP_VERIFY_TOKEN:
        logger.info(
            "Meta webhook verification successful. "
            "Webhook is now registered and active."
        )
        # Return the challenge — Meta confirms webhook ownership
        return int(hub_challenge)

    # Token mismatch — reject the verification attempt
    logger.warning(
        f"Meta webhook verification failed. "
        f"Received token: '{hub_verify_token}', "
        f"Expected: '{settings.WHATSAPP_VERIFY_TOKEN}'. "
        f"Check WHATSAPP_VERIFY_TOKEN in .env matches Meta dashboard setting."
    )
    raise HTTPException(status_code=403, detail="Webhook verification failed.")


# ---------------------------------------------------------------------------
# ENDPOINT 2 — POST /webhook (inbound messages from Meta/Interakt)
# ---------------------------------------------------------------------------

@router.post("/webhook")
async def receive_webhook(request: Request):
    """
    Receive and process inbound WhatsApp messages from Meta via Interakt.

    This is the main endpoint — called every time a factory owner
    sends a WhatsApp message to the ZetaOps number.

    IMPORTANT: Always returns 200 OK even on errors. If we return
    non-200, Meta retries the webhook causing duplicate messages.
    We handle errors gracefully and log them instead of returning errors.

    Args:
        request: The raw FastAPI request — needed for signature verification
                 and body parsing.
        db:      Session from FastAPI dependency injection.

    Returns:
        {"status": "ok"} always — even if processing failed.
    """

    # Step 1: Read raw request body
    # We need the raw bytes for signature verification BEFORE parsing JSON.
    # Once we call request.json(), the raw bytes are consumed.
    raw_body = await request.body()

    # Step 2: Verify Meta signature
    # Skip verification in mock mode — useful for simulator and dev testing
    if not settings.WHATSAPP_MOCK_MODE:
        signature_valid = await _verify_meta_signature(
            raw_body=raw_body,
            signature_header=request.headers.get("X-Hub-Signature-256", "")
        )
        if not signature_valid:
            logger.warning(
                "Webhook signature verification failed — request rejected. "
                "This could be a spoofed request not from Meta/Interakt."
            )
            return {"status": "ok"}  # Return 200 but do nothing

    # Step 3: Parse the payload
    try:
        payload = json.loads(raw_body)
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse webhook payload as JSON: {e}")
        return {"status": "ok"}

    # Step 4: Extract message from Meta's nested payload format
    message_event = _extract_message_from_payload(payload)

    if message_event is None:
        # Meta sends non-message events too (read receipts, status updates).
        logger.debug("Webhook received non-message event — ignoring.")
        return {"status": "ok"}

    phone_number = message_event.get("phone_number")
    message_text = message_event.get("text", "")
    message_type = message_event.get("type", "text")

    logger.info(
        f"Inbound message from ****{phone_number[-4:]} — "
        f"type={message_type}, length={len(message_text)}"
    )

    # Step 5: Process the message
    response_text = await _process_inbound_message(
        phone_number=phone_number,
        message_text=message_text,
        message_type=message_type,
        db=db
    )

    # Step 6: Send response back to owner
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

    Development only — disabled when WHATSAPP_MOCK_MODE=False.
    Used to test the full pipeline (identity to session to AI to formatter)
    without Interakt subscription or real phone number.

    Args:
        body: SimulateRequest with phone, message, and type fields.
        db:   Session from FastAPI dependency injection.

    Returns:
        SimulateResponse with the formatted AI response and metadata.

    Raises:
        403 if WHATSAPP_MOCK_MODE=False (disabled in production).
    """

    # Block this endpoint in production — it bypasses all security checks
    if not settings.WHATSAPP_MOCK_MODE:
        raise HTTPException(
            status_code=403,
            detail=(
                "Simulate endpoint is disabled in production. "
                "Set WHATSAPP_MOCK_MODE=True in .env to enable."
            )
        )

    logger.info(
        f"Simulate request: phone={body.phone}, "
        f"message='{body.message[:50]}', type={body.type}"
    )

    # Detect language before processing
    language = detect_language(body.message)

    db = SessionLocal()
    try:
        # Process through the same pipeline as real messages
        response_text = await _process_inbound_message(
            phone_number=body.phone,
            message_text=body.message,
            message_type=body.type,
            db=db
        )

        # Resolve identity to get tenant_id for the response metadata
        identity = await resolve_identity(
            phone_number=body.phone,
            db=db
        )

        return SimulateResponse(
            response=response_text or "No response generated.",
            tenant_id=identity.tenant_id if identity else None,
            language=language,
            formatted=True
        )

    finally:
        # Always close the session — even if an error occurred
        db.close()

    # Resolve identity to get tenant_id for the response
    identity =  resolve_identity(
        phone_number=body.phone,
        db=db
    )

    return SimulateResponse(
        response=response_text or "No response generated.",
        tenant_id=identity.tenant_id if identity else None,
        language=language,
        formatted=True
    )


# ---------------------------------------------------------------------------
# CORE PROCESSING FUNCTION
# ---------------------------------------------------------------------------

async def _process_inbound_message(
    phone_number: str,
    message_text: str,
    message_type: str,
    db: Session
) -> str | None:
    """
    Core message processing pipeline — shared by webhook and simulate endpoints.

    Handles the complete flow from raw message to formatted response:
    identity resolution, consent check, confirmation state machine,
    session management, AI call, formatting, conversation logging.

    Args:
        phone_number:  E.164 format phone number.
        message_text:  The message text (already transcribed if voice).
        message_type:  'text' or 'voice'.
        db:            Session for DB operations.

    Returns:
        Formatted response string to send back to the owner.
        None if message should be silently ignored.

    Side effects:
        Reads/writes Redis session.
        Calls Groq AI via whatsapp_bridge.
        Writes to whatsapp_conversations table if consent given.
        May write to main DB tables via whatsapp_actions (on confirmation).
    """

    # Step 1: Resolve identity
    identity = await resolve_identity(
        phone_number=phone_number,
        db=db
    )

    # Phone not registered — send instructions and stop
    if identity is None:
        logger.info(
            f"Unregistered phone ****{phone_number[-4:]} — "
            f"sending registration instructions."
        )
        return WELCOME_UNREGISTERED

    # Step 2: Handle first-time consent
    if not identity.consent_given:
        if message_text.lower().strip() == CONSENT_TRIGGER:
            record_consent(phone_number=phone_number, db=db)
            return (
                "Shukriya! Aapki consent record ho gayi.\n"
                "Ab aap ZetaOps Copilot use kar sakte hain.\n\n"
                "Poochein: 'aaj ka schedule kya hai'"
            )
        else:
            return CONSENT_REQUEST

    # Step 3: Check for pending confirmation state machine
    pending_action = await get_pending_action(phone_number=phone_number)

    if pending_action:
        if is_confirmation(message_text):
            sync_db = SessionLocal()
            try:
                success, result_message = await execute_action(
                    pending_action=pending_action,
                    db=db,
                    tenant_id=identity.tenant_id
                )
                await clear_pending_action(phone_number=phone_number)
                return result_message
            finally:
                sync_db.close()

        elif is_cancellation(message_text):
            await clear_pending_action(phone_number=phone_number)
            return "Theek hai, action cancel kar diya. Kuch aur poochein?"

        else:
            # Owner sent something else while action pending — remind them
            confirmation_reminder = build_confirmation_prompt(
                action_type=ActionType(pending_action["action_type"]),
                action_params=pending_action["action_params"]
            )
            return (
                f"Ek action abhi bhi pending hai:\n\n"
                f"{confirmation_reminder}"
            )

    # Step 4: Handle reset commands
    if message_text.lower().strip() in ("reset", "naya", "clear", "start over"):
        await clear_session(phone_number=phone_number)
        return (
            "Session reset ho gaya. Fresh start!\n"
            "Poochein: 'aaj ka schedule kya hai'"
        )

    # Step 5: Detect language
    language = detect_language(message_text)

    # Step 6: Add user message to session
    # Prefix voice messages so AI knows they were spoken not typed
    content_for_session = (
        f"[Voice] {message_text}" if message_type == "voice"
        else message_text
    )

    await add_message_to_session(
        phone_number=phone_number,
        role="user",
        content=content_for_session
    )

    # Step 7: Get conversation history for AI
    # get_ai_history() returns history stripped of timestamps — Groq-safe format
    ai_history = await get_ai_history(phone_number=phone_number)

    # Step 8: Call AI via bridge
    # Need a sync db session for run_ai_chat() which uses sync SQLAlchemy
    sync_db = SessionLocal()
    try:
        raw_ai_response = await active_bridge.process_message(
            messages=ai_history,
            db=sync_db,
            tenant_id=identity.tenant_id,
            industry_type=identity.industry_type,
            language=language
        )
    except Exception as e:
        logger.error(
            f"AI processing failed for ****{phone_number[-4:]}: {e}. "
            f"Sending error message to owner."
        )
        return (
            "Maafi kijiye, abhi AI service available nahi hai. "
            "Thodi der baad try karein."
        )
    finally:
        sync_db.close()

    # Step 9: Format response for WhatsApp
    formatted_response = format_for_whatsapp(raw_ai_response)

    # Step 10: Add AI response to session
    await add_message_to_session(
        phone_number=phone_number,
        role="assistant",
        content=formatted_response
    )

    # Step 11: Log conversation if consent given
    if identity.consent_given:
        await _log_conversation(
            phone_number=phone_number,
            tenant_id=identity.tenant_id,
            industry_type=identity.industry_type,
            role="user",
            content=content_for_session,
            content_type=message_type,
            language=language,
            db=db
        )
        await _log_conversation(
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

async def _verify_meta_signature(
    raw_body: bytes,
    signature_header: str
) -> bool:
    """
    Verify that an inbound webhook request was signed by Meta.

    Meta signs every webhook with HMAC-SHA256 using your app secret.
    We recompute the signature and compare — if they match, the request
    is genuinely from Meta/Interakt.

    Args:
        raw_body:         Raw request body bytes — must be raw, not parsed.
        signature_header: The X-Hub-Signature-256 header value from Meta.
                          Format: "sha256=<hex_digest>"

    Returns:
        True if signature is valid.
        False if signature is missing, malformed, or does not match.

    Side effects:
        None — pure verification function.
    """

    if not signature_header or not signature_header.startswith("sha256="):
        logger.warning(
            "Missing or malformed X-Hub-Signature-256 header. "
            "Request rejected. Check Interakt webhook configuration."
        )
        return False

    if not settings.WHATSAPP_APP_SECRET:
        logger.error(
            "WHATSAPP_APP_SECRET not set in .env. "
            "Cannot verify webhook signatures. "
            "Set this value from Meta developer dashboard."
        )
        return False

    # Extract the signature hex string after "sha256="
    received_signature = signature_header[7:]  # Remove "sha256=" prefix

    # Compute expected signature using our app secret
    expected_signature = hmac.new(
        key=settings.WHATSAPP_APP_SECRET.encode("utf-8"),
        msg=raw_body,
        digestmod=hashlib.sha256
    ).hexdigest()

    # Use compare_digest to prevent timing attacks.
    # Regular == comparison leaks timing information that attackers can exploit.
    is_valid = hmac.compare_digest(received_signature, expected_signature)

    if not is_valid:
        logger.warning(
            "Webhook signature mismatch — possible spoofed request. "
            "Check WHATSAPP_APP_SECRET in .env matches Meta app secret."
        )

    return is_valid


def _extract_message_from_payload(payload: dict) -> dict | None:
    """
    Extract the message data from Meta's nested webhook payload format.

    Meta's webhook payload is deeply nested. This function navigates
    the structure and returns a flat dict with just the data we need.

    Meta payload structure (simplified):
      entry -> changes -> value -> messages -> [0] -> from + type + text.body

    Args:
        payload: The parsed JSON payload from Meta/Interakt.

    Returns:
        Dict with phone_number, text, type keys.
        None if no message found (status update, read receipt etc.).

    Side effects:
        None — pure extraction function.
    """

    try:
        # Navigate Meta's nested structure safely using .get() at each level
        entry    = payload.get("entry", [{}])[0]
        changes  = entry.get("changes", [{}])[0]
        value    = changes.get("value", {})
        messages = value.get("messages", [])

        if not messages:
            return None

        message      = messages[0]
        message_type = message.get("type", "text")
        phone_number = message.get("from", "")

        # Extract text based on message type
        if message_type == "text":
            text = message.get("text", {}).get("body", "")
        elif message_type == "audio":
            # Voice note — transcription added in v5.2
            text = "[Voice message — transcription coming in v5.2]"
            message_type = "voice"
        else:
            # Unsupported type (image, video, document)
            logger.info(
                f"Unsupported message type '{message_type}' — ignoring."
            )
            return None

        if not phone_number or not text:
            return None

        return {
            "phone_number": phone_number,
            "text":         text,
            "type":         message_type
        }

    except (IndexError, KeyError, TypeError) as e:
        logger.error(f"Failed to extract message from payload: {e}")
        return None


async def _send_whatsapp_message(
    phone_number: str,
    message: str
) -> None:
    """
    Send a WhatsApp message to a phone number via Interakt API.

    In mock mode: logs the message to console instead of calling Interakt.
    In production: makes HTTP POST to Interakt API.

    Args:
        phone_number: E.164 format phone number e.g. +919876543210
        message:      Plain text message (already formatted, no markdown).

    Side effects:
        Mock mode: writes to log.
        Production: HTTP POST to Interakt API.
    """

    if settings.WHATSAPP_MOCK_MODE:
        logger.info(
            f"[MOCK SEND] To=****{phone_number[-4:]} "
            f"Message='{message[:100]}{'...' if len(message) > 100 else ''}'"
        )
        return

    if not settings.INTERAKT_API_KEY:
        logger.error(
            "INTERAKT_API_KEY not set but WHATSAPP_MOCK_MODE=False. "
            "Cannot send message. Set INTERAKT_API_KEY in .env."
        )
        return

    # Remove + from E.164 — Interakt expects number without +
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
                    f"Interakt API error {response.status_code} "
                    f"for ****{phone_number[-4:]}: {response.text[:200]}"
                )

    except httpx.TimeoutException:
        logger.error(
            f"Interakt API timeout for ****{phone_number[-4:]}. "
            f"Message not delivered."
        )
    except Exception as e:
        logger.error(
            f"Failed to send via Interakt to ****{phone_number[-4:]}: {e}"
        )


async def _log_conversation(
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
    Log a conversation message to the whatsapp_conversations table.

    Only called when identity.consent_given is True.
    This builds the Factory GPT training dataset.

    Args:
        phone_number:  E.164 phone number.
        tenant_id:     For multi-tenant isolation.
        industry_type: Cached for training data filtering.
        role:          'user' or 'assistant'.
        content:       Message text.
        content_type:  'text', 'voice', or 'alert'.
        language:      'hindi', 'hinglish', or 'english'.
        db:            Session for DB write.

    Side effects:
        Inserts one row into whatsapp_conversations table.
        Failure is logged but never blocks the main message flow.
    """
    try:
        conversation_log = WhatsAppConversation(
            tenant_id=tenant_id,
            phone_number=phone_number,
            role=role,
            content=content,
            content_type=content_type,
            language=language,
            industry_type=industry_type,
            consent_given=True  # Only called when consent is True
        )
        db.add(conversation_log)
        db.commit()

    except Exception as e:
        logger.error(
            f"Failed to log conversation for ****{phone_number[-4:]}: {e}. "
            f"Message was still processed and sent. Only logging failed."
        )
