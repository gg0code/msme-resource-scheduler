# app/services/briefing_intelligence/composer.py
# Branch: v5-whatsapp
#
# FILE PURPOSE
# Composer for v6.3.11 pattern-aware briefings. Takes (tenant, kind,
# date, db) → string. Per spec Section E.3.
#
# WHO CALLS THIS FILE
# - app/services/briefings/dispatcher.py — _build_content_for_kind
#   wraps this in a feature-flag check + try/except fallthrough.
# - tests/test_briefing_intelligence_composer.py
# - tests/test_dispatcher_pattern_briefing_integration.py
#
# WHAT THIS FILE CALLS
# - app/services/briefing_intelligence/catalog/job.py — detect_delayed_jobs
# - app/services/briefing_intelligence/cooldown.py — get_last_fired,
#   record_fired, is_in_cooldown
# - app/services/briefings/morning_content.py — build_morning_briefing
# - app/services/briefings/evening_content.py — build_evening_briefing
# - app/models/auth.py — Tenant (created_at for quiet-period + day-7 idle)
#
# DESIGN NOTES
# - ALL_DETECTORS is a single-element list in 2B. 2C extends it to
#   ~12 entries. The composer must work correctly with 1 OR many.
# - The fallback when zero signals fire is the EXISTING v6.3.4
#   templated content (build_morning/evening_briefing). This is the
#   spec D.6 "idle case". Per Q10 the tenant must be older than 7 days
#   before we append the trailing "Aaj koi alag pattern..." line.
# - Quiet period: tenants younger than QUIET_PERIOD_DAYS produce no
#   pattern signals — there is not enough data for the patterns to be
#   trustworthy. They still receive the templated fallback. Day-of-
#   tenancy signals (B.5) will land in 2C and are the only path that
#   bypasses this.
# - The composer commits its own transaction for record_fired() events
#   so signal-firing telemetry is durable. The dispatcher's outer
#   send-loop opens a fresh session per tenant and the composer's commit
#   is scoped to that session.

import logging
from datetime import date, datetime, timezone
from typing import Callable, Optional

from sqlalchemy.orm import Session

from app.models.auth import Tenant
from app.services.briefing_intelligence.catalog.attendance import (
    detect_attendance_ratio_concern,
    detect_consecutive_absence,
    detect_new_employee_no_show,
)
from app.services.briefing_intelligence.catalog.customer import (
    detect_recurring_customer,
    detect_revenue_at_risk,
)
from app.services.briefing_intelligence.catalog.health import (
    detect_manager_silence,
)
from app.services.briefing_intelligence.catalog.job import (
    detect_delayed_jobs,
    detect_no_progress,
)
from app.services.briefing_intelligence.catalog.machine import (
    detect_idle_machine,
    detect_low_utilization,
    detect_status_change_alert,
)
from app.services.briefing_intelligence.catalog.tenancy import (
    detect_day_2,
    detect_day_7,
)
from app.services.briefing_intelligence.cooldown import (
    get_last_fired,
    is_in_cooldown,
    record_fired,
)
from app.services.briefing_intelligence.signals import SignalResult
from app.services.briefings.evening_content import build_evening_briefing
from app.services.briefings.morning_content import build_morning_briefing

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# CONFIG
# ---------------------------------------------------------------------------

# Tenants younger than this are still in their first-impression window.
# All pattern signals are suppressed; the templated fallback runs.
QUIET_PERIOD_DAYS = 2

# Idle-case trailing line per spec D.6 / Q10.
IDLE_TRAILING_LINE_HI_EN = "Aaj koi alag pattern nahi dikha — sab routine hai."

# Day threshold for the idle trailing line (Q10 = "Only after Day 7").
IDLE_TRAILING_MIN_TENANT_AGE_DAYS = 7

# Hard cap on signals per briefing — spec D.1.
MAX_SIGNALS_PER_BRIEFING = 3

# Confidence rank for sort tie-breaks. Higher number = higher confidence.
_CONFIDENCE_RANK: dict[str, int] = {"high": 3, "medium": 2, "low": 1}


# Session 2C: 13 evaluators across 6 categories. Order is irrelevant
# for correctness — _select_signals re-sorts by tier / confidence /
# severity before applying the diversity rule.
DetectorFn = Callable[[int, date, Session], Optional[SignalResult]]
ALL_DETECTORS: tuple[DetectorFn, ...] = (
    # Attendance (B.1) — Phase 2, history-dependent.
    detect_consecutive_absence,
    detect_attendance_ratio_concern,
    detect_new_employee_no_show,
    # Machine (B.2).
    detect_idle_machine,
    detect_low_utilization,
    detect_status_change_alert,
    # Job (B.3) — detect_conflict_jobs deferred per Q4.
    detect_delayed_jobs,
    detect_no_progress,
    # Customer (B.4).
    detect_recurring_customer,
    detect_revenue_at_risk,
    # Day-of-tenancy (B.5) — detect_day_30 deferred (depends on v6.24).
    detect_day_2,
    detect_day_7,
    # Health (B.6) — Phase 2, history-dependent.
    detect_manager_silence,
)


# ---------------------------------------------------------------------------
# PUBLIC ENTRYPOINT
# ---------------------------------------------------------------------------

def compose_briefing(
    tenant_id: int,
    kind: str,
    today: date,
    db: Session,
) -> str:
    """Build the WhatsApp briefing string for one (tenant, kind).

    Called by:    briefings/dispatcher.py:_build_content_for_kind, only
                  when is_pattern_briefing_enabled(tenant) is True.
    Calls into:   ALL_DETECTORS, cooldown.{get_last_fired, is_in_cooldown,
                  record_fired}, build_morning_briefing, build_evening_briefing.
    Side effects: writes briefing.signal_fired Event rows for surfaced
                  signals + commits.

    Per spec E.3:
      1. Run all evaluators (filter out None).
      2. Quiet-period rule — skip all signals for very-young tenants.
      3. Cooldown filter (with escalation override).
      4. Sort by tier ASC, confidence DESC, severity DESC.
      5. Diversity rule — slot 1 wins; slots 2-3 must be a different
         category from any already-selected.
      6. Cap at MAX_SIGNALS_PER_BRIEFING.
      7. Empty selection → fall back to v6.3.4 templated content,
         optionally with the idle trailing line (Q10, after day 7).
      8. Render header + bullet messages.
      9. Persist briefing.signal_fired events for surfaced signals.

    Returns:
        WhatsApp-ready string. Never empty — the templated fallback
        guarantees a non-empty string even when zero signals fire.
    """
    tenant = db.query(Tenant).filter(Tenant.id == tenant_id).first()
    if tenant is None:
        # No tenant row — defensive fallback. Shouldn't happen in prod.
        return _render_templated_fallback(tenant_id, None, kind, today, db)

    candidates = _run_detectors(tenant_id, today, db)

    if _is_in_quiet_period(tenant, today):
        # Suppress pattern signals; let templated fallback handle the
        # message so the tenant still receives a briefing.
        candidates = []

    candidates = _filter_by_cooldown(candidates, tenant_id, today, db)

    selected = _select_signals(candidates)

    if not selected:
        return _render_templated_fallback(
            tenant_id, tenant, kind, today, db,
        )

    # Persist firing telemetry, then render. Commit once so the row is
    # durable even if the caller's send-loop later raises.
    for sig in selected:
        record_fired(tenant_id, sig, db)
    try:
        db.commit()
    except Exception:
        logger.exception(
            "Failed to commit briefing.signal_fired events for tenant %s",
            tenant_id,
        )
        try:
            db.rollback()
        except Exception:
            pass

    return _render_pattern_briefing(today, selected)


# ---------------------------------------------------------------------------
# DETECTOR ORCHESTRATION
# ---------------------------------------------------------------------------

def _run_detectors(
    tenant_id: int,
    today: date,
    db: Session,
) -> list[SignalResult]:
    """Run every registered detector serially. Detector exceptions are
    logged and dropped so one broken signal cannot poison the briefing.
    """
    out: list[SignalResult] = []
    for detector in ALL_DETECTORS:
        try:
            result = detector(tenant_id, today, db)
        except Exception:
            logger.exception(
                "Detector %s raised for tenant %s; skipping.",
                getattr(detector, "__name__", "<unknown>"),
                tenant_id,
            )
            continue
        if result is not None:
            out.append(result)
    return out


# ---------------------------------------------------------------------------
# QUIET PERIOD
# ---------------------------------------------------------------------------

def _is_in_quiet_period(tenant: Tenant, today: date) -> bool:
    """True when the tenant is too young for pattern signals to be
    trustworthy. See spec rationale in the module docstring.
    """
    age_days = _tenant_age_days(tenant, today)
    if age_days is None:
        return False
    return age_days < QUIET_PERIOD_DAYS


def _tenant_age_days(tenant: Tenant, today: date) -> Optional[int]:
    """Days between tenant.created_at (date) and today. None when
    created_at is missing.
    """
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


# ---------------------------------------------------------------------------
# COOLDOWN
# ---------------------------------------------------------------------------

def _filter_by_cooldown(
    candidates: list[SignalResult],
    tenant_id: int,
    today: date,
    db: Session,
) -> list[SignalResult]:
    """Drop candidates that are inside cooldown (with escalation override).
    Per spec D.4 / D.5.
    """
    kept: list[SignalResult] = []
    for c in candidates:
        prior = get_last_fired(
            tenant_id=tenant_id,
            signal_id=c.signal_id,
            subject_entity_id=c.subject_entity_id,
            db=db,
        )
        if is_in_cooldown(c, prior, today):
            c.suppression_reasons.append("cooldown")
            continue
        kept.append(c)
    return kept


# ---------------------------------------------------------------------------
# SELECTION + DIVERSITY + CAP
# ---------------------------------------------------------------------------

def _select_signals(
    candidates: list[SignalResult],
) -> list[SignalResult]:
    """Sort by priority, apply diversity rule (D.3), cap at 3 (D.1)."""
    if not candidates:
        return []

    sorted_candidates = sorted(candidates, key=_sort_key)

    selected: list[SignalResult] = []
    seen_categories: set[str] = set()
    for c in sorted_candidates:
        if len(selected) >= MAX_SIGNALS_PER_BRIEFING:
            break
        if not selected:
            # Slot 1 — top-priority candidate, always kept.
            selected.append(c)
            seen_categories.add(c.category)
            continue
        # Slots 2 and 3 — must be a different category.
        if c.category in seen_categories:
            c.suppression_reasons.append("diversity")
            continue
        selected.append(c)
        seen_categories.add(c.category)

    return selected


def _sort_key(s: SignalResult) -> tuple:
    """tier ASC → higher confidence → higher severity."""
    return (
        s.tier,
        -_CONFIDENCE_RANK.get(s.confidence, 0),
        -s.severity_score,
    )


# ---------------------------------------------------------------------------
# RENDERING
# ---------------------------------------------------------------------------

def _render_pattern_briefing(
    today: date,
    selected: list[SignalResult],
) -> str:
    """Header + one bullet per surfaced signal."""
    header = f"ZetaOps briefing — {today.strftime('%d %b')}"
    lines = [header, ""]
    for s in selected:
        lines.append(f"- {s.message_hi_en}")
    return "\n".join(lines)


def _render_templated_fallback(
    tenant_id: int,
    tenant: Optional[Tenant],
    kind: str,
    today: date,
    db: Session,
) -> str:
    """Idle case (D.6): defer to the v6.3.4 templated builder. Append
    the Q10 trailing line only when the tenant is older than the
    minimum age threshold.
    """
    industry_type = getattr(tenant, "industry_type", None) if tenant else None
    if kind == "evening":
        body = build_evening_briefing(
            tenant_id=tenant_id,
            industry_type=industry_type,
            today=today,
            db=db,
        )
    else:
        body = build_morning_briefing(
            tenant_id=tenant_id,
            industry_type=industry_type,
            today=today,
            db=db,
        )

    if tenant is not None:
        age_days = _tenant_age_days(tenant, today)
        if age_days is not None and age_days >= IDLE_TRAILING_MIN_TENANT_AGE_DAYS:
            return f"{body}\n\n{IDLE_TRAILING_LINE_HI_EN}"
    return body
