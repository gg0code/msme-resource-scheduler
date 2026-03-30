"""
FILE:    whatsapp.py
PATH:    backend/app/routers/whatsapp.py
PURPOSE: FastAPI router — the entry point for all WhatsApp messages.

         Six endpoints:
           GET  /api/v1/whatsapp/webhook              — Meta webhook verification handshake.
           POST /api/v1/whatsapp/webhook              — Receives inbound WhatsApp messages.
           POST /api/v1/whatsapp/simulate             — Dev only. Simulates full pipeline.
           POST /api/v1/whatsapp/link-phone           — Link a phone number to a tenant.
           GET  /api/v1/whatsapp/linked-phones        — List linked phones for a tenant.
           PATCH /api/v1/whatsapp/linked-phones/{id}/deactivate — Deactivate a linked phone.

         Message flow for POST /webhook:
           1.  Verify Meta signature (security)
           2.  Extract message from payload
           3.  Resolve phone to tenant identity
           4.  Check for pending confirmation (write action state machine)
           5.  Handle reset commands
           6.  Detect write intent in user message (v5.1 — whatsapp_intent.py)
           6b. If intent found — store pending action, return confirmation prompt
           6c. If no intent — add user message to session, continue to AI
           7.  Get conversation history for AI
           8.  Call AI via whatsapp_bridge.active_bridge
           9.  Format response for WhatsApp (strip markdown)
           10. Add AI response to session
           11. Log conversation if consent given

BRANCH:  v5-whatsapp
VERSION: v5.1
CREATED: 2026-03
UPDATED: 2026-03-29 — v5.1: Added intent detection layer (Step 6) between
                      user message and AI call. Write intents (mark absent,
                      maintenance, job status) now trigger confirmation flow
                      instead of going straight to AI.
                      Also added phone linking endpoints (v5.5).

DEPENDENCIES:
  app/services/whatsapp_identity.py  — resolve_identity(), record_consent()
  app/services/whatsapp_session.py   — add_message_to_session(), get_ai_history()
  app/services/whatsapp_bridge.py    — active_bridge.process_message()
  app/services/whatsapp_formatter.py — format_for_whatsapp(), detect_language()
  app/services/whatsapp_actions.py   — is_confirmation(), is_cancellation(),
                                       get_pending_action(), execute_action(),
                                       clear_pending_action(), build_confirmation_prompt()
  app/services/whatsapp_intent.py    — detect_write_intent() (v5.1)
  app/models/whatsapp.py             — WhatsAppConversation, PhoneTenantMap
  app/database.py                    — get_db() dependency, SessionLocal
  app/config.py                      — settings (WHATSAPP_MOCK_MODE, APP_SECRET etc.)
  app/core/dependencies.py           — get_current_user() for auth on linking endpoints

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
from app.services.whatsapp_intent import detect_write_intent
from app.models.whatsapp import WhatsAppConversation, PhoneTenantMap
from app.core.dependencies import get_current_user

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

# Valid roles — must match phone_tenant_map.phone_role constraint
VALID_PHONE_ROLES = {"owner", "manager", "operator"}


# ---------------------------------------------------------------------------
# PYDANTIC MODELS — request/response schemas
# ---------------------------------------------------------------------------

class SimulateRequest(BaseModel):
    """
    Request body for the /simulate endpoint.

    Simulates an inbound WhatsApp message without real WhatsApp.
    Used during development (v5.0-v5.4) to test the full pipeline.
    """
    phone: str       # E.164 format e.g. +919876543210
    message: str     # The message text to simulate
    type: str = "text"  # 'text' or 'voice' (voice not implemented until v5.2)


class SimulateResponse(BaseModel):
    """Response from the /simulate endpoint."""
    response: str             # The AI response formatted for WhatsApp
    tenant_id: int | None = None  # Which tenant was resolved
    language: str = "english"     # Detected language of the input
    formatted: bool = True        # Always True — response is always formatted


class LinkPhoneRequest(BaseModel):
    """
    Request body for POST /link-phone.
    All fields map directly to phone_tenant_map columns.
    """
    phone_number:  str              # E.164 format e.g. +919876543210
    display_name:  str              # Human name shown in AI responses
    phone_role:    str = "owner"    # 'owner' | 'manager' | 'operator'
    consent_given: bool = False     # Must be True to proceed


class LinkedPhoneResponse(BaseModel):
    """Single linked phone record returned to the frontend."""
    id:            int
    phone_number:  str
    display_name:  str
    phone_role:    str
    is_active:     bool
    consent_given: bool

    model_config = {"from_attributes": True}


class LinkedPhonesListResponse(BaseModel):
    """Response wrapper for GET /linked-phones."""
    phones: list[LinkedPhoneResponse]


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

    if hub_mode == "subscribe" and hub_verify_token == settings.WHATSAPP_VERIFY_TOKEN:
        logger.info(
            "Meta webhook verification successful. "
            "Webhook is now registered and active."
        )
        return int(hub_challenge)

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
async def receive_webhook(request: Request, db: Session = Depends(get_db)):
    """
    Receive and process inbound WhatsApp messages from Meta via Interakt.

    IMPORTANT: Always returns 200 OK even on errors. If we return
    non-200, Meta retries the webhook causing duplicate messages.

    Args:
        request: The raw FastAPI request — needed for signature verification.
        db:      Sync session from FastAPI dependency injection.

    Returns:
        {"status": "ok"} always — even if processing failed.
    """

    # Step 1: Read raw body for signature verification BEFORE parsing JSON
    raw_body = await request.body()

    # Step 2: Verify Meta signature — skip in mock mode
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
            return {"status": "ok"}

    # Step 3: Parse the payload
    try:
        payload = json.loads(raw_body)
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse webhook payload as JSON: {e}")
        return {"status": "ok"}

    # Step 4: Extract message from Meta's nested payload format
    message_event = _extract_message_from_payload(payload)

    if message_event is None:
        logger.debug("Webhook received non-message event — ignoring.")
        return {"status": "ok"}

    phone_number = message_event.get("phone_number")
    message_text = message_event.get("text", "")
    message_type = message_event.get("type", "text")

    logger.info(
        f"Inbound message from ****{phone_number[-4:]} — "
        f"type={message_type}, length={len(message_text)}"
    )

    # Step 5: Process the message through the full pipeline
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
    Used to test the full pipeline without Interakt or a real phone.

    Args:
        body: SimulateRequest with phone, message, and type fields.

    Returns:
        SimulateResponse with the formatted AI response and metadata.

    Raises:
        403 if WHATSAPP_MOCK_MODE=False (disabled in production).
    """

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

    language = detect_language(body.message)

    db = SessionLocal()
    try:
        response_text = await _process_inbound_message(
            phone_number=body.phone,
            message_text=body.message,
            message_type=body.type,
            db=db
        )

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
        db.close()


# ---------------------------------------------------------------------------
# ENDPOINT 4 — POST /link-phone (v5.5 — called by LinkWhatsApp.tsx)
# ---------------------------------------------------------------------------

@router.post("/link-phone", status_code=201)
def link_phone(
    payload: LinkPhoneRequest,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Link a WhatsApp phone number to the current user's tenant.

    Called by LinkWhatsApp.tsx when the owner submits the link form.
    Inserts a new row into phone_tenant_map. Returns 409 if already linked.

    Args:
        payload:      LinkPhoneRequest with phone_number, display_name,
                      phone_role, consent_given.
        current_user: Injected from JWT — provides tenant_id and user_id.
        db:           Sync SQLAlchemy session.

    Returns:
        201 with LinkedPhoneResponse on success.
        400 if consent not given or role invalid.
        409 if phone already linked to this tenant.

    Side effects:
        Inserts one row into phone_tenant_map.
    """

    if not payload.consent_given:
        raise HTTPException(
            status_code=400,
            detail="consent_given must be True. User must agree before linking."
        )

    if payload.phone_role not in VALID_PHONE_ROLES:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Invalid phone_role '{payload.phone_role}'. "
                f"Must be one of: {', '.join(VALID_PHONE_ROLES)}."
            )
        )

    existing = (
        db.query(PhoneTenantMap)
        .filter(
            PhoneTenantMap.phone_number == payload.phone_number,
            PhoneTenantMap.tenant_id   == current_user.tenant_id,
        )
        .first()
    )
    if existing:
        raise HTTPException(
            status_code=409,
            detail=f"Phone {payload.phone_number} is already linked to this tenant."
        )

    new_mapping = PhoneTenantMap(
        phone_number=payload.phone_number,
        tenant_id=current_user.tenant_id,
        user_id=current_user.id,
        is_active=True,
        industry_type=current_user.industry_type if hasattr(current_user, "industry_type") else "printing",
        consent_given=payload.consent_given,
        display_name=payload.display_name,
        phone_role=payload.phone_role,
    )
    db.add(new_mapping)
    db.commit()
    db.refresh(new_mapping)

    logger.info(
        f"Phone linked: ****{payload.phone_number[-4:]} "
        f"→ tenant_id={current_user.tenant_id}, role={payload.phone_role}"
    )

    return LinkedPhoneResponse(
        id=new_mapping.id,
        phone_number=new_mapping.phone_number,
        display_name=new_mapping.display_name,
        phone_role=new_mapping.phone_role,
        is_active=new_mapping.is_active,
        consent_given=new_mapping.consent_given,
    )


# ---------------------------------------------------------------------------
# ENDPOINT 5 — GET /linked-phones (v5.5 — called by LinkWhatsApp.tsx)
# ---------------------------------------------------------------------------

@router.get("/linked-phones", response_model=LinkedPhonesListResponse)
def list_linked_phones(
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    List all WhatsApp numbers linked to the current user's tenant.

    Called by LinkWhatsApp.tsx on page load. Returns all records
    (active and inactive) so owners can see the full history.

    Args:
        current_user: Injected from JWT — provides tenant_id.
        db:           Sync SQLAlchemy session.

    Returns:
        LinkedPhonesListResponse with all linked phones for this tenant.

    Side effects:
        None — read-only query.
    """

    phones = (
        db.query(PhoneTenantMap)
        .filter(PhoneTenantMap.tenant_id == current_user.tenant_id)
        .order_by(PhoneTenantMap.id.desc())
        .all()
    )

    return LinkedPhonesListResponse(
        phones=[
            LinkedPhoneResponse(
                id=p.id,
                phone_number=p.phone_number,
                display_name=p.display_name or "",
                phone_role=p.phone_role or "owner",
                is_active=p.is_active,
                consent_given=p.consent_given,
            )
            for p in phones
        ]
    )


# ---------------------------------------------------------------------------
# ENDPOINT 6 — PATCH /linked-phones/{id}/deactivate (v5.5)
# ---------------------------------------------------------------------------

@router.patch("/linked-phones/{phone_id}/deactivate", status_code=200)
def deactivate_linked_phone(
    phone_id: int,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Deactivate a linked WhatsApp number without deleting it.

    Sets is_active=False so the number stops receiving alerts and cannot
    chat — but the row is preserved for audit/history.

    Tenant isolation: owners can only deactivate their own tenant's numbers.

    Args:
        phone_id:     The phone_tenant_map.id to deactivate.
        current_user: Injected from JWT — provides tenant_id for isolation.
        db:           Sync SQLAlchemy session.

    Returns:
        {"status": "deactivated", "id": phone_id} on success.
        404 if phone_id not found or belongs to a different tenant.
        400 if already inactive.

    Side effects:
        Updates is_active=False on the phone_tenant_map row.
    """

    phone_record = (
        db.query(PhoneTenantMap)
        .filter(
            PhoneTenantMap.id        == phone_id,
            PhoneTenantMap.tenant_id == current_user.tenant_id,
        )
        .first()
    )

    if not phone_record:
        raise HTTPException(
            status_code=404,
            detail=(
                f"Phone record id={phone_id} not found for this tenant. "
                f"Check phone_tenant_map table."
            )
        )

    if not phone_record.is_active:
        raise HTTPException(
            status_code=400,
            detail=f"Phone record id={phone_id} is already inactive."
        )

    phone_record.is_active = False
    db.commit()

    logger.info(
        f"Phone deactivated: id={phone_id}, "
        f"****{phone_record.phone_number[-4:]} "
        f"for tenant_id={current_user.tenant_id}"
    )

    return {"status": "deactivated", "id": phone_id}


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

    Handles the complete flow from raw message to formatted response.

    Args:
        phone_number:  E.164 format phone number.
        message_text:  The message text (already transcribed if voice).
        message_type:  'text' or 'voice'.
        db:            Sync Session for DB operations.

    Returns:
        Formatted response string to send back to the owner.
        None if message should be silently ignored.

    Side effects:
        Reads/writes Redis session.
        Calls Groq AI via whatsapp_bridge.
        Writes to whatsapp_conversations table if consent given.
        May write to main DB tables via whatsapp_actions (on confirmation).
    """

    # Step 1: Resolve identity — phone → tenant
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
    # If a write action was proposed in the previous message, handle it first.
    pending_action = await get_pending_action(phone_number=phone_number)

    if pending_action:
        if is_confirmation(message_text):
            # Owner confirmed — execute the DB write
            try:
                success, result_message = await execute_action(
                    pending_action=pending_action,
                    db=db,
                    tenant_id=identity.tenant_id
                )
                await clear_pending_action(phone_number=phone_number)
                return result_message
            except Exception as e:
                logger.error(
                    f"execute_action failed for ****{phone_number[-4:]}: {e}. "
                    f"Clearing pending action to unblock conversation."
                )
                await clear_pending_action(phone_number=phone_number)
                return "Action complete nahi hua. Dobara try karein."

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

    # Step 6: Detect write intent BEFORE calling AI
    # If the user is asking us to change something (mark absent, maintenance etc.)
    # we intercept it here, store a pending action, and ask for confirmation.
    # Only read/query messages go through to the AI in Step 7+.
    intent_db = SessionLocal()
    try:
        action_type, action_params = detect_write_intent(
            user_message=message_text,
            tenant_id=identity.tenant_id,
            db=intent_db,
        )
    finally:
        intent_db.close()

    if action_type is not None:
        # Write intent detected — store pending action and return confirmation prompt
        await store_pending_action(
            phone_number=phone_number,
            action_type=action_type,
            action_params=action_params,
        )
        confirmation_prompt = build_confirmation_prompt(
            action_type=action_type,
            action_params=action_params,
        )
        logger.info(
            f"Write intent '{action_type.value}' detected for "
            f"****{phone_number[-4:]} — sending confirmation prompt."
        )
        return confirmation_prompt

    # Step 6b: No write intent — add user message to session for AI
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
    # Need a fresh sync db session for run_ai_chat() which uses sync SQLAlchemy
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

    # Step 9: Format response for WhatsApp (strip markdown, truncate)
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

    received_signature = signature_header[7:]  # Remove "sha256=" prefix

    expected_signature = hmac.new(
        key=settings.WHATSAPP_APP_SECRET.encode("utf-8"),
        msg=raw_body,
        digestmod=hashlib.sha256
    ).hexdigest()

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
        entry    = payload.get("entry", [{}])[0]
        changes  = entry.get("changes", [{}])[0]
        value    = changes.get("value", {})
        messages = value.get("messages", [])

        if not messages:
            return None

        message      = messages[0]
        message_type = message.get("type", "text")
        phone_number = message.get("from", "")

        if message_type == "text":
            text = message.get("text", {}).get("body", "")
        elif message_type == "audio":
            text = "[Voice message — transcription coming in v5.2]"
            message_type = "voice"
        else:
            logger.info(f"Unsupported message type '{message_type}' — ignoring.")
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
# ---------------------------------------------------------------------------
# ENDPOINT 7 — POST /trigger-dev-alerts (dev only)
# ---------------------------------------------------------------------------

@router.post("/trigger-dev-alerts")
async def trigger_dev_alerts(alert_type: str = "all"):
    """
    Manually trigger alert jobs for development testing.
    Only works when WHATSAPP_MOCK_MODE=True.

    Args:
        alert_type: 'briefing', 'delays', 'conflicts', or 'all'

    Returns:
        {"status": "fired", "alert_type": alert_type}
    """
    if not settings.WHATSAPP_MOCK_MODE:
        raise HTTPException(
            status_code=403,
            detail="Dev trigger only available in mock mode."
        )

    from app.services.whatsapp_alerts import (
        send_morning_briefings,
        check_delayed_jobs,
        check_scheduling_conflicts,
    )

    if alert_type == "briefing" or alert_type == "all":
        await send_morning_briefings()

    if alert_type == "delays" or alert_type == "all":
        await check_delayed_jobs()

    if alert_type == "conflicts" or alert_type == "all":
        await check_scheduling_conflicts()

    return {"status": "fired", "alert_type": alert_type}