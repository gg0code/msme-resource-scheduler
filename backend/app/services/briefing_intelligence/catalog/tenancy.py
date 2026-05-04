# app/services/briefing_intelligence/catalog/tenancy.py
# Branch: v5-whatsapp
#
# FILE PURPOSE
# Day-of-tenancy signal evaluators for v6.3.11 pattern briefings:
#   - detect_day_2 (spec B.5.day_2_first_observation, tier 1, high)
#   - detect_day_7 (spec B.5.day_7_wow_signal — daily marker only,
#     tier 1, medium)
#
# Per spec B.5: detect_day_30_savings_receipt depends on the
# v6.24 KPI Baseline that has not shipped, so it is intentionally
# omitted from this catalog.
#
# WHO CALLS THIS FILE
# - app/services/briefing_intelligence/composer.py — ALL_DETECTORS.
# - tests/services/test_detect_day_2.py
# - tests/services/test_detect_day_7.py
#
# WHAT THIS FILE CALLS
# - app/models/auth.py — Tenant ORM (created_at, industry_type).
# - app/models/employee.py — Employee count.
# - app/models/machine.py — Machine count.
# - app/services/briefings/templates.py — industry_labels for the
#   employees / machines vocabulary substitution in messages.
# - app/services/briefing_intelligence/signals.py — SignalResult.
#
# DESIGN NOTES
# - Day count uses calendar days from tenant.created_at, not working
#   days. Working-day arithmetic would require a tenant calendar that
#   v6.3.11 does not yet ship. The semantic is "Day 2 means the day
#   after the day they signed up" so calendar days are correct here.
# - Both detectors are tier 1 because they only fire once per tenant;
#   missing the day-2 message has no recovery path. The composer's
#   quiet-period rule (QUIET_PERIOD_DAYS=2) means detect_day_2 fires
#   on its first eligible run — a tenant created today is age 0,
#   age 1 is the next day's briefing, age 2 hits the day-2 marker.
# - detect_day_7 here is the *daily marker* only. The Day-7 wow gate
#   that selects the strongest pattern across the listening week is
#   v6.3.16, not this.

import logging
from datetime import date, datetime
from typing import Optional

from sqlalchemy.orm import Session

from app.models.auth import Tenant
from app.models.employee import Employee
from app.models.machine import Machine
from app.services.briefing_intelligence.signals import SignalResult
from app.services.briefings.templates import industry_labels

logger = logging.getLogger(__name__)

CATEGORY = "tenancy"

# ---------------------------------------------------------------------------
# detect_day_2
# ---------------------------------------------------------------------------

DAY_2_SIGNAL_ID = "day_2_first_observation"
DAY_2_TIER = 1
DAY_2_CONFIDENCE = "high"
DAY_2_TARGET_AGE_DAYS = 2
DAY_2_COOLDOWN_DAYS = 999  # single-shot, never repeats


def detect_day_2(
    tenant_id: int,
    today: date,
    db: Session,
) -> Optional[SignalResult]:
    """Tenant turned 2 days old today — surface the first observation.

    Tier: 1.
    Confidence: high.
    Data: tenants, employees count, machines count.
    Suppression: fires only when tenant.created_at = today - 2 days.
        Cooldown effectively forever (999 days) so the single-shot
        rule holds even if the briefing dispatcher reruns.
    Spec: v6_3_11_signals_spec.md B.5 day_2_first_observation.
    """
    tenant = db.query(Tenant).filter(Tenant.id == tenant_id).first()
    age = _tenant_age_days(tenant, today)
    if age != DAY_2_TARGET_AGE_DAYS:
        return None

    labels = industry_labels(getattr(tenant, "industry_type", None) if tenant else None)
    employees_label = labels.get("employees", "employees")
    machines_label = labels.get("machines", "machines")

    n_employees = (
        db.query(Employee).filter(Employee.tenant_id == tenant_id).count()
    )
    n_machines = (
        db.query(Machine).filter(Machine.tenant_id == tenant_id).count()
    )

    return SignalResult(
        signal_id=DAY_2_SIGNAL_ID,
        category=CATEGORY,
        tier=DAY_2_TIER,
        confidence=DAY_2_CONFIDENCE,
        subject_entity_type="tenant",
        subject_entity_id=None,
        severity_score=1.0,
        message_hi_en=(
            f"Yesterday aapne {n_employees} {employees_label} aur "
            f"{n_machines} {machines_label} add kiye. "
            f"Aaj se main rozana plan dekh raha hoon."
        ),
        message_en=(
            f"Yesterday you added {n_employees} {employees_label} and "
            f"{n_machines} {machines_label}. "
            f"From today I'll watch the daily plan."
        ),
        cooldown_days=DAY_2_COOLDOWN_DAYS,
    )


# ---------------------------------------------------------------------------
# detect_day_7
# ---------------------------------------------------------------------------

DAY_7_SIGNAL_ID = "day_7_marker"
DAY_7_TIER = 1
DAY_7_CONFIDENCE = "medium"
DAY_7_TARGET_AGE_DAYS = 7
DAY_7_COOLDOWN_DAYS = 999  # single-shot


def detect_day_7(
    tenant_id: int,
    today: date,
    db: Session,
) -> Optional[SignalResult]:
    """Tenant turned 7 days old today — celebratory listening-week marker.

    Tier: 1.
    Confidence: medium — the v6.3.16 Day-7 wow gate will pick the
        strongest pattern observed across the week. Until that lands,
        this evaluator surfaces a stable celebratory line so the
        moment is not silent.
    Data: tenants, employees count, machines count.
    Suppression: fires only when tenant.created_at = today - 7 days.
    Spec: v6_3_11_signals_spec.md B.5 day_7_wow_signal (daily marker
    only — full wow gate is deferred to v6.3.16).
    """
    tenant = db.query(Tenant).filter(Tenant.id == tenant_id).first()
    age = _tenant_age_days(tenant, today)
    if age != DAY_7_TARGET_AGE_DAYS:
        return None

    labels = industry_labels(getattr(tenant, "industry_type", None) if tenant else None)
    jobs_label = labels.get("jobs", "jobs")

    return SignalResult(
        signal_id=DAY_7_SIGNAL_ID,
        category=CATEGORY,
        tier=DAY_7_TIER,
        confidence=DAY_7_CONFIDENCE,
        subject_entity_type="tenant",
        subject_entity_id=None,
        severity_score=1.0,
        message_hi_en=(
            f"Aaj ZetaOps ke saath aapka 7 din complete ho gaye. "
            f"Hafte bhar ka {jobs_label} pattern dekh raha hoon."
        ),
        message_en=(
            f"You've completed 7 days with ZetaOps. "
            f"Watching the week's {jobs_label} pattern."
        ),
        cooldown_days=DAY_7_COOLDOWN_DAYS,
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _tenant_age_days(tenant: Optional[Tenant], today: date) -> Optional[int]:
    """Days between tenant.created_at and today, or None when missing.

    Called by:    detect_day_2 + detect_day_7 (this file) to gate the
                  signal to its single firing day.
    Calls into:   nothing — pure attribute access on the loaded Tenant.
    Side effects: none.

    Returns None when the tenant is missing or has a null created_at
    so the day-marker comparison fails closed (no fire) rather than
    raising.
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
