# app/services/briefing_intelligence/cooldown.py
# Branch: v5-whatsapp
#
# FILE PURPOSE
# Cooldown + escalation tracking for v6.3.11 pattern briefings, backed
# by the existing events table (no new schema). Per spec Section D.4
# / D.5.
#
# WHO CALLS THIS FILE
# - app/services/briefing_intelligence/composer.py — calls
#   get_last_fired() per candidate inside filter_by_cooldown(), and
#   record_fired() once per surfaced signal after rendering.
#
# WHAT THIS FILE CALLS
# - app/models/event.py — Event ORM (event_type='briefing.signal_fired').
# - sqlalchemy ORM session API.
#
# DESIGN NOTES
# - We fetch all briefing.signal_fired events for the tenant within the
#   30-day lookup window and filter the JSON payload in Python. Reasons:
#     * Postgres-only JSONB operators (payload->>'signal_id') would
#       break SQLite tests where conftest patches JSONB → JSON.
#     * The cardinality is tiny — at most a few signals per day per
#       tenant — so the filter cost is irrelevant.
# - record_fired() does NOT commit. The composer owns the transaction
#   boundary so all surfaced signals land atomically.

import logging
from datetime import date, datetime, timedelta, timezone
from typing import Optional

from sqlalchemy.orm import Session

from app.models.event import Event
from app.services.briefing_intelligence.signals import SignalResult

logger = logging.getLogger(__name__)


SIGNAL_FIRED_EVENT_TYPE = "briefing.signal_fired"

# How far back to look for prior fires. 30 days is a safety ceiling —
# any cooldown beyond a month would be a different design conversation.
COOLDOWN_LOOKUP_WINDOW_DAYS = 30


def get_last_fired(
    tenant_id: int,
    signal_id: str,
    subject_entity_id: Optional[int],
    db: Session,
) -> Optional[Event]:
    """Most recent briefing.signal_fired Event for (signal_id, subject) in
    the last 30 days, or None if never fired.

    Called by:    composer.filter_by_cooldown — once per candidate.
    Calls into:   Event ORM query.
    Side effects: read-only.

    Args:
        tenant_id:         Tenant scope. Mandatory.
        signal_id:         Signal identifier ('delayed_jobs_count').
        subject_entity_id: Per-entity scope, or None for tenant-wide
                           signals. None matches None in the payload —
                           tenant-wide signals share one cooldown.
        db:                Sync Session.

    Returns:
        The newest Event row whose payload['signal_id'] == signal_id
        AND payload.get('subject_entity_id') == subject_entity_id,
        within the COOLDOWN_LOOKUP_WINDOW_DAYS window. None otherwise.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(
        days=COOLDOWN_LOOKUP_WINDOW_DAYS
    )

    candidates = (
        db.query(Event)
        .filter(
            Event.tenant_id == tenant_id,
            Event.event_type == SIGNAL_FIRED_EVENT_TYPE,
            Event.created_at >= cutoff,
        )
        .order_by(Event.created_at.desc())
        .all()
    )

    for ev in candidates:
        payload = ev.payload or {}
        if payload.get("signal_id") != signal_id:
            continue
        # subject_entity_id may be missing in older payloads — treat
        # absent the same as None.
        prior_subject = payload.get("subject_entity_id")
        if prior_subject == subject_entity_id:
            return ev

    return None


def record_fired(
    tenant_id: int,
    result: SignalResult,
    db: Session,
) -> None:
    """Stage a briefing.signal_fired event for one surfaced signal.

    Called by:    composer.compose_briefing — once per surfaced signal,
                  inside the same db session, before the composer's
                  final db.commit().
    Calls into:   db.add(Event(...)).
    Side effects: stages an INSERT. Does NOT commit. Caller owns the
                  transaction boundary so all surfaced signals land
                  atomically.

    Args:
        tenant_id: Tenant scope.
        result:    SignalResult that was actually surfaced in the
                   rendered briefing. Severity is recorded so the next
                   day's composer can compare for escalation (D.5).
        db:        Sync Session.
    """
    event = Event(
        tenant_id=tenant_id,
        event_type=SIGNAL_FIRED_EVENT_TYPE,
        entity_type=result.subject_entity_type,
        entity_id=result.subject_entity_id,
        actor_user_id=None,  # composer is system-driven, no actor
        source="system",
        payload={
            "signal_id": result.signal_id,
            "subject_entity_id": result.subject_entity_id,
            "severity_score": result.severity_score,
            "message": result.message_hi_en,
        },
    )
    db.add(event)


def is_in_cooldown(
    candidate: SignalResult,
    prior: Optional[Event],
    today: date,
) -> bool:
    """True when the candidate must be suppressed by cooldown.

    Called by:    composer.filter_by_cooldown — wraps get_last_fired
                  + this comparator into the per-candidate decision.
    Calls into:   pure date arithmetic + payload read.
    Side effects: none.

    Logic per spec D.4 + D.5:
      - No prior fire → not in cooldown.
      - Prior fire older than cooldown_days → not in cooldown.
      - Prior fire within cooldown_days AND new severity strictly
        greater than prior severity → escalation, override cooldown.
      - Prior fire within cooldown_days AND new severity <= prior →
        cooldown applies, suppress.
    """
    if prior is None:
        return False

    prior_date = prior.created_at.date() if prior.created_at else today
    age_days = (today - prior_date).days
    if age_days >= candidate.cooldown_days:
        return False

    prior_payload = prior.payload or {}
    prior_severity = prior_payload.get("severity_score")
    try:
        prior_severity_f = float(prior_severity) if prior_severity is not None else float("-inf")
    except (TypeError, ValueError):
        prior_severity_f = float("-inf")

    if candidate.severity_score > prior_severity_f:
        # Escalation — fire even inside cooldown.
        return False

    return True
