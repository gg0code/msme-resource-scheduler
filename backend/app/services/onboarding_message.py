# app/services/onboarding_message.py - Version 1.0
# Branch: v5-whatsapp
# Iteration: v6.3.12 (Day-1 onboarding sequence)
#
# FILE PURPOSE
# Dispatches the one-shot WhatsApp confirmation message that fires when a
# fresh tenant finishes adding their first employees + machines. The
# message acknowledges the setup, sets expectations for tomorrow's morning
# push, and signals that the bot is now active. Idempotency is enforced
# via the v6.3.3 events audit table - the message can never fire twice
# for the same tenant.
#
# WHO CALLS THIS FILE
# - app/routers/onboarding.py - POST /api/v1/onboarding/complete handler
#                                calls send_if_unsent() after the frontend
#                                Promise.all save resolves.
# - app/routers/whatsapp.py   - the HAAN consent-flip path calls
#                                resume_pending_after_consent() to deliver
#                                a message that was staged earlier when
#                                the owner had not yet given consent.
#
# WHAT THIS FILE CALLS
# - app.models.auth.Tenant            - row read for industry_type + time
# - app.models.employee.Employee      - count of active employees
# - app.models.machine.Machine        - count of operational machines
# - app.models.whatsapp.PhoneTenantMap - owner phone + consent lookup
# - app.models.event.Event            - idempotency event writes (3 types)
# - app.services.briefings.templates  - industry_labels() vocabulary
# - app.services.push_schedule        - get_morning_briefing_time()
# - app.services.whatsapp_responses   - onboarding_complete template
# - app.services.whatsapp_send        - _send_whatsapp_message() async
#
# DESIGN NOTES
# - Three terminal event_types track every outcome path so the audit
#   trail is complete:
#     onboarding.message_sent        - delivered; idempotency lock
#     onboarding.pending_consent     - staged; awaiting HAAN reply
#     onboarding.skipped_no_phone    - desktop-first tenant; no message
#   Single-fire is enforced by checking for ANY of the three before
#   sending; once one is written, send_if_unsent() is a no-op.
# - The HAAN flip path (resume_pending_after_consent) is what converts a
#   pending_consent stage into message_sent. It is safe to call on every
#   HAAN reply - if no pending event exists, the function is a no-op.
# - Both public functions are async because they live downstream of the
#   _send_whatsapp_message() coroutine and so they can be awaited
#   directly from FastAPI async route handlers (the new onboarding
#   router and the existing whatsapp router are both async). The DB
#   session is sync per CLAUDE.md WhatsApp pipeline rule.
# - Industry vocabulary comes from briefings.templates.industry_labels.
#   This module never branches on industry_type itself - all vertical
#   variation is one dict lookup, matching the BUG-6 lesson.
# - Counts filter on status='Active' / 'Operational' to mirror the
#   dashboard's headcount logic. On Day-1 every row is active so the
#   number is identical to a total count today; using the same predicate
#   means the message agrees with the dashboard later.
# - v6.3.19 will introduce per-tenant push schedules. The morning time
#   we quote is read via get_morning_briefing_time(tenant) so the swap
#   happens entirely inside push_schedule.py and the message stays
#   truthful without changes here.

import logging
from typing import Optional, Tuple

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.auth import TOP_TIER_ROLES, Tenant
from app.models.employee import Employee
from app.models.event import Event
from app.models.machine import Machine
from app.models.whatsapp import PhoneTenantMap
from app.services.briefings.templates import industry_labels
from app.services.push_schedule import get_morning_briefing_time
from app.services.whatsapp_responses import get_response
from app.services.whatsapp_send import _send_whatsapp_message


logger = logging.getLogger(__name__)


# Terminal event types. Each tenant ends up with exactly one of these in
# the events table; pending_consent is the only non-terminal state and it
# converts to message_sent via resume_pending_after_consent().
EVENT_MESSAGE_SENT     = "onboarding.message_sent"
EVENT_PENDING_CONSENT  = "onboarding.pending_consent"
EVENT_SKIPPED_NO_PHONE = "onboarding.skipped_no_phone"

_TERMINAL_EVENT_TYPES = (EVENT_MESSAGE_SENT, EVENT_SKIPPED_NO_PHONE)


# ---------------------------------------------------------------------------
# Idempotency helpers
# ---------------------------------------------------------------------------


def _has_event(db: Session, tenant_id: int, event_type: str) -> bool:
    """
    Check whether an event of the given type exists for this tenant.

    Called by:    send_if_unsent (idempotency lock check),
                  resume_pending_after_consent (re-entry guard).
    Calls into:   db.query(Event) using the composite index
                  idx_events_tenant_event_type from migration 028.
    Side effects: read-only.

    Args:
        db:         sync SQLAlchemy session.
        tenant_id:  scope.
        event_type: dotted string e.g. 'onboarding.message_sent'.

    Returns: True if at least one row exists, False otherwise.
    """
    return db.query(Event.id).filter(
        Event.tenant_id == tenant_id,
        Event.event_type == event_type,
    ).first() is not None


def _is_already_handled(db: Session, tenant_id: int) -> bool:
    """
    True if this tenant has already reached a terminal onboarding state.

    Called by:    send_if_unsent (the single-fire gate).
    Calls into:   _has_event for each terminal event_type.
    Side effects: read-only.

    Args:
        db:        sync SQLAlchemy session.
        tenant_id: scope.

    Returns:
        True if onboarding.message_sent or onboarding.skipped_no_phone
        exists for this tenant. False if neither exists - the caller may
        proceed (a stale onboarding.pending_consent does NOT count as
        terminal; resume_pending_after_consent is what converts it).
    """
    for event_type in _TERMINAL_EVENT_TYPES:
        if _has_event(db, tenant_id, event_type):
            return True
    return False


# ---------------------------------------------------------------------------
# Tenant-scoped helpers
# ---------------------------------------------------------------------------


def _count_active_employees(db: Session, tenant_id: int) -> int:
    """
    Count employees with status='Active' for this tenant.

    Called by:    _build_message_kwargs.
    Calls into:   db.query(func.count()) with tenant_id + status filter,
                  matching the dashboard headcount pattern at
                  app/routers/dashboard.py:147-151.
    Side effects: read-only.

    Args:
        db:        sync SQLAlchemy session.
        tenant_id: scope.

    Returns: integer count of active employees. Zero is valid - means the
             tenant clicked "Save and continue" with no rows filled,
             which the validate() guard in OnboardingSetup.tsx normally
             prevents but cannot guarantee.
    """
    return db.query(func.count()).select_from(Employee).filter(
        Employee.tenant_id == tenant_id,
        Employee.status == "Active",
    ).scalar() or 0


def _count_operational_machines(db: Session, tenant_id: int) -> int:
    """
    Count machines with status='Operational' for this tenant.

    Called by:    _build_message_kwargs.
    Calls into:   db.query(func.count()) with tenant_id + status filter,
                  matching the dashboard pattern at
                  app/routers/dashboard.py:141-145.
    Side effects: read-only.
    """
    return db.query(func.count()).select_from(Machine).filter(
        Machine.tenant_id == tenant_id,
        Machine.status == "Operational",
    ).scalar() or 0


def _find_owner_phone_mapping(
    db: Session, tenant_id: int
) -> Optional[PhoneTenantMap]:
    """
    Locate the active top-tier PhoneTenantMap row for this tenant.

    Called by:    send_if_unsent (consent gate),
                  resume_pending_after_consent (re-resolve on HAAN flip).
    Calls into:   db.query(PhoneTenantMap) with tenant + role + active
                  filter. Top-tier set is the canonical TOP_TIER_ROLES
                  tuple from app/models/auth.py (owner / proprietor /
                  factory_manager / co_owner).
    Side effects: read-only.

    Args:
        db:        sync SQLAlchemy session.
        tenant_id: scope.

    Returns:
        The PhoneTenantMap row if a top-tier active mapping exists,
        else None. None means the tenant has no usable owner phone yet -
        either desktop-first signup (no phone captured) or a phone
        captured under a non-top-tier role (rare).
    """
    return db.query(PhoneTenantMap).filter(
        PhoneTenantMap.tenant_id == tenant_id,
        PhoneTenantMap.is_active == True,  # noqa: E712
        PhoneTenantMap.phone_role.in_(TOP_TIER_ROLES),
    ).first()


def _build_message(db: Session, tenant: Tenant) -> str:
    """
    Render the hinglish onboarding-complete message for this tenant.

    Called by:    send_if_unsent, resume_pending_after_consent.
    Calls into:   _count_active_employees, _count_operational_machines,
                  industry_labels (vertical vocabulary),
                  get_morning_briefing_time (push_schedule.py),
                  get_response('onboarding_complete', 'hinglish').
    Side effects: read-only - counts + tenant attribute reads only.

    Args:
        db:     sync SQLAlchemy session.
        tenant: Tenant ORM row.

    Returns:
        Fully formatted hinglish string ready to dispatch via
        _send_whatsapp_message. The english + hindi locale stubs are
        wired into the RESPONSES dict but not selected today; v6.3.18
        will introduce per-tenant locale routing.
    """
    labels = industry_labels(tenant.industry_type)
    morning_time = get_morning_briefing_time(tenant)

    return get_response(
        "onboarding_complete",
        "hinglish",
        workspace_label=labels["workspace_label"],
        employee_count=str(_count_active_employees(db, tenant.id)),
        employees_label=labels["employees"],
        machine_count=str(_count_operational_machines(db, tenant.id)),
        machines_label=labels["machines"],
        time=morning_time.strftime("%H:%M"),
    )


def _record_event(
    db: Session,
    tenant_id: int,
    event_type: str,
    actor_user_id: Optional[int],
    payload: Optional[dict],
) -> None:
    """
    Stage one Event row on the session. Caller commits.

    Called by:    send_if_unsent, resume_pending_after_consent.
    Calls into:   db.add(Event(...)) - matches the canonical pattern at
                  app/services/team_service.py:233-240.
    Side effects: stages one INSERT into events. Caller is responsible
                  for db.commit() so the event is durable.

    Args:
        db:            sync SQLAlchemy session.
        tenant_id:     scope.
        event_type:    one of EVENT_MESSAGE_SENT, EVENT_PENDING_CONSENT,
                       EVENT_SKIPPED_NO_PHONE.
        actor_user_id: user who triggered the flow (typically the owner
                       who clicked "Save and continue"). Nullable because
                       the HAAN-flip resume path is system-driven.
        payload:       optional JSONB body (phone, counts, labels). Kept
                       small - the audit row should not duplicate the
                       message text.
    """
    db.add(Event(
        tenant_id=tenant_id,
        event_type=event_type,
        entity_type="tenant",
        entity_id=tenant_id,
        actor_user_id=actor_user_id,
        source="system",
        payload=payload,
    ))


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def send_if_unsent(
    *,
    tenant_id: int,
    actor_user_id: Optional[int],
    db: Session,
) -> Tuple[str, Optional[str]]:
    """
    Fire the Day-1 onboarding confirmation if the tenant has not yet
    reached a terminal state. Idempotent.

    Called by:    app/routers/onboarding.py POST /api/v1/onboarding/complete
                  handler. The route is fire-and-forget from the
                  frontend's perspective.
    Calls into:   _is_already_handled (single-fire gate),
                  _find_owner_phone_mapping, _build_message,
                  _send_whatsapp_message (async),
                  _record_event + db.commit() to persist the outcome.
    Side effects:
        - Reads tenants, employees, machines, phone_tenant_map, events.
        - On send: one HTTP POST to Meta Cloud API (or [MOCK SEND] log).
        - Always: writes one event row + commits, except when
          _is_already_handled returns True (no DB writes at all).

    Args:
        tenant_id:     the tenant whose onboarding just completed. Caller
                       takes this from the JWT, never from request body.
        actor_user_id: user who triggered completion (for audit). Pass
                       None when called from a system context.
        db:            sync SQLAlchemy session.

    Returns:
        (outcome, detail) where outcome is one of:
          'already_handled' - terminal event already exists; no-op.
          'sent'            - delivered now; message_sent event recorded.
          'pending_consent' - phone exists but consent_given is False;
                              pending event recorded; HAAN flip will
                              call resume_pending_after_consent later.
          'skipped_no_phone'- no top-tier active phone mapping; skipped
                              event recorded.
        detail is the masked phone tail for sent/pending paths, else None.

    Raises: nothing. All transport failures are swallowed by the
            underlying _send_whatsapp_message; we still record the
            message_sent event because the caller cannot observe
            HTTP-level errors anyway (matches team_invite_whatsapp.py
            v6.3.5 contract).
    """
    if _is_already_handled(db, tenant_id):
        logger.info(
            f"onboarding_message: tenant_id={tenant_id} already handled, no-op."
        )
        return "already_handled", None

    tenant = db.query(Tenant).filter(Tenant.id == tenant_id).first()
    if tenant is None:
        # Should not happen - the JWT guarantees the tenant row - but
        # guard so we never crash a request for a stale token.
        logger.warning(
            f"onboarding_message: tenant_id={tenant_id} not found, skipping."
        )
        return "already_handled", None

    mapping = _find_owner_phone_mapping(db, tenant_id)

    if mapping is None:
        # Desktop-first tenant or pre-v6.3.2 signup: no usable phone.
        # Record the skip so future iterations can surface "% of new
        # tenants reached on Day 1" without scanning every tenant row.
        _record_event(
            db, tenant_id, EVENT_SKIPPED_NO_PHONE, actor_user_id,
            payload={"reason": "no_top_tier_active_phone_mapping"},
        )
        db.commit()
        logger.info(
            f"onboarding_message: tenant_id={tenant_id} skipped - no phone."
        )
        return "skipped_no_phone", None

    masked = f"****{mapping.phone_number[-4:]}"

    if not mapping.consent_given:
        # Phone exists but the owner has not yet replied HAAN. Stage the
        # message; resume_pending_after_consent fires on consent flip.
        _record_event(
            db, tenant_id, EVENT_PENDING_CONSENT, actor_user_id,
            payload={"phone": mapping.phone_number},
        )
        db.commit()
        logger.info(
            f"onboarding_message: tenant_id={tenant_id} pending consent "
            f"for {masked}."
        )
        return "pending_consent", masked

    # Happy path: consent given, dispatch now.
    message = _build_message(db, tenant)
    await _send_whatsapp_message(mapping.phone_number, message)
    _record_event(
        db, tenant_id, EVENT_MESSAGE_SENT, actor_user_id,
        payload={
            "phone": mapping.phone_number,
            "trigger": "onboarding_complete",
        },
    )
    db.commit()
    logger.info(
        f"onboarding_message: tenant_id={tenant_id} sent to {masked}."
    )
    return "sent", masked


async def resume_pending_after_consent(
    *,
    tenant_id: int,
    db: Session,
) -> bool:
    """
    Deliver a previously-staged onboarding message after the owner replies
    HAAN. Safe to call on every HAAN reply - no-op when nothing is staged.

    Called by:    app/routers/whatsapp.py inside the CONSENT_TRIGGER
                  branch, immediately after `await record_consent(...)`.
    Calls into:   _is_already_handled (avoid double-send if a manual
                  re-trigger already delivered),
                  _has_event(EVENT_PENDING_CONSENT) (only resume when a
                  pending stage exists),
                  _find_owner_phone_mapping (re-resolve - the consent
                  flip just happened so consent_given is now True),
                  _build_message + _send_whatsapp_message,
                  _record_event + db.commit().
    Side effects:
        - Read-only when no pending stage exists (the common case - any
          HAAN that wasn't preceded by an onboarding completion).
        - On stage-found: one HTTP POST to Meta + one event INSERT + commit.

    Args:
        tenant_id: identity from the resolved PhoneTenantMap row.
        db:        sync SQLAlchemy session.

    Returns:
        True if a message was sent during this call, False if there was
        nothing pending or the tenant was already handled. Callers in
        whatsapp.py do not branch on this - the HAAN reply text is
        chosen independently - but tests rely on the boolean.
    """
    if _is_already_handled(db, tenant_id):
        return False
    if not _has_event(db, tenant_id, EVENT_PENDING_CONSENT):
        return False

    tenant = db.query(Tenant).filter(Tenant.id == tenant_id).first()
    if tenant is None:
        return False

    mapping = _find_owner_phone_mapping(db, tenant_id)
    if mapping is None or not mapping.consent_given:
        # Consent flip should have just landed; if not, do not invent a
        # send. The pending event stays in place for a future retry.
        return False

    message = _build_message(db, tenant)
    await _send_whatsapp_message(mapping.phone_number, message)
    _record_event(
        db, tenant_id, EVENT_MESSAGE_SENT,
        actor_user_id=None,  # system-triggered after HAAN flip
        payload={
            "phone": mapping.phone_number,
            "trigger": "consent_flip_resume",
        },
    )
    db.commit()
    logger.info(
        f"onboarding_message: tenant_id={tenant_id} resumed after consent "
        f"flip, sent to ****{mapping.phone_number[-4:]}."
    )
    return True
