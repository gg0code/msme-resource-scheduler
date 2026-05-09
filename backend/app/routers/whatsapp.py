"""
FILE:    whatsapp.py
PATH:    backend/app/routers/whatsapp.py
PURPOSE: FastAPI router — the entry point for all WhatsApp messages.

         Eight endpoints:
           GET  /api/v1/whatsapp/webhook              — Meta webhook verification handshake.
           POST /api/v1/whatsapp/webhook              — Receives inbound WhatsApp messages.
           POST /api/v1/whatsapp/simulate             — Dev only. Simulates full pipeline.
           POST /api/v1/whatsapp/link-phone           — Link a phone number to a tenant.
           GET  /api/v1/whatsapp/linked-phones        — List linked phones for a tenant.
           PATCH /api/v1/whatsapp/linked-phones/{id}/deactivate — Deactivate a linked phone.
           POST /api/v1/whatsapp/trigger-dev-alerts   — Dev only. Fire alerts on demand.
           POST /api/v1/whatsapp/simulate-voice       — Dev only. Test voice transcription.

         Message flow for POST /webhook:
           1.  Verify Meta signature (security)
           2.  Extract message from payload
           2b. If audio message — transcribe via Groq Whisper (v5.2)
           3.  Resolve phone to tenant identity
           3a. Check for in-flight v6.3.15 (revised) confirmation batch
               — runs BEFORE the v5.12 pending-action machine so a HAAN
               reply to a confirmation message is never swallowed by an
               unrelated pending action. Gated by the 48h
               INFLIGHT_REPLY_WINDOW_HOURS pending-state filter (Q4
               routing-precedence rule).
           4.  Check for pending confirmation (write action state machine)
           5.  Handle reset commands
           5b. Detect language (v5.12: moved before intent to localise blocked replies)
           5c. Manager check-in window 7-9am IST → handle_manager_checkin_reply() (v5.15)
           6.  Detect write intent — with role gate (v5.12)
           6a. If role blocked — send localised blocked reply, return immediately
           6b. If intent found — store pending action, return confirmation prompt
           6c. If no intent — add user message to session, continue to AI
           7.  Get conversation history for AI
           8.  Call AI via whatsapp_bridge.active_bridge
           9.  Format response for WhatsApp (strip markdown)
           10. Add AI response to session
           11. Log conversation if consent given

BRANCH:  v5-whatsapp
VERSION: v5.15
CREATED: 2026-03
UPDATED: 2026-04-10 — v5.15: Manager check-in window routing (step 5c).
                      Messages from phone_role='manager' between 7-9am IST
                      routed to handle_manager_checkin_reply() in
                      whatsapp_checkin.py. Outside window: normal AI pipeline.
                      trigger-dev-alerts extended with 'checkin' and
                      'owner_briefing' alert_type values.
         2026-04-08 — v5.12: Role limiting + language support.
                      detect_language() moved to step 5b (before intent).
                      detect_write_intent() now receives phone_role + language.
                      Role gate blocks manager/operator actions before AI.
                      Blocked reply localised to detected language.
         2026-03-30 — v5.2: Voice note support via Groq Whisper.

DEPENDENCIES:
  app/services/whatsapp_send.py      — _send_whatsapp_message() (shared sender)
  app/services/whatsapp_identity.py  — resolve_identity(), record_consent()
  app/services/whatsapp_session.py   — add_message_to_session(), get_ai_history()
  app/services/whatsapp_bridge.py    — active_bridge.process_message()
  app/services/whatsapp_formatter.py — format_for_whatsapp(), detect_language()
  app/services/whatsapp_actions.py   — confirmation state machine
  app/services/whatsapp_intent.py    — detect_write_intent() (v5.12: 4-tuple return)
  app/services/whatsapp_whisper.py   — transcribe_voice_note() (v5.2)
  app/services/whatsapp_checkin.py   — handle_manager_checkin_reply() (v5.15)
  app/services/whatsapp_alerts.py    — CHECKIN_WINDOW_* constants (v5.15)
  app/models/whatsapp.py             — WhatsAppConversation, PhoneTenantMap
  app/database.py                    — get_db() dependency, SessionLocal
  app/config.py                      — settings
  app/core/dependencies.py           — get_current_user()

NOTES:
  - Always return 200 OK to Meta even on errors. Meta retries on non-200.
  - Signature verification must happen before any business logic.
  - /simulate and /simulate-voice only available in WHATSAPP_MOCK_MODE.
  - v5.12: detect_write_intent() now returns a 4-tuple. Always unpack all 4 values.
"""

import hashlib
import hmac
import json
import logging

from fastapi import APIRouter, Depends, File, HTTPException, Request, Query, UploadFile
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db, SessionLocal
from app.services.whatsapp_send import _send_whatsapp_message
from app.services.whatsapp_identity import resolve_identity, record_consent
from app.services.onboarding_message import resume_pending_after_consent
from app.services.whatsapp_session import add_message_to_session, get_ai_history, clear_session
from app.services.whatsapp_bridge import active_bridge
from app.services.whatsapp_formatter import format_for_whatsapp, detect_language
# v6.3.14 — module-level import so Base.metadata picks up
# ExtractionCandidate at app startup (the import chain reaches the
# model file). The hook itself runs inside _process_inbound_message.
from app.services.extraction import schedule_extraction as _schedule_extraction
from app.services.whatsapp_actions import (
    is_confirmation, is_cancellation,
    get_pending_action, execute_action,
    clear_pending_action, build_confirmation_prompt,
    ActionType, store_pending_action
)
from app.services.whatsapp_intent import (
    detect_write_intent,
    detect_briefing_request_intent,
    PHONE_TOP_TIER_ROLES,
)
from app.services.whatsapp_whisper import transcribe_voice_note, transcribe_audio_bytes
from app.models.whatsapp import WhatsAppConversation, PhoneTenantMap
from app.core.dependencies import get_current_user

# ---------------------------------------------------------------------------
# Module logger
# ---------------------------------------------------------------------------
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Router
# ---------------------------------------------------------------------------
router = APIRouter(
    prefix="/api/v1/whatsapp",
    tags=["whatsapp"]
)

# ---------------------------------------------------------------------------
# CONSTANTS
# ---------------------------------------------------------------------------

CONSENT_TRIGGER = "haan"

WELCOME_UNREGISTERED = (
    "Namaste! Ye number ZetaOps mein registered nahi hai.\n"
    "Apna number link karne ke liye ZetaOps web app mein "
    "jaayein aur WhatsApp Link karein."
)

CONSENT_REQUEST = (
    "ZetaOps Copilot mein aapka swagat hai!\n\n"
    "Behtar service ke liye, kya hum aapki conversations "
    "improve karne ke liye use kar sakte hain?\n\n"
    "Reply karein:\n"
    "HAAN — agree karne ke liye\n"
    "NAHI — decline karne ke liye\n\n"
    "Aap bina consent ke bhi ZetaOps use kar sakte hain."
)

# Sent when voice transcription fails — asks owner to type instead
VOICE_TRANSCRIPTION_FAILED = (
    "Voice note samajh nahi aaya. "
    "Kripya type karke message bhejein."
)

VALID_PHONE_ROLES = {"owner", "manager", "operator"}


# ---------------------------------------------------------------------------
# v6.3.5: bot-number lookup for the post-signup landing page
# ---------------------------------------------------------------------------

@router.get("/bot-number")
def get_bot_number() -> dict:
    """
    GET /api/v1/whatsapp/bot-number - returns the WhatsApp bot's E.164 digits
    for the post-signup landing's "Open WhatsApp" deep-link.

    Called by: frontend/src/pages/PostSignupLanding.tsx on mount.
    Calls into: app.config.settings.WHATSAPP_BOT_NUMBER.

    Returns: {"bot_number": "919876543210" | ""} - empty string when not
             configured. The frontend renders the CTA disabled in that case
             instead of producing a broken wa.me link.

    No auth: the value is non-sensitive (it is by definition the public
    address users contact ZetaOps on) and the landing page is the very
    first authenticated screen after register, so making this open also
    keeps the page snappy.
    """
    return {"bot_number": settings.WHATSAPP_BOT_NUMBER or ""}


# ---------------------------------------------------------------------------
# PYDANTIC MODELS
# ---------------------------------------------------------------------------

class SimulateRequest(BaseModel):
    """Request body for the /simulate endpoint."""
    phone: str
    message: str
    type: str = "text"


class SimulateResponse(BaseModel):
    """Response from the /simulate endpoint."""
    response: str
    tenant_id: int | None = None
    language: str = "english"
    formatted: bool = True
    transcribed: bool = False   # v5.2 — True if message was voice-transcribed


class LinkPhoneRequest(BaseModel):
    """Request body for POST /link-phone."""
    phone_number:  str
    display_name:  str
    phone_role:    str = "owner"
    consent_given: bool = False


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
# ENDPOINT 1 — GET /webhook
# ---------------------------------------------------------------------------

@router.get("/webhook")
async def verify_webhook(
    hub_mode: str = Query(None, alias="hub.mode"),
    hub_verify_token: str = Query(None, alias="hub.verify_token"),
    hub_challenge: str = Query(None, alias="hub.challenge")
):
    """
    Handle Meta's webhook verification handshake.
    Called once by Meta when registering the webhook URL.

    Args:
        hub_mode:         Always 'subscribe' from Meta.
        hub_verify_token: Must match WHATSAPP_VERIFY_TOKEN in .env.
        hub_challenge:    Random string to echo back.

    Returns:
        hub_challenge integer if verification passes.
        403 if token does not match.
    """
    if hub_mode == "subscribe" and hub_verify_token == settings.WHATSAPP_VERIFY_TOKEN:
        logger.info("Meta webhook verification successful.")
        return int(hub_challenge)

    logger.warning(
        f"Meta webhook verification failed. "
        f"Received: '{hub_verify_token}', Expected: '{settings.WHATSAPP_VERIFY_TOKEN}'."
    )
    raise HTTPException(status_code=403, detail="Webhook verification failed.")


# ---------------------------------------------------------------------------
# ENDPOINT 2 — POST /webhook
# ---------------------------------------------------------------------------

@router.post("/webhook")
async def receive_webhook(request: Request, db: Session = Depends(get_db)):
    """
    Receive and process inbound WhatsApp messages from Meta.

    Always returns 200 OK — Meta retries on non-200 causing duplicates.
    v5.2: Audio messages are transcribed via Groq Whisper before processing.

    Args:
        request: Raw FastAPI request for signature verification.
        db:      Sync session from dependency injection.

    Returns:
        {"status": "ok"} always.
    """
    raw_body = await request.body()

    if not settings.WHATSAPP_MOCK_MODE:
        signature_valid = await _verify_meta_signature(
            raw_body=raw_body,
            signature_header=request.headers.get("X-Hub-Signature-256", "")
        )
        if not signature_valid:
            logger.warning("Webhook signature verification failed — rejected.")
            return {"status": "ok"}

    try:
        payload = json.loads(raw_body)
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse webhook payload as JSON: {e}")
        return {"status": "ok"}

    message_event = _extract_message_from_payload(payload)

    if message_event is None:
        logger.debug("Webhook received non-message event — ignoring.")
        return {"status": "ok"}

    phone_number = message_event.get("phone_number")
    message_text = message_event.get("text", "")
    message_type = message_event.get("type", "text")
    media_id     = message_event.get("media_id")

    # v5.2 — Transcribe voice note if audio message
    if message_type == "voice" and media_id:
        access_token = getattr(settings, "WHATSAPP_ACCESS_TOKEN", "")
        transcribed = await transcribe_voice_note(
            media_id=media_id,
            access_token=access_token
        )
        if transcribed:
            message_text = transcribed
            logger.info(
                f"Voice transcribed for ****{phone_number[-4:]}: '{message_text[:50]}'"
            )
        else:
            await _send_whatsapp_message(
                phone_number=phone_number,
                message=VOICE_TRANSCRIPTION_FAILED
            )
            return {"status": "ok"}

    logger.info(
        f"Inbound from ****{phone_number[-4:]} — "
        f"type={message_type}, length={len(message_text)}"
    )

    response_text = await _process_inbound_message(
        phone_number=phone_number,
        message_text=message_text,
        message_type=message_type,
        db=db
    )

    if response_text:
        await _send_whatsapp_message(
            phone_number=phone_number,
            message=response_text
        )

    return {"status": "ok"}


# ---------------------------------------------------------------------------
# ENDPOINT 3 — POST /simulate
# ---------------------------------------------------------------------------

@router.post("/simulate", response_model=SimulateResponse)
async def simulate_message(body: SimulateRequest):
    """
    Simulate an inbound WhatsApp text message without real WhatsApp.
    Dev only. For voice simulation use /simulate-voice.

    Args:
        body: SimulateRequest with phone, message, type fields.

    Returns:
        SimulateResponse with formatted AI response.

    Raises:
        403 if WHATSAPP_MOCK_MODE=False.
    """
    if not settings.WHATSAPP_MOCK_MODE:
        raise HTTPException(
            status_code=403,
            detail="Simulate endpoint is disabled in production."
        )

    logger.info(f"Simulate: phone={body.phone}, message='{body.message[:50]}'")

    language = detect_language(body.message)

    db = SessionLocal()
    try:
        response_text = await _process_inbound_message(
            phone_number=body.phone,
            message_text=body.message,
            message_type=body.type,
            db=db
        )
        identity = await resolve_identity(phone_number=body.phone, db=db)

        return SimulateResponse(
            response=response_text or "No response generated.",
            tenant_id=identity.tenant_id if identity else None,
            language=language,
            formatted=True,
            transcribed=False
        )
    finally:
        db.close()


# ---------------------------------------------------------------------------
# ENDPOINT 4 — POST /link-phone
# ---------------------------------------------------------------------------

@router.post("/link-phone", status_code=201)
def link_phone(
    payload: LinkPhoneRequest,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Link a WhatsApp phone number to the current user's tenant.
    Called by LinkWhatsApp.tsx.

    Args:
        payload:      LinkPhoneRequest with phone_number, display_name,
                      phone_role, consent_given.
        current_user: From JWT — provides tenant_id and user_id.
        db:           Sync SQLAlchemy session.

    Returns:
        201 with LinkedPhoneResponse on success.
        400 if consent not given or role invalid.
        409 if phone already linked to this tenant.

    Side effects:
        Inserts one row into phone_tenant_map.
    """
    if not payload.consent_given:
        raise HTTPException(status_code=400, detail="consent_given must be True.")

    if payload.phone_role not in VALID_PHONE_ROLES:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid phone_role. Must be one of: {', '.join(VALID_PHONE_ROLES)}."
        )

    # v6.3.2: PhoneTenantMap creation is centralised in whatsapp_identity.
    # Same helper drives the signup flow's auto-link path. The helper
    # flushes; this endpoint owns the commit.
    from app.services.whatsapp_identity import (
        link_phone_to_tenant, PhoneAlreadyLinkedError,
    )
    try:
        new_mapping = link_phone_to_tenant(
            db,
            tenant_id=current_user.tenant_id,
            user_id=current_user.id,
            phone_number=payload.phone_number,
            phone_role=payload.phone_role,
            display_name=payload.display_name,
            consent_given=payload.consent_given,
        )
    except PhoneAlreadyLinkedError:
        raise HTTPException(
            status_code=409,
            detail=f"Phone {payload.phone_number} is already linked to this tenant.",
        )
    db.commit()
    db.refresh(new_mapping)

    return LinkedPhoneResponse(
        id=new_mapping.id,
        phone_number=new_mapping.phone_number,
        display_name=new_mapping.display_name,
        phone_role=new_mapping.phone_role,
        is_active=new_mapping.is_active,
        consent_given=new_mapping.consent_given,
    )


# ---------------------------------------------------------------------------
# ENDPOINT 5 — GET /linked-phones
# ---------------------------------------------------------------------------

@router.get("/linked-phones", response_model=LinkedPhonesListResponse)
def list_linked_phones(
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    List all WhatsApp numbers linked to the current user's tenant.
    Called by LinkWhatsApp.tsx on page load.

    Args:
        current_user: From JWT — provides tenant_id.
        db:           Sync SQLAlchemy session.

    Returns:
        LinkedPhonesListResponse with all linked phones.

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
# ENDPOINT 6 — PATCH /linked-phones/{id}/deactivate
# ---------------------------------------------------------------------------

@router.patch("/linked-phones/{phone_id}/deactivate", status_code=200)
def deactivate_linked_phone(
    phone_id: int,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Deactivate a linked WhatsApp number. Row is preserved for audit history.

    Args:
        phone_id:     The phone_tenant_map.id to deactivate.
        current_user: From JWT — provides tenant_id for isolation.
        db:           Sync SQLAlchemy session.

    Returns:
        {"status": "deactivated", "id": phone_id} on success.
        404 if not found or belongs to different tenant.
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
        raise HTTPException(status_code=404, detail=f"Phone id={phone_id} not found.")

    if not phone_record.is_active:
        raise HTTPException(status_code=400, detail=f"Phone id={phone_id} is already inactive.")

    phone_record.is_active = False
    db.commit()

    logger.info(
        f"Phone deactivated: id={phone_id}, ****{phone_record.phone_number[-4:]} "
        f"for tenant_id={current_user.tenant_id}"
    )

    return {"status": "deactivated", "id": phone_id}


# ---------------------------------------------------------------------------
# ENDPOINT 7 — POST /trigger-dev-alerts
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

    Raises:
        403 if WHATSAPP_MOCK_MODE=False.
    """
    if not settings.WHATSAPP_MOCK_MODE:
        raise HTTPException(status_code=403, detail="Dev trigger only available in mock mode.")

    from app.services.whatsapp_alerts import (
        send_morning_briefings,
        check_delayed_jobs,
        check_scheduling_conflicts,
        send_manager_checkin,
        send_owner_briefing_from_checkin,
    )

    if alert_type in ("briefing", "all"):
        await send_morning_briefings()
    if alert_type in ("delays", "all"):
        await check_delayed_jobs()
    if alert_type in ("conflicts", "all"):
        await check_scheduling_conflicts()
    if alert_type in ("checkin", "all"):
        await send_manager_checkin()
    if alert_type in ("owner_briefing", "all"):
        await send_owner_briefing_from_checkin()

    return {"status": "fired", "alert_type": alert_type}


# ---------------------------------------------------------------------------
# ENDPOINT 8 — POST /simulate-voice (v5.2 dev only)
# ---------------------------------------------------------------------------

@router.post("/simulate-voice", response_model=SimulateResponse)
async def simulate_voice_message(
    phone: str,
    audio_file: UploadFile = File(...),
):
    """
    Simulate a WhatsApp voice note by uploading a real audio file.
    Dev only — tests the full voice pipeline end to end.

    Upload an .ogg, .mp3, or .wav file. The file is transcribed via
    Groq Whisper then processed through the normal AI pipeline.

    Args:
        phone:      E.164 phone number e.g. +919876543210
        audio_file: Audio file upload (ogg, mp3, wav, m4a supported)

    Returns:
        SimulateResponse with transcribed=True and AI response.
        The language field contains the detected language plus
        a preview of the transcribed text for verification.

    Raises:
        403 if WHATSAPP_MOCK_MODE=False.
        400 if audio file is empty or transcription fails.
    """
    if not settings.WHATSAPP_MOCK_MODE:
        raise HTTPException(status_code=403, detail="Voice simulate disabled in production.")

    audio_bytes = await audio_file.read()
    if not audio_bytes:
        raise HTTPException(status_code=400, detail="Audio file is empty.")

    logger.info(
        f"Voice simulate: phone={phone}, "
        f"file={audio_file.filename}, size={len(audio_bytes)} bytes"
    )

    # Transcribe via Groq Whisper
    transcribed_text = await transcribe_audio_bytes(
        audio_bytes=audio_bytes,
        filename=audio_file.filename or "voice_note.ogg"
    )

    if not transcribed_text:
        raise HTTPException(
            status_code=400,
            detail="Transcription failed. Check GROQ_API_KEY and audio file validity."
        )

    logger.info(f"Voice transcribed: '{transcribed_text[:100]}'")

    language = detect_language(transcribed_text)

    db = SessionLocal()
    try:
        response_text = await _process_inbound_message(
            phone_number=phone,
            message_text=transcribed_text,
            message_type="voice",
            db=db
        )
        identity = await resolve_identity(phone_number=phone, db=db)

        return SimulateResponse(
            response=response_text or "No response generated.",
            tenant_id=identity.tenant_id if identity else None,
            language=f"{language} | transcribed: {transcribed_text[:80]}",
            formatted=True,
            transcribed=True
        )
    finally:
        db.close()


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
    Core message processing pipeline — shared by all inbound message endpoints.

    Voice messages arrive here already transcribed. They are treated
    identically to text messages except for the [Voice] session prefix
    which tells the AI the message was spoken rather than typed.

    Args:
        phone_number:  E.164 format phone number.
        message_text:  Message text (already transcribed if voice).
        message_type:  'text' or 'voice'.
        db:            Sync Session for DB operations.

    Returns:
        Formatted response string to send back to the owner.
        None if message should be silently ignored.

    Side effects:
        Reads/writes Redis session.
        Calls Groq AI via whatsapp_bridge.
        Writes to whatsapp_conversations if consent given.
        May write to DB via whatsapp_actions on confirmation.
    """

    # Step 1: Resolve identity
    identity = await resolve_identity(phone_number=phone_number, db=db)

    if identity is None:
        logger.info(f"Unregistered phone ****{phone_number[-4:]}.")
        return WELCOME_UNREGISTERED

    # Step 2: First-time consent
    if not identity.consent_given:
        if message_text.lower().strip() == CONSENT_TRIGGER:
            # v6.3.5 fix: record_consent is `async def` but the original call
            # site forgot the await. Without it the coroutine was created and
            # immediately discarded - the consent flip never reached the DB,
            # while the "Shukriya..." success line was returned regardless.
            # Verified during v6.3.5 E2E (test_v6_3_5_onboarding step 9 was
            # failing because consent_given stayed False after HAAN). The
            # pattern matches `await resolve_identity(...)` two lines above.
            await record_consent(phone_number=phone_number, db=db)
            # v6.3.12: if a Day-1 onboarding-complete event was staged
            # before consent landed, deliver it now. No-op when nothing
            # is pending (the common case for HAAN replies that aren't
            # tied to a fresh signup). The reply text below is unchanged
            # because the resumed message is a separate WhatsApp send,
            # not part of this conversation turn.
            await resume_pending_after_consent(
                tenant_id=identity.tenant_id, db=db,
            )
            return (
                "Shukriya! Aapki consent record ho gayi.\n"
                "Ab aap ZetaOps Copilot use kar sakte hain.\n\n"
                "Poochein: 'aaj ka schedule kya hai'"
            )
        else:
            return CONSENT_REQUEST

    # Step 2.5: v6.3.15 (revised) confirmation reply branch.
    # Runs BEFORE Step 3 so a HAAN/NAHI reply to a v6.3.15 confirmation
    # message is never swallowed by an unrelated v5.12 pending action
    # (e.g. owner had a "mark Suresh absent" prompt outstanding from
    # earlier and now answers "haan" intending to confirm a different
    # batch of extracted entities). The pre-fire query checks for any
    # extraction_candidates rows with confirmation_state='pending' for
    # this tenant within the last 48h
    # (promoter.INFLIGHT_REPLY_WINDOW_HOURS).
    #
    # Design choice: when an in-flight batch exists we ALWAYS swallow
    # the message (return the ack here without falling through). Even
    # when the parser falls back to "all deferred", the ack instructs
    # the owner to be more specific — protects the data model from
    # accidental writes via misinterpreted AI responses.
    inflight_db = SessionLocal()
    try:
        from app.services.promotion import (
            apply_confirmation_decisions as _apply_decisions,
            compose_ack as _compose_ack,
            find_inflight_batch_for_tenant as _find_inflight,
            parse_reply as _parse_reply,
        )
        in_flight = _find_inflight(inflight_db, identity.tenant_id)
        if in_flight:
            parsed = _parse_reply(
                message_text,
                in_flight,
                tenant_id=identity.tenant_id,
            )
            # All candidates in a single in-flight batch share the same
            # confirmation_message_id (or all None when the send failed);
            # take the first row's value for the audit payload.
            batch_msg_id = in_flight[0].confirmation_message_id
            _apply_decisions(
                identity.tenant_id,
                inflight_db,
                decisions=parsed.decisions,
                message_id=batch_msg_id,
                decided_by_user_id=identity.user_id,
                parse_strategy=parsed.strategy,
                raw_reply=parsed.raw_reply,
            )
            # Build the owner-facing ack from the (possibly mutated)
            # candidates — re-fetch so confirmation_state reflects the
            # apply step.
            from app.models.extraction_candidate import ExtractionCandidate as _EC
            refreshed = (
                inflight_db.query(_EC)
                .filter(_EC.id.in_([int(c.id) for c in in_flight]))
                .all()
            )
            cand_by_id = {int(c.id): c for c in refreshed}
            ack_text = _compose_ack(
                decisions=parsed.decisions,
                candidates_by_id=cand_by_id,
                industry_type=identity.industry_type,
            )
            logger.info(
                "v6.3.15 confirmation reply applied: phone=****%s "
                "tenant=%s strategy=%s decisions=%s",
                phone_number[-4:],
                identity.tenant_id,
                parsed.strategy,
                parsed.decisions,
            )
            return ack_text
    finally:
        inflight_db.close()

    # Step 3: Pending confirmation state machine
    pending_action = await get_pending_action(phone_number=phone_number)

    if pending_action:
        if is_confirmation(message_text):
            try:
                success, result_message = await execute_action(
                    pending_action=pending_action,
                    db=db,
                    tenant_id=identity.tenant_id
                )
                await clear_pending_action(phone_number=phone_number)
                return result_message
            except Exception as e:
                logger.error(f"execute_action failed for ****{phone_number[-4:]}: {e}.")
                await clear_pending_action(phone_number=phone_number)
                return "Action complete nahi hua. Dobara try karein."

        elif is_cancellation(message_text):
            await clear_pending_action(phone_number=phone_number)
            return "Theek hai, action cancel kar diya. Kuch aur poochein?"

        else:
            reminder = build_confirmation_prompt(
                action_type=ActionType(pending_action["action_type"]),
                action_params=pending_action["action_params"]
            )
            return f"Ek action abhi bhi pending hai:\n\n{reminder}"

    # Step 4: Reset commands
    if message_text.lower().strip() in ("reset", "naya", "clear", "start over"):
        await clear_session(phone_number=phone_number)
        return "Session reset ho gaya. Fresh start!\nPoochein: 'aaj ka schedule kya hai'"

    # Step 5b: Detect language (v5.12: moved before intent so blocked reply
    # is localised to the user's language)
    language = detect_language(message_text)

    # Step 5c: Manager check-in window routing (v5.15)
    # If the sender is a manager and the time is between 7:00am and 9:00am IST,
    # route to the check-in handler instead of the normal AI pipeline.
    # Outside this window, manager messages go through the normal AI pipeline.
    # This keeps the check-in flow time-bounded — managers can still query AI
    # freely for the rest of the day.
    if identity.phone_role == "manager":
        from datetime import datetime as _dt, timezone as tz
        import zoneinfo
        from app.services.whatsapp_alerts import (
            CHECKIN_WINDOW_START_HOUR,
            CHECKIN_WINDOW_END_HOUR,
        )
        from app.services.whatsapp_checkin import handle_manager_checkin_reply

        ist = zoneinfo.ZoneInfo("Asia/Kolkata")
        now_ist = _dt.now(tz.utc).astimezone(ist)
        in_checkin_window = (
            CHECKIN_WINDOW_START_HOUR <= now_ist.hour < CHECKIN_WINDOW_END_HOUR
        )

        if in_checkin_window:
            logger.info(
                "Manager check-in window: routing ****%s to checkin handler.",
                phone_number[-4:],
            )
            checkin_db = SessionLocal()
            try:
                replies = handle_manager_checkin_reply(
                    message=message_text,
                    tenant_id=identity.tenant_id,
                    phone_number=phone_number,
                    lang=language,
                    db=checkin_db,
                )
            finally:
                checkin_db.close()

            # Send all replies in sequence except the last — caller sends last
            for reply in replies[:-1]:
                await _send_whatsapp_message(
                    phone_number=phone_number,
                    message=reply,
                )
            # Return last reply for caller to send via normal flow
            return replies[-1] if replies else None

    # Step 5c: Detect briefing request - on-demand "morning briefing" /
    # "evening briefing" / "aaj ka plan" etc. Top-tier requesters get
    # the briefing as the reply; everyone else gets a polite refusal.
    # Runs BEFORE detect_write_intent so a briefing keyword cannot be
    # accidentally swallowed by the role gate's broader keyword sweep.
    briefing_kind = detect_briefing_request_intent(message_text)
    if briefing_kind is not None:
        from app.services.whatsapp_responses import get_response
        if (identity.phone_role or "owner") not in PHONE_TOP_TIER_ROLES:
            logger.info(
                "Briefing request refused for non-top-tier phone: "
                "phone=****%s role=%s kind=%s",
                phone_number[-4:], identity.phone_role, briefing_kind,
            )
            return get_response("briefing_refused", language)
        # Top-tier: load the User row, dispatch the briefing, return text.
        from app.services.briefings import manual_trigger_briefing
        from app.models.auth import User
        briefing_db = SessionLocal()
        try:
            pmap_user = briefing_db.execute(
                select(PhoneTenantMap).where(
                    PhoneTenantMap.phone_number == phone_number,
                    PhoneTenantMap.is_active == True,  # noqa: E712
                )
            ).scalars().first()
            if pmap_user is None:
                logger.warning(
                    "Briefing request from un-mapped phone: ****%s",
                    phone_number[-4:],
                )
                return get_response("briefing_sent_ack", language)
            user_row = briefing_db.get(User, pmap_user.user_id)
            if user_row is None:
                logger.warning(
                    "Briefing request: phone ****%s mapped to missing user_id=%s",
                    phone_number[-4:], pmap_user.user_id,
                )
                return get_response("briefing_sent_ack", language)
            briefing_text = await manual_trigger_briefing(
                user=user_row,
                kind=briefing_kind,
                db=briefing_db,
            )
            briefing_db.commit()
        finally:
            briefing_db.close()
        logger.info(
            "Briefing manual trigger fired: phone=****%s kind=%s",
            phone_number[-4:], briefing_kind,
        )
        return briefing_text

    # Step 6: Detect write intent - with role gate (v5.12)
    # Returns 4-tuple: (blocked, block_reply, action_type, action_params)
    # blocked=True means role gate fired - send reply and return immediately.
    # Never pass blocked messages to AI.
    intent_db = SessionLocal()
    try:
        blocked, block_reply, action_type, action_params = detect_write_intent(
            user_message=message_text,
            tenant_id=identity.tenant_id,
            db=intent_db,
            phone_role=identity.phone_role or "owner",
            language=language,
        )
    finally:
        intent_db.close()

    # Step 6a: Role blocked — send localised reply, stop processing
    if blocked:
        logger.info(
            "Role gate blocked: phone=****%s role=%s",
            phone_number[-4:],
            identity.phone_role,
        )
        return block_reply

    # Step 6a.5: v6.3.17 owner-bypass direct-write branch.
    # Top-tier (proprietor/owner/factory_manager/co_owner) explicit
    # creation messages — "naya welder hai - Mukesh add kar do",
    # "ek aur skill banao - powder coating", etc. — write directly
    # to employees/machines/skills with source='whatsapp_owner',
    # bypassing the v6.3.14 extractor confidence threshold and the
    # v6.3.15 confirmation cycle. evaluate_and_write enforces a strict
    # role gate (NULL / unknown / mid-tier / operator return None) and
    # a tight heuristic that requires both a creation verb AND an
    # entity name. Anything else returns None and the rest of the
    # pipeline runs unchanged.
    owner_writer_db = SessionLocal()
    try:
        from app.services.owner_entity_writer import evaluate_and_write
        owner_reply = evaluate_and_write(
            message=message_text,
            tenant_id=identity.tenant_id,
            phone_role=identity.phone_role,
            actor_user_id=identity.user_id,
            db=owner_writer_db,
        )
        owner_writer_db.commit()
    except Exception:  # noqa: BLE001 - never raise to the dispatcher
        logger.exception(
            "Owner-bypass write raised: phone=****%s tenant=%s",
            phone_number[-4:], identity.tenant_id,
        )
        owner_writer_db.rollback()
        owner_reply = None
    finally:
        owner_writer_db.close()
    if owner_reply is not None:
        logger.info(
            "Owner-bypass write fired: phone=****%s tenant=%s",
            phone_number[-4:], identity.tenant_id,
        )
        return owner_reply

    if action_type is not None:
        await store_pending_action(
            phone_number=phone_number,
            action_type=action_type,
            action_params=action_params,
        )
        confirmation_prompt = build_confirmation_prompt(
            action_type=action_type,
            action_params=action_params,
        )
        logger.info(f"Write intent '{action_type.value}' for ****{phone_number[-4:]}.")
        return confirmation_prompt

    # Step 6b: Add user message to session
    # Voice messages prefixed with [Voice] so AI knows context
    content_for_session = (
        f"[Voice] {message_text}" if message_type == "voice"
        else message_text
    )

    await add_message_to_session(
        phone_number=phone_number,
        role="user",
        content=content_for_session
    )

    # v6.3.14 — Schedule entity extraction in the background. Per-tenant
    # gated by ENTITY_EXTRACTION_TENANT_IDS; default OFF for everyone.
    # Detached task: never blocks the reply path, never raises. The
    # raw user text is passed (not the [Voice]-prefixed copy used in
    # the AI history) so the extractor sees what the user actually said.
    _schedule_extraction(
        tenant_id=identity.tenant_id,
        industry_type=identity.industry_type,
        message_text=message_text,
        source_message_id=None,
    )

    # Step 7: Get conversation history
    ai_history = await get_ai_history(phone_number=phone_number)

    # Step 8: Call AI
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
        logger.error(f"AI failed for ****{phone_number[-4:]}: {e}.")
        return "Maafi kijiye, abhi AI service available nahi hai. Thodi der baad try karein."
    finally:
        sync_db.close()

    # Step 9: Format for WhatsApp
    formatted_response = format_for_whatsapp(raw_ai_response)

    # Step 9b (v6.3.18): wrap with AI_REPLY_HEADER warm-greeting prefix.
    # render_ai_reply pulls the first token off display_name when present
    # and squashes the resulting double-space when it isn't.
    from app.services.message_templates import render_ai_reply
    first_name = ""
    if identity.display_name:
        first_name = identity.display_name.split()[0]
    formatted_response = render_ai_reply(formatted_response, first_name=first_name)

    # Step 10: Add AI response to session
    await add_message_to_session(
        phone_number=phone_number,
        role="assistant",
        content=formatted_response
    )

    # Step 11: Log if consent given
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

async def _verify_meta_signature(raw_body: bytes, signature_header: str) -> bool:
    """
    Verify that a webhook request was signed by Meta using HMAC-SHA256.

    Args:
        raw_body:         Raw request bytes — must be raw before JSON parsing.
        signature_header: X-Hub-Signature-256 header value from Meta.

    Returns:
        True if signature valid, False otherwise.

    Side effects:
        None — pure verification function.
    """
    if not signature_header or not signature_header.startswith("sha256="):
        logger.warning("Missing or malformed X-Hub-Signature-256 header.")
        return False

    if not settings.WHATSAPP_APP_SECRET:
        logger.error("WHATSAPP_APP_SECRET not set in .env.")
        return False

    received_signature = signature_header[7:]
    expected_signature = hmac.new(
        key=settings.WHATSAPP_APP_SECRET.encode("utf-8"),
        msg=raw_body,
        digestmod=hashlib.sha256
    ).hexdigest()

    is_valid = hmac.compare_digest(received_signature, expected_signature)
    if not is_valid:
        logger.warning("Webhook signature mismatch — possible spoofed request.")

    return is_valid


def _extract_message_from_payload(payload: dict) -> dict | None:
    """
    Extract message data from Meta's nested webhook payload.

    Meta payload: entry -> changes -> value -> messages -> [0]

    v5.2: Also extracts media_id for audio messages so the webhook
    handler can download and transcribe the voice note.

    Args:
        payload: Parsed JSON from Meta webhook.

    Returns:
        Dict with phone_number, text, type, and optionally media_id.
        None if no message found (status updates, read receipts etc.).

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

        # Meta sends `from` as digits-only (wa_id format, e.g. "919845539868"),
        # but resolve_identity() and PhoneTenantMap lookups require E.164
        # ("+919845539868"). Normalize at the entry point so every downstream
        # consumer sees a consistent shape.
        if phone_number and not phone_number.startswith("+"):
            phone_number = "+" + phone_number

        if message_type == "text":
            text     = message.get("text", {}).get("body", "")
            media_id = None

        elif message_type == "audio":
            # v5.2 — extract media_id for Whisper transcription
            # text is empty here — filled after transcription in receive_webhook()
            media_id     = message.get("audio", {}).get("id")
            text         = ""
            message_type = "voice"

        else:
            logger.info(f"Unsupported message type '{message_type}' — ignoring.")
            return None

        if not phone_number:
            return None

        # Text messages must have content — voice messages will be transcribed
        if message_type == "text" and not text:
            return None

        result = {
            "phone_number": phone_number,
            "text":         text,
            "type":         message_type,
        }

        if media_id:
            result["media_id"] = media_id

        return result

    except (IndexError, KeyError, TypeError) as e:
        logger.error(f"Failed to extract message from payload: {e}")
        return None


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
    Log a conversation message to whatsapp_conversations table.
    Only called when consent_given is True — builds Factory GPT training data.

    Args:
        phone_number:  E.164 phone number.
        tenant_id:     For multi-tenant isolation.
        industry_type: Cached for training data filtering.
        role:          'user' or 'assistant'.
        content:       Message text (transcribed text for voice).
        content_type:  'text', 'voice', or 'alert'.
        language:      'hindi', 'hinglish', or 'english'.
        db:            Session for DB write.

    Side effects:
        Inserts one row. Failure logged but never blocks message flow.
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
            consent_given=True
        )
        db.add(conversation_log)
        db.commit()

    except Exception as e:
        logger.error(
            f"Failed to log conversation for ****{phone_number[-4:]}: {e}. "
            f"Message still processed. Only logging failed."
        )
