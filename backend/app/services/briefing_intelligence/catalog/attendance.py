# app/services/briefing_intelligence/catalog/attendance.py
# Branch: v5-whatsapp
#
# FILE PURPOSE
# Attendance-category signal evaluators for v6.3.11 pattern briefings:
#   - detect_consecutive_absence (spec B.1.consecutive_absence,
#     tier 1, high — once history is wired)
#   - detect_attendance_ratio_concern (spec B.1.attendance_ratio_concern,
#     tier 2, medium)
#   - detect_new_employee_no_show (spec B.1.new_employee_no_show,
#     tier 2, medium)
#
# WHO CALLS THIS FILE
# - app/services/briefing_intelligence/composer.py — ALL_DETECTORS.
# - tests/services/test_detect_consecutive_absence.py
# - tests/services/test_detect_attendance_ratio_concern.py
# - tests/services/test_detect_new_employee_no_show.py
#
# WHAT THIS FILE CALLS
# - app/models/auth.py — Tenant ORM (quiet-period gate).
# - app/models/employee.py — Employee ORM (worker_type, created_at).
# - app/models/event.py — Event ORM (attendance.recorded payload).
# - app/models/unavailability.py — EmployeeLeave (planned-leave skip).
# - app/services/briefing_intelligence/signals.py — SignalResult.
#
# DESIGN NOTES
# - All three signals read from the events table where event_type =
#   'attendance.recorded'. The payload shape is fixed by
#   whatsapp_checkin.save_checkin_state():
#       {"for_date": "2026-05-04",
#        "absent_employee_ids": [int, ...],
#        "down_machine_ids":   [int, ...]}
#   for_date is the date the manager was reporting on, not the event
#   timestamp. We index attendance by for_date so a check-in submitted
#   late evening still counts toward the morning of that date.
# - "Working day" definition: any date that has at least one
#   attendance.recorded event for this tenant. This is the spec's
#   "weekends without check-ins don't count against absence ratio"
#   rule and means the ratio denominator is exactly the days the
#   manager actually reported.
# - History-dependent: returns None when fewer than 2 working days
#   for consecutive_absence, fewer than 7 for ratio_concern, and 3+
#   working days post-creation for no_show. The composer treats None
#   as "did not fire" so insufficient history is invisible to the
#   downstream selector.
# - Per-employee subject. When multiple employees qualify on the
#   same day, the worst case wins (longest streak, lowest ratio,
#   etc.) and the others are dropped at this layer — the composer's
#   diversity rule would reject same-category siblings anyway.
# - Contractor exclusion (Q8 — "always exclude") is enforced via
#   Employee.worker_type == 'permanent' filter. Spec rationale:
#   contractors have variable presence by design.

import logging
from datetime import date, datetime, timedelta
from typing import Optional

from sqlalchemy.orm import Session

from app.models.auth import Tenant
from app.models.employee import Employee
from app.models.event import Event
from app.models.unavailability import EmployeeLeave
from app.services.briefing_intelligence.signals import SignalResult

logger = logging.getLogger(__name__)

CATEGORY = "attendance"
ATTENDANCE_EVENT_TYPE = "attendance.recorded"
PERMANENT_WORKER_TYPE = "permanent"

# ---------------------------------------------------------------------------
# detect_consecutive_absence
# ---------------------------------------------------------------------------

CONSEC_SIGNAL_ID = "consecutive_absence"
CONSEC_TIER = 1
CONSEC_CONFIDENCE = "high"
CONSEC_COOLDOWN_DAYS = 1
CONSEC_WINDOW_DAYS = 7
CONSEC_MIN_DAYS = 2
# New-joinee skip — employees onboarded inside this window are exempt
# (spec suppression rule B.1).
CONSEC_NEW_JOINEE_DAYS = 7


def detect_consecutive_absence(
    tenant_id: int,
    today: date,
    db: Session,
) -> Optional[SignalResult]:
    """Detect an employee absent N consecutive working days through today.

    Tier: 1 (must fire when triggered — workforce reliability).
    Confidence: high (once attendance history accumulates post-deploy).
    Data: events table (attendance.recorded), employees, employee_leaves.
    Suppression: contractors (Q8), new joinees (< 7 days), planned
        leave covering the dates.
    Spec: v6_3_11_signals_spec.md B.1 consecutive_absence.

    Called by:    composer.compose_briefing via ALL_DETECTORS.
    Calls into:   Event + Employee + EmployeeLeave ORM.
    Side effects: none — pure read.
    """
    timeline = _attendance_timeline(tenant_id, today, CONSEC_WINDOW_DAYS, db)
    if len(timeline) < CONSEC_MIN_DAYS:
        # Insufficient history — return None gracefully.
        return None

    # Most-recent reported date must be today; otherwise "consecutive
    # through today" cannot be computed.
    if timeline[-1][0] != today:
        return None

    # Eligible employees: permanent + onboarded > 7 days ago.
    employees = _eligible_permanent_employees(
        tenant_id, today, CONSEC_NEW_JOINEE_DAYS, db,
    )
    if not employees:
        return None

    # Planned leave map — set of dates per employee where leave was
    # already approved (skip absences on those dates so we don't fire
    # on something the owner already knows).
    leave_dates = _employee_leave_dates(
        tenant_id,
        [e.id for e in employees],
        timeline[0][0],
        today,
        db,
    )

    # Build per-employee streak. Walk timeline newest→oldest; each
    # absent day extends the streak; the first non-absent or planned-
    # leave date breaks it.
    best: Optional[tuple[Employee, int]] = None
    for emp in employees:
        streak = 0
        for d, absent_ids in reversed(timeline):
            if d in leave_dates.get(emp.id, set()):
                # Planned leave breaks the streak (owner knows).
                break
            if emp.id in absent_ids:
                streak += 1
                continue
            break
        if streak >= CONSEC_MIN_DAYS:
            if best is None or streak > best[1]:
                best = (emp, streak)

    if best is None:
        return None

    emp, days = best
    if days == 2:
        message_hi_en = f"{emp.full_name} pichhle 2 din se nahi aaye"
    else:
        message_hi_en = f"{emp.full_name} ab tak {days} din se gayab"
    message_en = f"{emp.full_name} has been absent {days} working days in a row."

    return SignalResult(
        signal_id=CONSEC_SIGNAL_ID,
        category=CATEGORY,
        tier=CONSEC_TIER,
        confidence=CONSEC_CONFIDENCE,
        subject_entity_type="employee",
        subject_entity_id=emp.id,
        severity_score=float(days),
        message_hi_en=message_hi_en,
        message_en=message_en,
        cooldown_days=CONSEC_COOLDOWN_DAYS,
    )


# ---------------------------------------------------------------------------
# detect_attendance_ratio_concern
# ---------------------------------------------------------------------------

RATIO_SIGNAL_ID = "attendance_ratio_concern"
RATIO_TIER = 2
RATIO_CONFIDENCE = "medium"
RATIO_COOLDOWN_DAYS = 7
RATIO_WINDOW_DAYS = 14
RATIO_MIN_HISTORY_DAYS = 7
RATIO_THRESHOLD = 0.60


def detect_attendance_ratio_concern(
    tenant_id: int,
    today: date,
    db: Session,
) -> Optional[SignalResult]:
    """Detect an employee whose 14-day attendance ratio is below 60%.

    Tier: 2.
    Confidence: medium (depends on manager check-in compliance).
    Data: events (attendance.recorded), employees.
    Suppression: < 7 working days of history returns None; new
        joinees inside the consecutive-absence skip window are
        exempt; tenant-wide consecutive_absence overlap is left to
        the composer's diversity rule (categories collide).
    Spec: v6_3_11_signals_spec.md B.1 attendance_ratio_concern.
    """
    timeline = _attendance_timeline(tenant_id, today, RATIO_WINDOW_DAYS, db)
    if len(timeline) < RATIO_MIN_HISTORY_DAYS:
        return None

    employees = _eligible_permanent_employees(
        tenant_id, today, CONSEC_NEW_JOINEE_DAYS, db,
    )
    if not employees:
        return None

    working_days = len(timeline)
    worst: Optional[tuple[Employee, float, int]] = None
    for emp in employees:
        absent_count = sum(
            1 for _d, absent_ids in timeline if emp.id in absent_ids
        )
        present_count = working_days - absent_count
        ratio = present_count / working_days
        if ratio >= RATIO_THRESHOLD:
            continue
        if worst is None or ratio < worst[1]:
            worst = (emp, ratio, present_count)

    if worst is None:
        return None

    emp, ratio, present = worst
    pct = int(round(ratio * 100))

    return SignalResult(
        signal_id=RATIO_SIGNAL_ID,
        category=CATEGORY,
        tier=RATIO_TIER,
        confidence=RATIO_CONFIDENCE,
        subject_entity_type="employee",
        subject_entity_id=emp.id,
        # Lower ratio → higher severity so escalation fires when the
        # ratio worsens.
        severity_score=float(round((1.0 - ratio) * 100, 2)),
        message_hi_en=(
            f"Pichhle 2 hafte mein {emp.full_name} sirf {pct}% present rahe — "
            f"sab theek hai?"
        ),
        message_en=(
            f"{emp.full_name} was only {pct}% present over the last "
            f"{working_days} reported working days."
        ),
        cooldown_days=RATIO_COOLDOWN_DAYS,
    )


# ---------------------------------------------------------------------------
# detect_new_employee_no_show
# ---------------------------------------------------------------------------

NOSHOW_SIGNAL_ID = "new_employee_no_show"
NOSHOW_TIER = 2
NOSHOW_CONFIDENCE = "medium"
NOSHOW_COOLDOWN_DAYS = 999  # single-shot per spec
NOSHOW_NEW_JOINEE_DAYS = 14
NOSHOW_MIN_DAYS_POST_CREATE = 3


def detect_new_employee_no_show(
    tenant_id: int,
    today: date,
    db: Session,
) -> Optional[SignalResult]:
    """Detect a recently-added employee who has never been seen present.

    Tier: 2.
    Confidence: medium.
    Data: employees.created_at, events (attendance.recorded).
    Suppression:
      - Skip if a future-dated employee_leaves row covers today
        (joining late deliberately).
      - Single-shot: cooldown 999 days, fires once per employee.
    Spec: v6_3_11_signals_spec.md B.1 new_employee_no_show.

    Trigger: employee.created_at within the last 14 days, employee
        has been mentioned as absent on every recorded check-in OR
        not mentioned at all for 3+ working days post-creation.
    """
    cutoff_create = today - timedelta(days=NOSHOW_NEW_JOINEE_DAYS)
    new_employees: list[Employee] = (
        db.query(Employee)
        .filter(
            Employee.tenant_id == tenant_id,
            Employee.worker_type == PERMANENT_WORKER_TYPE,
        )
        .all()
    )
    new_employees = [
        e for e in new_employees if _employee_created_within(e, cutoff_create)
    ]
    if not new_employees:
        return None

    # Pull every attendance.recorded event since the earliest new-joinee
    # creation — small set, in-memory bucketing keeps the SQL simple.
    timeline = _attendance_timeline(
        tenant_id, today, NOSHOW_NEW_JOINEE_DAYS + 1, db,
    )

    # Build per-employee leave map for the same window.
    leave_dates = _employee_leave_dates(
        tenant_id,
        [e.id for e in new_employees],
        cutoff_create,
        today,
        db,
    )

    best: Optional[Employee] = None
    best_days_silent = -1
    for emp in new_employees:
        ec = _employee_create_date(emp)
        if ec is None:
            continue
        # Only count working days strictly after creation (creation
        # day itself is the onboarding day, not a working day yet).
        post_create = [
            (d, absent_ids) for d, absent_ids in timeline if d > ec
        ]
        if len(post_create) < NOSHOW_MIN_DAYS_POST_CREATE:
            continue

        # If a leave row covers today the employee is intentionally
        # absent — skip this signal.
        if today in leave_dates.get(emp.id, set()):
            continue

        # Has the employee been mentioned as NOT absent on any of the
        # post-create days? If yes — they've shown up at least once,
        # not a no-show.
        seen_present = False
        for d, absent_ids in post_create:
            if emp.id not in absent_ids:
                seen_present = True
                break
        if seen_present:
            continue

        days_silent = len(post_create)
        if days_silent > best_days_silent:
            best = emp
            best_days_silent = days_silent

    if best is None:
        return None

    n = best_days_silent
    return SignalResult(
        signal_id=NOSHOW_SIGNAL_ID,
        category=CATEGORY,
        tier=NOSHOW_TIER,
        confidence=NOSHOW_CONFIDENCE,
        subject_entity_type="employee",
        subject_entity_id=best.id,
        severity_score=float(n),
        message_hi_en=(
            f"{best.full_name} ko aapne {n} din pehle add kiya — "
            f"kya woh aaye nahi abhi tak?"
        ),
        message_en=(
            f"{best.full_name} was added {n} days ago and has not been "
            f"marked present yet."
        ),
        cooldown_days=NOSHOW_COOLDOWN_DAYS,
    )


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _attendance_timeline(
    tenant_id: int,
    today: date,
    window_days: int,
    db: Session,
) -> list[tuple[date, set[int]]]:
    """Return a chronological list of (working_date, absent_employee_ids).

    Called by:    detect_consecutive_absence, detect_attendance_ratio_concern,
                  detect_new_employee_no_show (all in this file).
    Calls into:   Event ORM read on event_type='attendance.recorded'.
    Side effects: read-only.

    Reads attendance.recorded events from the last `window_days`
    days and indexes them by the payload's `for_date`. Each working
    date appears at most once — when the same date has multiple
    events (manager corrected the check-in mid-day), the most-
    recently-created event wins.
    """
    # Pull the window from the events table. Use a generous lookback
    # against created_at (tz-aware) to catch events written after
    # midnight. The for_date inside the payload is what we index by.
    cutoff_dt = datetime.combine(
        today - timedelta(days=window_days + 2),
        datetime.min.time(),
    )

    rows: list[Event] = (
        db.query(Event)
        .filter(
            Event.tenant_id == tenant_id,
            Event.event_type == ATTENDANCE_EVENT_TYPE,
            Event.created_at >= cutoff_dt,
        )
        .order_by(Event.created_at.asc())
        .all()
    )

    by_date: dict[date, set[int]] = {}
    for ev in rows:
        payload = ev.payload or {}
        for_date_raw = payload.get("for_date")
        if not for_date_raw:
            continue
        try:
            for_date = date.fromisoformat(for_date_raw)
        except (TypeError, ValueError):
            continue
        if for_date > today:
            continue
        if (today - for_date).days > window_days:
            continue
        absent_ids = payload.get("absent_employee_ids") or []
        try:
            absent_set = {int(x) for x in absent_ids}
        except (TypeError, ValueError):
            absent_set = set()
        # Most-recent event wins for a given date.
        by_date[for_date] = absent_set

    return sorted(by_date.items(), key=lambda pair: pair[0])


def _eligible_permanent_employees(
    tenant_id: int,
    today: date,
    new_joinee_skip_days: int,
    db: Session,
) -> list[Employee]:
    """Permanent employees onboarded > N days ago.

    Called by:    detect_consecutive_absence, detect_attendance_ratio_concern
                  (this file). Implements the spec B.1 contractor + new-
                  joinee suppression rules in one helper.
    Calls into:   Employee ORM, _employee_created_within (this file).
    Side effects: read-only.
    """
    cutoff_create = today - timedelta(days=new_joinee_skip_days)
    rows: list[Employee] = (
        db.query(Employee)
        .filter(
            Employee.tenant_id == tenant_id,
            Employee.worker_type == PERMANENT_WORKER_TYPE,
        )
        .all()
    )
    return [e for e in rows if not _employee_created_within(e, cutoff_create)]


def _employee_created_within(employee: Employee, cutoff: date) -> bool:
    """True when employee.created_at >= cutoff (i.e. recently added).

    Called by:    _eligible_permanent_employees, detect_new_employee_no_show
                  (this file).
    Calls into:   _employee_create_date (this file).
    Side effects: none.
    """
    cd = _employee_create_date(employee)
    if cd is None:
        return False
    return cd >= cutoff


def _employee_create_date(employee: Employee) -> Optional[date]:
    """Date portion of employee.created_at, or None when missing.

    Called by:    _employee_created_within, detect_new_employee_no_show
                  (this file).
    Calls into:   nothing — pure attribute access.
    Side effects: none.
    """
    created = getattr(employee, "created_at", None)
    if created is None:
        return None
    if isinstance(created, datetime):
        return created.date()
    if isinstance(created, date):
        return created
    return None


def _employee_leave_dates(
    tenant_id: int,
    employee_ids: list[int],
    window_start: date,
    window_end: date,
    db: Session,
) -> dict[int, set[date]]:
    """Map of employee_id → set of dates covered by EmployeeLeave rows
    overlapping [window_start, window_end].

    Called by:    detect_consecutive_absence, detect_new_employee_no_show
                  (this file). Used by both to skip "absences" the owner
                  has already approved as planned leave.
    Calls into:   EmployeeLeave ORM (read-only).
    Side effects: none.
    """
    if not employee_ids:
        return {}
    rows: list[EmployeeLeave] = (
        db.query(EmployeeLeave)
        .filter(
            EmployeeLeave.tenant_id == tenant_id,
            EmployeeLeave.employee_id.in_(employee_ids),
            EmployeeLeave.start_date <= window_end,
            EmployeeLeave.end_date >= window_start,
        )
        .all()
    )
    out: dict[int, set[date]] = {}
    for r in rows:
        s = max(r.start_date, window_start)
        e = min(r.end_date, window_end)
        if e < s:
            continue
        d = s
        bucket = out.setdefault(r.employee_id, set())
        while d <= e:
            bucket.add(d)
            d = d + timedelta(days=1)
    return out
