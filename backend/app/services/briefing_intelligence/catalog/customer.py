# app/services/briefing_intelligence/catalog/customer.py
# Branch: v5-whatsapp
#
# FILE PURPOSE
# Customer-category signal evaluators for v6.3.11 pattern briefings:
#   - detect_recurring_customer (spec B.4.recurring_customer_callout,
#     tier 2, high)
#   - detect_revenue_at_risk (spec B.4.revenue_at_risk, tier 2, medium)
#
# WHO CALLS THIS FILE
# - app/services/briefing_intelligence/composer.py — ALL_DETECTORS.
# - tests/services/test_detect_recurring_customer.py
# - tests/services/test_detect_revenue_at_risk.py
#
# WHAT THIS FILE CALLS
# - app/models/job.py — Job ORM (customer, status, order_value, end_date).
# - app/models/auth.py — Tenant ORM (created_at for day-marker gate).
# - app/services/status_normalize.py — status_in().
# - app/services/briefing_intelligence/signals.py — SignalResult.
#
# DESIGN NOTES
# - jobs.customer is a free-text VARCHAR. We GROUP BY customer in
#   Python after a tenant-scoped scan rather than relying on database-
#   side GROUP BY because (a) the cardinality is small and (b) we
#   normalise customer strings (strip + casefold) so 'ACME' and 'acme'
#   collapse into one bucket.
# - detect_recurring_customer fires only on day_count IN
#   {7, 14, 21, 30} (per-evaluator note in the prompt) so it doesn't
#   add daily noise — recurring customers are a Day-7 / monthly-marker
#   observation, not something to flag every morning.
# - detect_revenue_at_risk self-suppresses when delayed_jobs_count
#   would fire for the same set of jobs. The composer's diversity
#   rule keeps one job-category signal per briefing; suppressing here
#   prevents this signal from competing with the higher-tier
#   delayed_jobs_count over the same data.

import logging
from datetime import date, datetime, timedelta
from typing import Optional

from sqlalchemy.orm import Session

from app.models.auth import Tenant
from app.models.job import Job
from app.services.briefing_intelligence.signals import SignalResult
from app.services.status_normalize import status_in

logger = logging.getLogger(__name__)

CATEGORY = "customer"

# Terminal job statuses excluded from both signals.
TERMINAL_STATUSES: frozenset[str] = frozenset({"completed", "cancelled"})

# ---------------------------------------------------------------------------
# detect_recurring_customer
# ---------------------------------------------------------------------------

RECURRING_SIGNAL_ID = "recurring_customer_callout"
RECURRING_TIER = 2
RECURRING_CONFIDENCE = "high"
RECURRING_COOLDOWN_DAYS = 7
RECURRING_WINDOW_DAYS = 30
RECURRING_MIN_JOBS = 3
# Day markers — the signal is allowed to fire only on these tenant
# ages. Off-marker days return None to keep the daily briefing quiet.
RECURRING_DAY_MARKERS: frozenset[int] = frozenset({7, 14, 21, 30})


def detect_recurring_customer(
    tenant_id: int,
    today: date,
    db: Session,
) -> Optional[SignalResult]:
    """Detect a customer with 3+ active jobs in the last 30 days.

    Tier: 2.
    Confidence: high — the count is exact, the only judgement call
        is "is 3 enough to flag?", which is the threshold knob.
    Data: jobs.customer, jobs.status, jobs.created_at.
    Suppression: only fires on Day 7, 14, 21, 30 of the tenant — the
        spec rule that this is a marker-day observation, not a daily
        one. Skips terminal-status jobs and skips jobs missing customer.
    Spec: v6_3_11_signals_spec.md B.4 recurring_customer_callout.

    Called by:    composer.compose_briefing via ALL_DETECTORS.
    Calls into:   Tenant + Job ORM.
    Side effects: none — pure read.
    """
    age = _tenant_age_days(tenant_id, today, db)
    if age is None or age not in RECURRING_DAY_MARKERS:
        return None

    window_start = today - timedelta(days=RECURRING_WINDOW_DAYS)
    jobs: list[Job] = (
        db.query(Job)
        .filter(
            Job.tenant_id == tenant_id,
            Job.created_at.isnot(None),
        )
        .all()
    )

    buckets: dict[str, list[Job]] = {}
    for j in jobs:
        if j.customer is None:
            continue
        key = j.customer.strip().casefold()
        if not key:
            continue
        if status_in(j.status, TERMINAL_STATUSES):
            continue
        # Created within the 30-day window.
        ca = j.created_at
        if ca is None:
            continue
        if isinstance(ca, datetime):
            ca_date = ca.date()
        else:
            ca_date = ca
        if ca_date < window_start:
            continue
        buckets.setdefault(key, []).append(j)

    qualifying = [
        (jobs_for_customer, jobs_for_customer[0].customer.strip())
        for jobs_for_customer in buckets.values()
        if len(jobs_for_customer) >= RECURRING_MIN_JOBS
    ]
    if not qualifying:
        return None

    qualifying.sort(key=lambda pair: (-len(pair[0]), pair[1].casefold()))
    top_jobs, top_name = qualifying[0]
    n = len(top_jobs)

    return SignalResult(
        signal_id=RECURRING_SIGNAL_ID,
        category=CATEGORY,
        tier=RECURRING_TIER,
        confidence=RECURRING_CONFIDENCE,
        subject_entity_type="customer",
        subject_entity_id=None,
        severity_score=float(n),
        message_hi_en=(
            f"{top_name} ke saath aapke {n} jobs chal rahe hain — top customer."
        ),
        message_en=(
            f"You have {n} active jobs with {top_name} — a top customer."
        ),
        cooldown_days=RECURRING_COOLDOWN_DAYS,
    )


# ---------------------------------------------------------------------------
# detect_revenue_at_risk
# ---------------------------------------------------------------------------

REVENUE_SIGNAL_ID = "revenue_at_risk"
REVENUE_TIER = 2
REVENUE_CONFIDENCE = "medium"
REVENUE_COOLDOWN_DAYS = 2
REVENUE_THRESHOLD_INR = 50_000.0


def detect_revenue_at_risk(
    tenant_id: int,
    today: date,
    db: Session,
) -> Optional[SignalResult]:
    """Detect ₹>=50,000 of order_value tied up in delayed jobs.

    Tier: 2.
    Confidence: medium — order_value is nullable so the figure under-
        counts when fields are blank.
    Data: jobs.order_value, jobs.status, jobs.end_date.
    Suppression:
      - When `delayed_jobs_count` would also fire AND there are <= 3
        delayed jobs, suppress to avoid two job-category signals over
        the same data. The composer's diversity rule already keeps
        one per category, but suppressing here ensures
        delayed_jobs_count (tier 1) wins over revenue_at_risk
        (tier 2) at the candidate stage even when severities differ.
      - When the summed value is below REVENUE_THRESHOLD_INR.
    Spec: v6_3_11_signals_spec.md B.4 revenue_at_risk and per-evaluator
    note "alternate-day surfacing" handled via cooldown_days=2.

    Called by:    composer.compose_briefing via ALL_DETECTORS.
    Calls into:   Job ORM.
    Side effects: none — pure read.
    """
    delayed_jobs: list[Job] = (
        db.query(Job)
        .filter(
            Job.tenant_id == tenant_id,
            Job.end_date.isnot(None),
            Job.end_date < today,
        )
        .all()
    )
    active_delayed = [
        j for j in delayed_jobs
        if not status_in(j.status, TERMINAL_STATUSES)
    ]
    if not active_delayed:
        return None

    with_value = [j for j in active_delayed if (j.order_value or 0.0) > 0.0]
    total_value = sum(float(j.order_value or 0.0) for j in with_value)
    if total_value < REVENUE_THRESHOLD_INR:
        return None

    # Same-data suppression: small-N delayed-jobs lists already get
    # surfaced verbatim by detect_delayed_jobs. Adding revenue here on
    # top would double-message the same observation.
    if len(active_delayed) <= 3:
        return None

    n = len(with_value)
    amount_text = _format_inr(total_value)

    return SignalResult(
        signal_id=REVENUE_SIGNAL_ID,
        category=CATEGORY,
        tier=REVENUE_TIER,
        confidence=REVENUE_CONFIDENCE,
        subject_entity_type="tenant",
        subject_entity_id=None,
        severity_score=float(round(total_value, 2)),
        message_hi_en=(
            f"{n} delayed jobs ka total {amount_text} order value pending hai."
        ),
        message_en=(
            f"{n} delayed jobs hold a total of {amount_text} in pending "
            f"order value."
        ),
        cooldown_days=REVENUE_COOLDOWN_DAYS,
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _tenant_age_days(
    tenant_id: int,
    today: date,
    db: Session,
) -> Optional[int]:
    """Days between tenant.created_at and today, or None when missing.

    Called by:    detect_recurring_customer (this file) — gates the
                  signal to day_count IN {7, 14, 21, 30} markers.
    Calls into:   Tenant ORM (read-only).
    Side effects: none.

    Returns None for missing tenants or null created_at so callers
    treat the gate as "do not fire" rather than crashing.
    """
    tenant = db.query(Tenant).filter(Tenant.id == tenant_id).first()
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


def _format_inr(amount: float) -> str:
    """Format an INR amount with the 'Rs.' ASCII prefix.

    Called by:    detect_revenue_at_risk (this file).
    Calls into:   nothing — pure string formatting.
    Side effects: none.

    The CLAUDE.md ASCII rule disallows the Devanagari/Latin Rupee
    glyph in source files, so we use the legacy 'Rs.' textual prefix
    plus thousands separators (Western grouping; the Indian comma
    grouping is deferred to a future locale layer).
    """
    rounded = int(round(amount))
    return f"Rs.{rounded:,}"
