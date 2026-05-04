# app/services/briefing_intelligence/catalog/machine.py
# Branch: v5-whatsapp
#
# FILE PURPOSE
# Machine-category signal evaluators for v6.3.11 pattern briefings:
#   - detect_idle_machine (spec B.2.idle_machine, tier 2, high)
#   - detect_low_utilization (spec B.2.low_utilization, tier 3, medium)
#   - detect_status_change_alert (spec B.2.status_change_alert, tier 3, low)
#
# WHO CALLS THIS FILE
# - app/services/briefing_intelligence/composer.py — ALL_DETECTORS.
# - tests/services/test_detect_idle_machine.py
# - tests/services/test_detect_low_utilization.py
# - tests/services/test_detect_status_change_alert.py
#
# WHAT THIS FILE CALLS
# - app/models/machine.py — Machine ORM (status, updated_at).
# - app/models/job.py — JobAssignment, Job (assignment dates, hours).
# - app/models/unavailability.py — MachineDowntime (suppression).
# - app/services/status_normalize.py — status_in().
# - app/services/briefing_intelligence/signals.py — SignalResult.
#
# DESIGN NOTES
# - Each detector returns at most one SignalResult per call. When
#   multiple machines qualify, the worst case wins (longest idle,
#   lowest utilisation, most recent status flip) and its name goes
#   into the message. Composer's diversity rule already caps machine
#   signals at one per briefing; selecting the worst here means we
#   surface the most actionable observation.
# - IDLE_OK statuses are the union of {Operational, active}. Both
#   casings appear in production (Section C). status_in handles the
#   case-insensitive match.
# - low_utilization self-suppresses when the same machine is already
#   firing idle_machine: redundant observation, would cascade past
#   the diversity rule because both share category='machine' but the
#   composer keeps only the higher-tier one and we want the high-
#   confidence idle_machine to win when both qualify.
# - status_change_alert reads machines.updated_at, knowing that any
#   column edit refreshes it (not just status flips). Confidence is
#   pinned at 'low' as a result; a future migration could add a
#   machine.status_changed event log to lift this to 'medium'.

import logging
from datetime import date, datetime, time, timedelta
from typing import Optional

from sqlalchemy import and_
from sqlalchemy.orm import Session

from app.models.job import Job, JobAssignment
from app.models.machine import Machine
from app.models.unavailability import MachineDowntime
from app.services.briefing_intelligence.signals import SignalResult
from app.services.status_normalize import status_in

logger = logging.getLogger(__name__)

CATEGORY = "machine"

# Statuses that mean the machine is available for work — both casings
# observed in production (Section C).
IDLE_OK_STATUSES: frozenset[str] = frozenset({"operational", "active"})

# Statuses that explicitly mean the machine is NOT available.
NOT_OPERATIONAL_STATUSES: frozenset[str] = frozenset(
    {"under maintenance", "decommissioned"},
)

# ---------------------------------------------------------------------------
# detect_idle_machine
# ---------------------------------------------------------------------------

IDLE_SIGNAL_ID = "idle_machine"
IDLE_TIER = 2
IDLE_CONFIDENCE = "high"
IDLE_COOLDOWN_DAYS = 7
IDLE_WINDOW_DAYS = 7
# Tenant-age floor: do not fire idle_machine for very young tenants
# because there is no activity baseline yet (spec B.2.idle_machine
# suppression rule).
IDLE_MIN_TENANT_AGE_DAYS = 14


def detect_idle_machine(
    tenant_id: int,
    today: date,
    db: Session,
) -> Optional[SignalResult]:
    """Detect a machine with zero job assignments in the last N days.

    Tier: 2.
    Confidence: high.
    Data: machines, job_assignments, machine_downtimes.
    Suppression: skip non-operational machines (already known broken),
        skip machines with an open downtime row covering today, skip
        when the tenant itself is < 14 days old.
    Spec: v6_3_11_signals_spec.md B.2 idle_machine.

    Called by:    composer.compose_briefing via ALL_DETECTORS.
    Calls into:   Machine ORM, JobAssignment ORM, MachineDowntime ORM.
    Side effects: none — pure read.
    """
    if not _tenant_old_enough(tenant_id, today, db, IDLE_MIN_TENANT_AGE_DAYS):
        return None

    machines: list[Machine] = (
        db.query(Machine)
        .filter(Machine.tenant_id == tenant_id)
        .all()
    )
    if not machines:
        return None

    cutoff_dt = datetime.combine(today - timedelta(days=IDLE_WINDOW_DAYS), time.min)
    down_machine_ids = _machines_with_open_downtime(tenant_id, today, db)

    idle_candidates: list[tuple[int, Machine]] = []
    for m in machines:
        if not status_in(m.status, IDLE_OK_STATUSES):
            continue
        if m.id in down_machine_ids:
            continue

        last_assignment_at = _machine_last_assigned_at(tenant_id, m.id, cutoff_dt, db)
        if last_assignment_at is not None:
            continue

        # No assignment in window → idle. Score by how stale the most
        # recent assignment is, capped to IDLE_WINDOW_DAYS for sanity.
        most_recent = _machine_most_recent_assigned_at(tenant_id, m.id, db)
        if most_recent is None:
            idle_days = IDLE_WINDOW_DAYS
        else:
            mr = most_recent
            if mr.tzinfo is not None:
                mr = mr.replace(tzinfo=None)
            idle_days = (datetime.combine(today, time.min) - mr).days
            idle_days = max(IDLE_WINDOW_DAYS, idle_days)
        idle_candidates.append((idle_days, m))

    if not idle_candidates:
        return None

    idle_candidates.sort(key=lambda pair: (-pair[0], pair[1].id))
    days_idle, worst = idle_candidates[0]

    return SignalResult(
        signal_id=IDLE_SIGNAL_ID,
        category=CATEGORY,
        tier=IDLE_TIER,
        confidence=IDLE_CONFIDENCE,
        subject_entity_type="machine",
        subject_entity_id=worst.id,
        severity_score=float(days_idle),
        message_hi_en=(
            f"{worst.name} ek hafte se khali hai — koi job dena hai?"
        ),
        message_en=(
            f"{worst.name} has had no assignment in the last "
            f"{IDLE_WINDOW_DAYS} days."
        ),
        cooldown_days=IDLE_COOLDOWN_DAYS,
    )


# ---------------------------------------------------------------------------
# detect_low_utilization
# ---------------------------------------------------------------------------

LOW_UTIL_SIGNAL_ID = "low_utilization"
LOW_UTIL_TIER = 3
LOW_UTIL_CONFIDENCE = "medium"
LOW_UTIL_COOLDOWN_DAYS = 7
LOW_UTIL_WINDOW_DAYS = 7
LOW_UTIL_THRESHOLD = 0.30
# Available hours per day used as the baseline for utilisation %.
LOW_UTIL_BASE_HOURS_PER_DAY = 8.0


def detect_low_utilization(
    tenant_id: int,
    today: date,
    db: Session,
) -> Optional[SignalResult]:
    """Detect a machine whose scheduled hours fall below 30% of capacity.

    Tier: 3.
    Confidence: medium (job-day arithmetic is approximate).
    Data: machines, job_assignments, jobs (date range + hours/day).
    Suppression: same as idle_machine plus self-suppress when the
        same machine is already firing idle_machine — the composer's
        diversity rule keeps one signal per category, idle_machine is
        higher-tier so it would win anyway, but we drop this one
        first to keep the candidate list clean.
    Spec: v6_3_11_signals_spec.md B.2 low_utilization.
    """
    if not _tenant_old_enough(tenant_id, today, db, IDLE_MIN_TENANT_AGE_DAYS):
        return None

    machines: list[Machine] = (
        db.query(Machine)
        .filter(Machine.tenant_id == tenant_id)
        .all()
    )
    if not machines:
        return None

    window_start = today - timedelta(days=LOW_UTIL_WINDOW_DAYS)
    cutoff_dt = datetime.combine(window_start, time.min)
    capacity_hours = LOW_UTIL_BASE_HOURS_PER_DAY * float(LOW_UTIL_WINDOW_DAYS)
    if capacity_hours <= 0:
        return None

    down_machine_ids = _machines_with_open_downtime(tenant_id, today, db)

    util_candidates: list[tuple[float, Machine]] = []
    for m in machines:
        if not status_in(m.status, IDLE_OK_STATUSES):
            continue
        if m.id in down_machine_ids:
            continue

        # Self-suppress: if idle_machine would fire (no assignments in
        # the window) we skip low_utilization. This avoids duplicate
        # machine signals competing inside one category slot.
        if _machine_last_assigned_at(tenant_id, m.id, cutoff_dt, db) is None:
            continue

        scheduled_hours = _machine_scheduled_hours_in_window(
            tenant_id, m.id, window_start, today, db,
        )
        ratio = scheduled_hours / capacity_hours
        if ratio >= LOW_UTIL_THRESHOLD:
            continue
        util_candidates.append((ratio, m))

    if not util_candidates:
        return None

    util_candidates.sort(key=lambda pair: (pair[0], pair[1].id))
    worst_ratio, worst = util_candidates[0]
    pct = max(0, int(round(worst_ratio * 100)))

    return SignalResult(
        signal_id=LOW_UTIL_SIGNAL_ID,
        category=CATEGORY,
        tier=LOW_UTIL_TIER,
        confidence=LOW_UTIL_CONFIDENCE,
        subject_entity_type="machine",
        subject_entity_id=worst.id,
        # Severity inverts ratio so smaller utilisation → larger
        # severity, matching the escalation rule's "worse fires again"
        # semantics.
        severity_score=float(round((1.0 - worst_ratio) * 100, 2)),
        message_hi_en=(
            f"{worst.name} pichhle hafte sirf {pct}% busy thi."
        ),
        message_en=(
            f"{worst.name} was only {pct}% utilised over the last "
            f"{LOW_UTIL_WINDOW_DAYS} days."
        ),
        cooldown_days=LOW_UTIL_COOLDOWN_DAYS,
    )


# ---------------------------------------------------------------------------
# detect_status_change_alert
# ---------------------------------------------------------------------------

STATUS_CHANGE_SIGNAL_ID = "status_change_alert"
STATUS_CHANGE_TIER = 3
STATUS_CHANGE_CONFIDENCE = "low"
STATUS_CHANGE_COOLDOWN_DAYS = 1
STATUS_CHANGE_WINDOW_HOURS = 24


def detect_status_change_alert(
    tenant_id: int,
    today: date,
    db: Session,
) -> Optional[SignalResult]:
    """Detect a machine that flipped to non-operational in the last 24h.

    Tier: 3.
    Confidence: low — updated_at refreshes on any column edit, not
        just status flips. Future fix is a machine.status_changed
        event log; until then the false-positive rate is acceptable
        only inside tier 3.
    Data: machines.updated_at, machines.status.
    Suppression: skip machines whose status is operational (no flip
        to flag). When multiple machines qualify, the most-recently-
        changed one wins and its name appears in the message.
    Spec: v6_3_11_signals_spec.md B.2 status_change_alert.
    """
    cutoff_dt = datetime.combine(today, time.min) - timedelta(hours=STATUS_CHANGE_WINDOW_HOURS)

    machines: list[Machine] = (
        db.query(Machine)
        .filter(Machine.tenant_id == tenant_id)
        .all()
    )
    flipped: list[Machine] = []
    for m in machines:
        if status_in(m.status, IDLE_OK_STATUSES):
            continue
        if m.updated_at is None:
            continue
        ua = m.updated_at
        if ua.tzinfo is not None:
            ua = ua.replace(tzinfo=None)
        if ua < cutoff_dt:
            continue
        flipped.append(m)

    if not flipped:
        return None

    flipped.sort(
        key=lambda x: (
            -(x.updated_at.replace(tzinfo=None).timestamp()
              if x.updated_at and x.updated_at.tzinfo
              else x.updated_at.timestamp() if x.updated_at else 0.0),
            x.id,
        ),
    )
    worst = flipped[0]
    status_label = (worst.status or "").strip() or "non-operational"

    return SignalResult(
        signal_id=STATUS_CHANGE_SIGNAL_ID,
        category=CATEGORY,
        tier=STATUS_CHANGE_TIER,
        confidence=STATUS_CHANGE_CONFIDENCE,
        subject_entity_type="machine",
        subject_entity_id=worst.id,
        severity_score=1.0,
        message_hi_en=(
            f"{worst.name} ka status '{status_label}' hua. "
            f"Kab tak theek ho jaayegi?"
        ),
        message_en=(
            f"{worst.name} flipped to '{status_label}' in the last "
            f"{STATUS_CHANGE_WINDOW_HOURS} hours."
        ),
        cooldown_days=STATUS_CHANGE_COOLDOWN_DAYS,
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _tenant_old_enough(
    tenant_id: int,
    today: date,
    db: Session,
    min_age_days: int,
) -> bool:
    """True when tenant.created_at is at least min_age_days before today.

    Called by:    detect_idle_machine, detect_low_utilization (this file)
                  to enforce the spec B.2 "skip in tenant's first 14 days"
                  suppression rule.
    Calls into:   Tenant ORM read (local import to avoid an import-time
                  cycle with app.models.auth).
    Side effects: read-only.

    Returns True (permissive) when the tenant row is missing a
    created_at value — degrade open rather than silently suppressing
    legitimate signals when the column is null.
    """
    from app.models.auth import Tenant  # local import to avoid cycles

    tenant = db.query(Tenant).filter(Tenant.id == tenant_id).first()
    if tenant is None:
        return False
    created = getattr(tenant, "created_at", None)
    if created is None:
        return True
    if isinstance(created, datetime):
        created_date = created.date()
    elif isinstance(created, date):
        created_date = created
    else:
        return True
    return (today - created_date).days >= min_age_days


def _machines_with_open_downtime(
    tenant_id: int,
    today: date,
    db: Session,
) -> set[int]:
    """Set of machine_ids whose machine_downtimes row covers `today`.

    Called by:    detect_idle_machine, detect_low_utilization (this file)
                  to suppress signals on machines the owner has already
                  flagged out.
    Calls into:   MachineDowntime ORM (read-only).
    Side effects: none.
    """
    rows = (
        db.query(MachineDowntime.machine_id)
        .filter(
            MachineDowntime.tenant_id == tenant_id,
            MachineDowntime.start_date <= today,
            MachineDowntime.end_date >= today,
        )
        .all()
    )
    return {r[0] for r in rows if r[0] is not None}


def _machine_last_assigned_at(
    tenant_id: int,
    machine_id: int,
    cutoff_dt: datetime,
    db: Session,
) -> Optional[datetime]:
    """Most recent JobAssignment.assigned_at within window, else None.

    Called by:    detect_idle_machine (negative test — None means idle)
                  and detect_low_utilization (positive test — non-None
                  means at least one assignment exists in the window so
                  the utilisation arithmetic is meaningful).
    Calls into:   JobAssignment ORM (read-only).
    Side effects: none.
    """
    row = (
        db.query(JobAssignment.assigned_at)
        .filter(
            JobAssignment.tenant_id == tenant_id,
            JobAssignment.machine_id == machine_id,
            JobAssignment.assigned_at.isnot(None),
            JobAssignment.assigned_at >= cutoff_dt,
        )
        .order_by(JobAssignment.assigned_at.desc())
        .first()
    )
    return row[0] if row else None


def _machine_most_recent_assigned_at(
    tenant_id: int,
    machine_id: int,
    db: Session,
) -> Optional[datetime]:
    """Most recent JobAssignment.assigned_at all-time, else None.

    Called by:    detect_idle_machine (this file) — used to compute the
                  severity score (days since the very last assignment)
                  when the in-window query returned None.
    Calls into:   JobAssignment ORM (read-only).
    Side effects: none.
    """
    row = (
        db.query(JobAssignment.assigned_at)
        .filter(
            JobAssignment.tenant_id == tenant_id,
            JobAssignment.machine_id == machine_id,
            JobAssignment.assigned_at.isnot(None),
        )
        .order_by(JobAssignment.assigned_at.desc())
        .first()
    )
    return row[0] if row else None


def _machine_scheduled_hours_in_window(
    tenant_id: int,
    machine_id: int,
    window_start: date,
    window_end: date,
    db: Session,
) -> float:
    """Total scheduled hours for a machine across [window_start, window_end].

    Called by:    detect_low_utilization (this file) — the numerator of
                  the utilisation ratio.
    Calls into:   Job + JobAssignment ORM (read-only join).
    Side effects: none.

    Hours-per-day is read from Job.estimated_hours_per_day and
    multiplied by the count of overlapping days that fall inside the
    window. Jobs that don't overlap the window contribute zero.
    """
    rows = (
        db.query(Job)
        .join(JobAssignment, JobAssignment.job_id == Job.id)
        .filter(
            JobAssignment.tenant_id == tenant_id,
            JobAssignment.machine_id == machine_id,
            Job.tenant_id == tenant_id,
            Job.start_date <= window_end,
            Job.end_date >= window_start,
        )
        .all()
    )
    total = 0.0
    for j in rows:
        overlap_start = max(j.start_date, window_start)
        overlap_end = min(j.end_date, window_end)
        if overlap_end < overlap_start:
            continue
        days = (overlap_end - overlap_start).days + 1
        per_day = float(j.estimated_hours_per_day or 0.0)
        total += per_day * days
    return total
