# app/services/whatsapp_send_helper.py
# Branch: v5-whatsapp
# Iteration: v6.3.22 — channel-decision send helper.
#
# FILE PURPOSE
# Single entry point for outbound WhatsApp sends that must respect Meta's
# 24-hour conversation window. Given a recipient phone + an internal
# event name + positional args + an already-rendered free-form string,
# the helper:
#   1. reads phone_tenant_map.last_seen_at for (tenant_id, phone).
#   2. if last_seen_at is within 24h, sends free-form via the existing
#      _send_whatsapp_message transport (the "session" path).
#   3. otherwise resolves the Meta HSM template via resolve_template()
#      and sends a template payload (the "template" path).
#   4. writes one audit event per outcome so the events table tells the
#      story of every send attempt.
#
# Dispatchers continue to compute their own field values and rendered
# free-form strings. They pass BOTH artefacts to this helper; the helper
# picks the wire format.
#
# WHO CALLS THIS FILE (v6.3.22 cutover)
# - app/services/whatsapp_alerts._send_alert (optional template path)
# - app/services/consolidated_briefing.{_dispatch_one, dispatch_delay_alert,
#   dispatch_conflict_alert}
# - app/services/team_invite_whatsapp.send_invite_welcome (sync->async bridge)
#
# WHAT THIS FILE CALLS
# - app/config.settings (WHATSAPP_MOCK_MODE, WHATSAPP_ACCESS_TOKEN,
#   WHATSAPP_PHONE_NUMBER_ID)
# - app/models.event.Event (audit row writes)
# - app/models.whatsapp.PhoneTenantMap (last_seen_at read)
# - app/services.whatsapp_templates.resolve_template, ResolvedTemplate,
#   UnknownEventError, ArgCountMismatchError
# - app/services.whatsapp_meta_templates.META_TEMPLATES (HEADER/BODY split
#   for the Meta template POST body)
# - app/services.whatsapp_send._send_whatsapp_message (free-form path)
# - httpx (real-mode template POST)
#
# KEY DESIGN DECISIONS
# - last_seen_at is reused as the inbound-window source. v6.3.22 audit
#   confirmed it is written exclusively by resolve_identity() in
#   whatsapp_identity.py from inbound paths — never on outbound sends.
#   That eliminates the doc's proposed migration 035 + last_inbound_at
#   column.
# - The helper never raises on transport failure. It catches every
#   exception, writes the appropriate audit event, and returns a
#   SendOutcome with success=False. Dispatchers can stop wrapping send
#   calls in try/except for transport errors.
# - Mock mode emits `[MOCK TEMPLATE] ...` lines structurally similar to
#   the existing `[MOCK SEND]` / `[MOCK ALERT]` breadcrumbs so log-grep
#   tests across the codebase keep working.
# - All five new audit event types are dotted strings under the
#   "whatsapp." namespace (whatsapp.freeform_sent, whatsapp.template_sent,
#   whatsapp.template_param_mismatch, whatsapp.window_expired_no_template,
#   whatsapp.template_rejected). The events table String(50) column has
#   plenty of room.
# - HEADER/BODY split for the real-mode Meta template POST is computed
#   from META_TEMPLATES["components"]: parameters in `args` are sliced
#   by the HEADER placeholder count, with the remainder forming the BODY
#   parameters. This avoids duplicating Meta's component structure here.

from __future__ import annotations

import logging
import re
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.models.event import Event
from app.models.whatsapp import PhoneTenantMap
from app.services.whatsapp_meta_templates import META_TEMPLATES
from app.services.whatsapp_send import _send_whatsapp_message
from app.services.whatsapp_templates import (
    ArgCountMismatchError,
    ResolvedTemplate,
    UnknownEventError,
    resolve_template,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Meta's free-form session window. Any send outside this window must go
# through an approved HSM template; free-form text is rejected upstream.
WINDOW_24H = timedelta(hours=24)

# Audit event_type strings. Kept short so they fit comfortably under the
# events.event_type String(50) cap.
EVENT_FREEFORM_SENT             = "whatsapp.freeform_sent"
EVENT_TEMPLATE_SENT             = "whatsapp.template_sent"
EVENT_TEMPLATE_PARAM_MISMATCH   = "whatsapp.template_param_mismatch"
EVENT_WINDOW_EXPIRED_NO_TEMPLATE = "whatsapp.window_expired_no_template"
EVENT_TEMPLATE_REJECTED         = "whatsapp.template_rejected"


# ---------------------------------------------------------------------------
# Public dataclass
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class SendOutcome:
    """Result of send_with_window_decision.

    path:           Which branch executed.
                      'freeform'              — in-window, free-form text sent
                      'template'              — out-of-window, template sent
                      'skipped_unknown_event' — event not in EVENT_ROUTING
                      'skipped_param_mismatch' — args count wrong for template
                      'failed'                — wire-level error
    success:        True iff the message reached Meta (or the mock log)
                    without error.
    wamid:          WhatsApp message id (real) or synthetic id (mock),
                    None on skip/failure.
    used_fallback:  True iff the template path fired and language fell
                    back from hi to en_US. False otherwise.
    error:          Short error code for failure outcomes; None on success.
    """
    path: str
    success: bool
    wamid: Optional[str]
    used_fallback: bool
    error: Optional[str]


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _read_last_seen_at(
    db: Session,
    *,
    tenant_id: int,
    phone_e164: str,
) -> Optional[datetime]:
    """Look up last_seen_at for (tenant_id, phone_e164).

    Returns None if no PhoneTenantMap row exists, the row is inactive,
    or the column is NULL. NULL is treated as "never messaged us" —
    callers should pick the template path.
    """
    row = db.execute(
        select(PhoneTenantMap.last_seen_at).where(
            PhoneTenantMap.tenant_id == tenant_id,
            PhoneTenantMap.phone_number == phone_e164,
            PhoneTenantMap.is_active == True,  # noqa: E712 — SQLAlchemy needs ==
        )
    ).first()
    if row is None:
        return None
    return row[0]


def _is_within_window(last_seen_at: Optional[datetime], now: datetime) -> bool:
    """Return True iff last_seen_at is within WINDOW_24H of now.

    NULL last_seen_at is False (never messaged us — outside window).
    Both timestamps are tz-aware in production; tests may pass naive
    UTC datetimes, which we normalise here.
    """
    if last_seen_at is None:
        return False
    if last_seen_at.tzinfo is None:
        last_seen_at = last_seen_at.replace(tzinfo=timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    return (now - last_seen_at) < WINDOW_24H


def _write_event(
    db: Session,
    *,
    tenant_id: int,
    event_type: str,
    payload: dict,
    actor_user_id: Optional[int] = None,
) -> None:
    """Stage one Event row. Caller commits.

    All v6.3.22 helper events use entity_type='whatsapp_send' and
    source='system' (the dispatcher tick is the originator). The
    dispatcher's own per-tenant events (push.morning_sent etc) are
    written separately by the caller — those describe the dispatcher
    outcome at the tenant level, while these describe the per-recipient
    channel decision.
    """
    db.add(Event(
        tenant_id=tenant_id,
        event_type=event_type,
        entity_type="whatsapp_send",
        source="system",
        actor_user_id=actor_user_id,
        payload=payload,
    ))
    # Flush so the row is visible to same-session queries in tests
    # (TestingSessionLocal is autoflush=False). Caller still owns commit.
    db.flush()


def _split_meta_params(
    meta_name: str,
    meta_language: str,
    meta_params: list[str],
) -> tuple[list[str], list[str]]:
    """Split a flat meta_params list into (header_params, body_params).

    The HEADER component count is read from META_TEMPLATES — every
    {{n}} placeholder inside the HEADER component contributes one
    param slot, in order. Everything else goes to BODY.

    If the template has no HEADER component, header_params is [] and
    body_params is the full input list.
    """
    entry = META_TEMPLATES.get((meta_name, meta_language))
    if entry is None:
        return [], list(meta_params)
    header_count = 0
    for component in entry["components"]:
        if (component.get("type") or "").upper() == "HEADER":
            header_count += len(re.findall(r"\{\{\d+\}\}", component.get("text") or ""))
    if header_count == 0:
        return [], list(meta_params)
    return list(meta_params[:header_count]), list(meta_params[header_count:])


async def _post_template_to_meta(
    phone_e164: str,
    resolved: ResolvedTemplate,
) -> tuple[Optional[str], Optional[str]]:
    """POST a Meta template message and return (wamid, error).

    Mock mode returns (synthetic_wamid, None) without an HTTP call and
    emits the `[MOCK TEMPLATE]` breadcrumb. Real mode builds the
    components array, POSTs to graph.facebook.com, and returns the
    Meta wamid or the error body.

    Symmetrical to _send_whatsapp_message in whatsapp_send.py — never
    raises; transport errors come back as the error string.
    """
    if settings.WHATSAPP_MOCK_MODE:
        synthetic_id = f"mock_wamid_{uuid.uuid4().hex[:16]}"
        logger.info(
            f"[MOCK TEMPLATE] To=****{phone_e164[-4:]} "
            f"event_template={resolved.meta_name} "
            f"language={resolved.meta_language} "
            f"params={resolved.meta_params} "
            f"wamid={synthetic_id}"
        )
        return synthetic_id, None

    if not (settings.WHATSAPP_ACCESS_TOKEN and settings.WHATSAPP_PHONE_NUMBER_ID):
        msg = "send_unconfigured"
        logger.error(
            "WhatsApp template send unconfigured: set WHATSAPP_ACCESS_TOKEN "
            "and WHATSAPP_PHONE_NUMBER_ID, or set WHATSAPP_MOCK_MODE=True."
        )
        return None, msg

    header_params, body_params = _split_meta_params(
        resolved.meta_name, resolved.meta_language, resolved.meta_params,
    )
    components: list[dict] = []
    if header_params:
        components.append({
            "type": "header",
            "parameters": [{"type": "text", "text": p} for p in header_params],
        })
    if body_params:
        components.append({
            "type": "body",
            "parameters": [{"type": "text", "text": p} for p in body_params],
        })

    phone_without_plus = phone_e164.lstrip("+")
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
                    "type": "template",
                    "template": {
                        "name": resolved.meta_name,
                        "language": {"code": resolved.meta_language},
                        "components": components,
                    },
                },
                timeout=10.0,
            )
            if response.status_code // 100 != 2:
                error_body = response.text[:300]
                logger.error(
                    f"Meta template error {response.status_code} for "
                    f"****{phone_e164[-4:]} template={resolved.meta_name}: "
                    f"{error_body}"
                )
                return None, f"meta_{response.status_code}"
            try:
                payload = response.json()
                messages = payload.get("messages") or []
                if messages and isinstance(messages[0], dict):
                    wamid = messages[0].get("id")
                    if wamid:
                        return str(wamid), None
            except (ValueError, KeyError, TypeError) as parse_err:
                logger.warning(
                    f"Meta template 2xx but wamid parse failed for "
                    f"****{phone_e164[-4:]}: {parse_err}"
                )
            return None, "wamid_parse_failed"
    except httpx.TimeoutException:
        logger.error(f"Meta template timeout for ****{phone_e164[-4:]}.")
        return None, "timeout"
    except Exception as e:  # noqa: BLE001 — httpx raises many types
        logger.error(
            f"Meta template send failed for ****{phone_e164[-4:]}: {e}"
        )
        return None, f"exception:{type(e).__name__}"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

async def send_with_window_decision(
    *,
    db: Session,
    tenant_id: int,
    phone_e164: str,
    event: str,
    language: str,
    args: tuple,
    free_form_text: str,
    alert_type: str,
    actor_user_id: Optional[int] = None,
    now: Optional[datetime] = None,
) -> SendOutcome:
    """Send one WhatsApp message picking free-form vs template by window.

    Called by:    every WhatsApp outbound dispatcher in v6.3.22+.
                  See WHO CALLS THIS FILE in the module header.
    Calls into:   _read_last_seen_at, resolve_template,
                  _send_whatsapp_message, _post_template_to_meta,
                  _write_event.
    Side effects: one Event row staged (caller commits), one log line
                  (either [MOCK SEND] / [MOCK ALERT] from existing
                  layer, or [MOCK TEMPLATE] from this layer), one HTTP
                  call to Meta in real mode.

    Args:
        db:               sync SQLAlchemy session. Caller commits.
        tenant_id:        scope for last_seen_at lookup AND the audit
                          event row.
        phone_e164:       recipient phone, E.164 with leading '+'.
        event:            internal event name. Must be a key of
                          whatsapp_templates.EVENT_ROUTING. Unknown
                          values trigger the
                          window_expired_no_template branch (out of
                          window) and skip the send.
        language:         'en_US' or 'hi'. The helper passes this
                          straight to resolve_template, which handles
                          hi -> en_US fallback.
        args:             positional args matching the Meta template's
                          HEADER+BODY {{n}} placeholder count. Tuple
                          or list. Same shape as the args the dispatcher
                          already passes to message_formatters.*.format().
        free_form_text:   the already-rendered Python string for the
                          in-window branch. Dispatchers that built this
                          via message_formatters.format() pass it
                          verbatim.
        alert_type:       short label used in log breadcrumbs and audit
                          payloads. Mirrors the existing _send_alert
                          alert_type contract.
        actor_user_id:    optional user id for the event row's
                          actor_user_id column. System-tick dispatchers
                          leave this None.
        now:              optional clock override for tests. Defaults
                          to datetime.now(timezone.utc).

    Returns:
        SendOutcome. See dataclass docstring.

    Raises:
        Never. Transport, registry, and resolve_template errors all
        surface as SendOutcome(success=False, error=...).
    """
    now = now or datetime.now(timezone.utc)
    last_seen_at = _read_last_seen_at(
        db, tenant_id=tenant_id, phone_e164=phone_e164,
    )
    within_window = _is_within_window(last_seen_at, now)

    # Common audit payload shared by every branch — minus the branch-
    # specific keys layered on top before the row is staged.
    base_payload = {
        "phone": phone_e164,
        "event": event,
        "language": language,
        "alert_type": alert_type,
        "within_window": within_window,
        "last_seen_at": last_seen_at.isoformat() if last_seen_at else None,
    }

    if within_window:
        wamid = await _send_whatsapp_message(phone_e164, free_form_text)
        success = wamid is not None
        _write_event(
            db,
            tenant_id=tenant_id,
            event_type=EVENT_FREEFORM_SENT,
            payload={**base_payload, "wamid": wamid, "success": success},
            actor_user_id=actor_user_id,
        )
        return SendOutcome(
            path="freeform",
            success=success,
            wamid=wamid,
            used_fallback=False,
            error=None if success else "freeform_send_failed",
        )

    # Out of window — template path.
    try:
        resolved = resolve_template(event, language, args)
    except UnknownEventError:
        _write_event(
            db,
            tenant_id=tenant_id,
            event_type=EVENT_WINDOW_EXPIRED_NO_TEMPLATE,
            payload={**base_payload, "reason": "unknown_event"},
            actor_user_id=actor_user_id,
        )
        logger.warning(
            "whatsapp_send_helper: dropping send — unknown event %r "
            "outside 24h window for ****%s",
            event, phone_e164[-4:],
        )
        return SendOutcome(
            path="skipped_unknown_event",
            success=False,
            wamid=None,
            used_fallback=False,
            error="unknown_event",
        )
    except ArgCountMismatchError as exc:
        _write_event(
            db,
            tenant_id=tenant_id,
            event_type=EVENT_TEMPLATE_PARAM_MISMATCH,
            payload={
                **base_payload,
                "args_count": len(args),
                "message": str(exc),
            },
            actor_user_id=actor_user_id,
        )
        logger.warning(
            "whatsapp_send_helper: param mismatch event=%s lang=%s "
            "args=%d phone=****%s — %s",
            event, language, len(args), phone_e164[-4:], exc,
        )
        return SendOutcome(
            path="skipped_param_mismatch",
            success=False,
            wamid=None,
            used_fallback=False,
            error="param_mismatch",
        )
    except (KeyError, ValueError) as exc:
        # Registry drift (META_TEMPLATES missing both hi and en_US for
        # this event) or invalid language string. Surface as
        # window_expired_no_template — from the dispatcher's point of
        # view, no template was available.
        _write_event(
            db,
            tenant_id=tenant_id,
            event_type=EVENT_WINDOW_EXPIRED_NO_TEMPLATE,
            payload={
                **base_payload,
                "reason": type(exc).__name__,
                "message": str(exc),
            },
            actor_user_id=actor_user_id,
        )
        logger.error(
            "whatsapp_send_helper: registry drift for event=%s lang=%s — %s",
            event, language, exc,
        )
        return SendOutcome(
            path="skipped_unknown_event",
            success=False,
            wamid=None,
            used_fallback=False,
            error="registry_drift",
        )

    wamid, error = await _post_template_to_meta(phone_e164, resolved)
    if wamid is not None:
        _write_event(
            db,
            tenant_id=tenant_id,
            event_type=EVENT_TEMPLATE_SENT,
            payload={
                **base_payload,
                "meta_name": resolved.meta_name,
                "meta_language": resolved.meta_language,
                "meta_params": resolved.meta_params,
                "used_fallback": resolved.used_fallback,
                "wamid": wamid,
                "rendered_text": resolved.rendered_text,
            },
            actor_user_id=actor_user_id,
        )
        return SendOutcome(
            path="template",
            success=True,
            wamid=wamid,
            used_fallback=resolved.used_fallback,
            error=None,
        )

    # Real-mode failure (mock mode never reaches here — _post_template_to_meta
    # always returns a synthetic wamid in mock mode).
    _write_event(
        db,
        tenant_id=tenant_id,
        event_type=EVENT_TEMPLATE_REJECTED,
        payload={
            **base_payload,
            "meta_name": resolved.meta_name,
            "meta_language": resolved.meta_language,
            "meta_params": resolved.meta_params,
            "used_fallback": resolved.used_fallback,
            "error": error,
        },
        actor_user_id=actor_user_id,
    )
    return SendOutcome(
        path="failed",
        success=False,
        wamid=None,
        used_fallback=resolved.used_fallback,
        error=error or "unknown",
    )
