# app/services/briefing_intelligence/catalog/health.py
# Branch: v5-whatsapp
#
# FILE PURPOSE
# Health / freshness signal evaluators for v6.3.11 pattern briefings:
#   - detect_manager_silence (spec B.6.manager_silence, tier 2, high)
#
# WHO CALLS THIS FILE
# - app/services/briefing_intelligence/composer.py — ALL_DETECTORS.
# - tests/services/test_detect_manager_silence.py
#
# WHAT THIS FILE CALLS
# - app/models/auth.py — Tenant ORM (created_at for quiet period).
# - app/models/event.py — Event ORM (attendance.recorded reads).
# - app/services/briefing_intelligence/signals.py — SignalResult.
#
# DESIGN NOTES
# - "Manager silence" is detected via the count of attendance.recorded
#   events written by save_checkin_state() over the last 7 days. The
#   v6.3.11 prerequisite (whatsapp_checkin.py) writes one Event per
#   manager check-in; absence of those events for several days is the
#   signal that the manager has stopped replying.
# - Threshold: < 4 events in the last 7 days fires (spec B.6 "manager
#   missed 3+ working days"). Strictly less than 4 because "missed 3"
#   means at most 4 days were checked in.
# - Quiet period: tenants younger than 7 days return None — the
#   manager has not had time to establish a pattern, so silence is
#   meaningless.
# - Confidence is high once data is wired. The prompt explicitly
#   notes this is a Phase-2 signal: until 7+ days of attendance.
#   recorded events accumulate post-deploy, the signal is almost
#   guaranteed to fire for new tenants — that's why the quiet-period
#   filter is mandatory.

import logging
from datetime import date, datetime, timedelta, timezone
from typing import Optional

from sqlalchemy.orm import Session

from app.models.auth import Tenant
from app.models.event import Event
from app.services.briefing_intelligence.signals import SignalResult

logger = logging.getLogger(__name__)

CATEGORY = "health"

ATTENDANCE_EVENT_TYPE = "attendance.recorded"

MANAGER_SILENCE_SIGNAL_ID = "manager_silence"
MANAGER_SILENCE_TIER = 2
MANAGER_SILENCE_CONFIDENCE = "high"
MANAGER_SILENCE_COOLDOWN_DAYS = 7
MANAGER_SILENCE_WINDOW_DAYS = 7
# Strictly less than this many check-ins in the window fires the signal.
MANAGER_SILENCE_MIN_CHECKINS = 4
# Tenants younger than this many days return None (insufficient pattern).
MANAGER_SILENCE_MIN_TENANT_AGE_DAYS = 7


def detect_manager_silence(
    tenant_id: int,
    today: date,
    db: Session,
) -> Optional[SignalResult]:
    """Detect a manager who has stopped replying to morning check-ins.

    Tier: 2.
    Confidence: high (once 7+ days of attendance.recorded events
        have accumulated post-deploy).
    Data: events table, event_type='attendance.recorded'.
    Suppression: tenant younger than 7 days returns None.
    Spec: v6_3_11_signals_spec.md B.6 manager_silence.

    Called by:    composer.compose_briefing via ALL_DETECTORS.
    Calls into:   Tenant + Event ORM.
    Side effects: none — pure read.
    """
    tenant = db.query(Tenant).filter(Tenant.id == tenant_id).first()
    age = _tenant_age_days(tenant, today)
    if age is None or age < MANAGER_SILENCE_MIN_TENANT_AGE_DAYS:
        return None

    cutoff_dt = datetime.combine(
        today - timedelta(days=MANAGER_SILENCE_WINDOW_DAYS),
        datetime.min.time(),
    ).replace(tzinfo=timezone.utc)

    checkin_count = (
        db.query(Event)
        .filter(
            Event.tenant_id == tenant_id,
            Event.event_type == ATTENDANCE_EVENT_TYPE,
            Event.created_at >= cutoff_dt,
        )
        .count()
    )

    if checkin_count >= MANAGER_SILENCE_MIN_CHECKINS:
        return None

    missed = MANAGER_SILENCE_WINDOW_DAYS - checkin_count

    return SignalResult(
        signal_id=MANAGER_SILENCE_SIGNAL_ID,
        category=CATEGORY,
        tier=MANAGER_SILENCE_TIER,
        confidence=MANAGER_SILENCE_CONFIDENCE,
        subject_entity_type="tenant",
        subject_entity_id=None,
        severity_score=float(missed),
        message_hi_en=(
            f"Pichhle {MANAGER_SILENCE_WINDOW_DAYS} din mein manager ne sirf "
            f"{checkin_count} check-in reply diye — sab theek hai?"
        ),
        message_en=(
            f"Manager replied to only {checkin_count} of the last "
            f"{MANAGER_SILENCE_WINDOW_DAYS} check-ins."
        ),
        cooldown_days=MANAGER_SILENCE_COOLDOWN_DAYS,
    )


def _tenant_age_days(tenant: Optional[Tenant], today: date) -> Optional[int]:
    """Days between tenant.created_at and today, or None when missing.

    Called by:    detect_manager_silence (this file) — enforces the
                  spec quiet-period rule that this signal is silent
                  for tenants younger than 7 days.
    Calls into:   nothing — pure attribute access.
    Side effects: none.
    """
    if tenant is None:
        return None
    created = getattr(tenant, "created_at", None)
    if created is None:
        return None
    if isinstance(created, datetime):
        created_date = created.date()
    elif isinstance(created, date):
        created_date = created
    else:
        return None
    return (today - created_date).days
