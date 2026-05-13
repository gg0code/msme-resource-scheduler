# app/services/day7_insight.py
# Branch: v5-whatsapp
# Iteration: v6.3.16 (Day-7 First-Insight Gate)
#
# FILE PURPOSE
# Owner-side "wow" message that fires once per tenant on the 7th day of
# delivered morning briefings. The dispatcher calls evaluate_and_send()
# on every 5-minute tick; this module decides whether the gate is due,
# picks the strongest of four signals (attendance pattern → skill
# bottleneck → machine spread → recurring customer name) or the
# "routine set" fallback, sends one WhatsApp message per top-tier
# recipient, and records the firing in tenants.engagement_ladder_state
# so the gate can never fire twice.
#
# WHO CALLS THIS FILE
# - app/services/briefings/dispatcher.py — dispatch_due_briefings calls
#   evaluate_and_send(tenant_id, db) immediately after a successful
#   morning dispatch (kind == 'morning', sent_count >= 1). Late import
#   to avoid the briefings.dispatcher → day7_insight → briefings.dispatcher
#   cycle on resolve_recipients.
# - tests/services/test_day7_insight.py — unit tests build attendance,
#   skill, machine, and customer fixtures and call evaluate_and_send
#   to assert which signal fires and what message text is sent.
#
# WHAT THIS FILE CALLS
# - app/services/day7_thresholds.py — every numeric knob lives there.
# - app/services/briefings/dispatcher.resolve_recipients — top-tier
#   subscribed users with linked WhatsApp numbers.
# - app/services/briefings/templates.industry_labels — vertical-aware
#   vocabulary for the machine-utilisation message.
# - app/services/whatsapp_alerts._send_alert — late-imported per-send
#   so a circular import via the alert scheduler is impossible. Mock-
#   mode aware; never raises.
# - app/models.{auth.Tenant, auth.User, employee.Employee,
#   machine.Machine, job.Job/JobAssignment/JobSkillRequirement,
#   skill.Skill, event.Event, extraction_candidate.ExtractionCandidate,
#   whatsapp.PhoneTenantMap}.
# - sqlalchemy ORM read queries; one tenant-row update for the
#   engagement_ladder_state JSONB write.
#
# KEY DESIGN DECISIONS
# - Idempotency lives in tenants.engagement_ladder_state['day7_owner_sent_at'].
#   Presence of the key means the gate has been processed (sent OR
#   suppressed). evaluate_and_send is otherwise a no-op.
# - Two skip paths bypass the gate without writing the ledger:
#     1. tenant.first_briefing_sent_at IS NULL — never received a
#        morning briefing, so the day-counting anchor does not exist.
#     2. day_count < 7 — too early.
#   In both cases the gate stays eligible for a future tick.
# - Two skip paths DO write the ledger (so the gate can never fire
#   later):
#     1. day_count > SUPPRESS_IF_DAY_COUNT_OVER (14) — the back-fill
#        anchored an existing tenant too far in the past; sending a
#        post-hoc Day-7 message would be confusing.
#     2. Successful send to >= 1 recipient — normal happy path.
# - Send failures do NOT write the ledger. The gate retries on the
#   next morning tick (which keeps day_count <= 14 for a few days).
#   A persistent failure eventually trips the > 14-day suppression
#   path and silently retires the gate — better than infinite retries.
# - Signal priority: attendance → skill bottleneck → machine spread
#   → recurring customer → fallback. First signal that crosses
#   threshold wins. Spec Section "Signals to evaluate, in priority
#   order".
# - All threshold values come from day7_thresholds.py. Adding logic
#   constants here is forbidden — every knob must be tunable without
#   re-reading this file.
# - Industry vocabulary (presses vs reactors vs assets) is applied
#   only to the machine-utilisation message, which is the only one
#   that names the resource type. Names of people and customers are
#   passed through verbatim.
# - All four detector functions are pure reads. Only the tenant ledger
#   write + the audit Event row write happen at the end of
#   evaluate_and_send, both on the caller-supplied session. Caller
#   commits.
#
# FORWARD-COMPAT
# - v6.4.0 engagement ladder will add Day-1, Day-3, Day-7-manager,
#   conditional-nudge messages. Each will get its own module that
#   reads/writes its own key in engagement_ladder_state. The four
#   signal detectors here can stay; the message composer and
#   evaluator harness move into engagement_ladder/. day7_thresholds
#   moves with them. v6.4.0 also gets to retire the existing
#   detect_day_7 marker in briefing_intelligence/catalog/tenancy.py
#   (which currently fires on the same day as a generic celebration
#   line — duplication is acceptable in v6.3.16 per the spec).

import logging
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta, timezone
from typing import Any, Awaitable, Callable, Optional
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.auth import Tenant
from app.models.employee import Employee
from app.models.event import Event
from app.models.extraction_candidate import ExtractionCandidate
from app.models.job import Job, JobAssignment, JobSkillRequirement
from app.models.machine import Machine
from app.models.skill import Skill
from app.services.briefings.templates import industry_labels
from app.services.day7_thresholds import (
    ATTENDANCE_MIN_ABSENT_DAYS_PER_WORKER,
    ATTENDANCE_MIN_WORKERS_SAME_WEEKDAY,
    CUSTOMER_RECURRING_ALIAS_MIN_OVERLAP,
    CUSTOMER_RECURRING_MIN_MENTIONS,
    LOOKBACK_DAYS,
    MACHINE_UTILISATION_MIN_HOURS_PER_DAY,
    MACHINE_UTILISATION_MIN_MACHINES,
    MACHINE_UTILISATION_RATIO_THRESHOLD,
    SKILL_BOTTLENECK_MIN_JOBS,
    SKILL_BOTTLENECK_RATIO,
    SUPPRESS_IF_DAY_COUNT_OVER,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Public constants
# ---------------------------------------------------------------------------

# Key written into tenants.engagement_ladder_state when the gate has
# been processed. Value is an ISO-8601 UTC timestamp string.
LADDER_KEY_DAY7_SENT: str = "day7_owner_sent_at"

# Audit event type names. extraction.* / briefing.* are already taken;
# engagement.* is the namespace v6.4.0 will reuse for the rest of the
# ladder. Naming here so v6.4.0 inherits the convention.
EVENT_DAY7_SENT:       str = "engagement.day7_owner_sent"
EVENT_DAY7_SUPPRESSED: str = "engagement.day7_owner_suppressed"
EVENT_DAY7_FAILED:     str = "engagement.day7_owner_failed"

# Stable signal IDs — flow into the audit payload so future telemetry
# can group "which signal won how often". Match the priority order in
# the spec.
SIGNAL_ATTENDANCE: str = "attendance_pattern"
SIGNAL_SKILL:      str = "skill_bottleneck"
SIGNAL_MACHINE:    str = "machine_utilisation"
SIGNAL_CUSTOMER:   str = "recurring_customer"
SIGNAL_FALLBACK:   str = "routine_set"

ALERT_TYPE: str = "day7_owner_gate"

# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------

@dataclass
class SignalCandidate:
    """One detector's verdict.

    Used by:
        Detector functions return SignalCandidate(fired=False) when
        they are below threshold and SignalCandidate(fired=True, ...)
        when the signal qualifies. The evaluator picks the first
        fired candidate in priority order.

    Fields:
        fired:      True iff the signal crosses its threshold and
                    the gate should compose this message.
        signal_id:  One of SIGNAL_* constants. Stable across renames.
        message:    The composed body text, ready to send.
        payload:    Free-form audit detail merged into the
                    engagement.day7_owner_sent event. Lets future
                    telemetry analyse which thresholds fired without
                    re-running the detectors.
    """
    fired: bool
    signal_id: str = ""
    message: str = ""
    payload: dict[str, Any] = field(default_factory=dict)


@dataclass
class Day7Result:
    """Outcome of one evaluate_and_send call.

    Used by:
        Tests assert on .signal_id and .sent_count. The dispatcher
        ignores the return value (the gate is fire-and-forget).

    Fields:
        signal_id:    SIGNAL_* constant of the message that won, or
                      empty string when the gate was skipped.
        sent_count:   Number of recipients the message reached. Zero
                      on skip OR on a fan-out that found no eligible
                      recipients.
        skipped:      Reason string when the gate did not fire:
                      'no_anchor', 'too_early', 'already_sent',
                      'suppressed_too_late', 'no_recipients',
                      'send_failed'. Empty on a successful send.
    """
    signal_id: str = ""
    sent_count: int = 0
    skipped: str = ""


# Send-function signature mirrors the briefings dispatcher's so tests
# can inject a fake. (phone_number, message, alert_type) -> awaitable.
SendFn = Callable[[str, str, str], Awaitable[None]]


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

async def evaluate_and_send(
    tenant_id: int,
    db: Session,
    *,
    now_utc: Optional[datetime] = None,
    send_fn: Optional[SendFn] = None,
) -> Day7Result:
    """Evaluate Day-7 eligibility for one tenant and, if eligible, send.

    Called by:
        app.services.briefings.dispatcher.dispatch_due_briefings
        (immediately after a successful morning dispatch for this
        tenant). Tests call it directly with a stubbed send_fn.

    Calls into:
        - _compute_day_count (this file)
        - _detect_attendance_signal (this file)
        - _detect_skill_bottleneck (this file)
        - _detect_machine_utilisation (this file)
        - _detect_recurring_customer (this file)
        - _compose_fallback_message (this file)
        - _resolve_recipients_for_tenant (this file)
        - _record_outcome (this file) — writes the engagement-ladder
          state + audit event on the caller's session.
        - send_fn (defaults to _default_send → _send_alert →
          _send_whatsapp_message; mock-aware, never raises).

    Side effects:
        - At most one ledger update on tenants.engagement_ladder_state
          (key 'day7_owner_sent_at').
        - At most one audit Event row (engagement.day7_owner_*).
        - Up to N WhatsApp sends (one per resolved recipient).
        - Caller commits. This function never commits.

    Args:
        tenant_id: Tenant to evaluate. The tenant must exist; missing
                   IDs return Day7Result(skipped='no_anchor') so a
                   stale ID cannot crash the dispatcher.
        db:        Sync SQLAlchemy session. Caller commits.
        now_utc:   UTC anchor for the day-count computation. Defaults
                   to datetime.now(tz=utc). Tests pin a fixed value
                   so day_count assertions are deterministic.
        send_fn:   Async (phone, message, alert_type) callable. None
                   resolves to _default_send which routes through
                   _send_alert. Tests pass an in-memory recorder.

    Returns:
        Day7Result describing what happened. Never raises — every
        internal exception is logged and converted to
        Day7Result(skipped='send_failed') so a misbehaving detector
        cannot break the dispatcher tick.
    """
    if now_utc is None:
        now_utc = datetime.now(timezone.utc)

    tenant = db.get(Tenant, tenant_id)
    if tenant is None:
        logger.info("Day-7 gate: tenant %s not found; skipping.", tenant_id)
        return Day7Result(skipped="no_anchor")

    # Already processed (sent or suppressed) — never fire twice.
    state = tenant.engagement_ladder_state or {}
    if state.get(LADDER_KEY_DAY7_SENT):
        return Day7Result(skipped="already_sent")

    # No anchor → no day count → nothing to do this tick.
    if tenant.first_briefing_sent_at is None:
        return Day7Result(skipped="no_anchor")

    today_local, day_count = _compute_day_count(tenant, now_utc)
    if day_count < LOOKBACK_DAYS:
        return Day7Result(skipped="too_early")

    if day_count > SUPPRESS_IF_DAY_COUNT_OVER:
        # Existing pilot tenant — anchor is too far back; mark fired
        # without sending so the gate retires permanently for them.
        _record_outcome(
            db,
            tenant=tenant,
            now_utc=now_utc,
            event_type=EVENT_DAY7_SUPPRESSED,
            payload={
                "day_count": day_count,
                "reason":    "anchor_older_than_suppression_window",
            },
        )
        logger.info(
            "Day-7 gate: tenant %s suppressed (day_count=%s > %s).",
            tenant_id, day_count, SUPPRESS_IF_DAY_COUNT_OVER,
        )
        return Day7Result(signal_id="", sent_count=0, skipped="suppressed_too_late")

    # Pick the highest-priority signal that fires, else fallback.
    candidate = _select_signal(tenant=tenant, today=today_local, db=db)

    # Resolve recipients. No fan-out, no point composing.
    recipients = _resolve_recipients_for_tenant(tenant_id, db)
    if not recipients:
        # Do NOT mark the ledger — the gate stays eligible for a
        # later tick where a recipient may have been linked.
        logger.info(
            "Day-7 gate: tenant %s has no eligible recipients; skipping.",
            tenant_id,
        )
        return Day7Result(skipped="no_recipients")

    real_send = send_fn if send_fn is not None else _default_send

    sent_count = 0
    send_errors: list[str] = []
    for phone in recipients:
        try:
            await real_send(phone, candidate.message, ALERT_TYPE)
            sent_count += 1
        except Exception as exc:  # noqa: BLE001 - never raise to dispatcher
            logger.exception(
                "Day-7 send failed: tenant=%s phone=****%s signal=%s",
                tenant_id, phone[-4:] if phone else "????", candidate.signal_id,
            )
            send_errors.append(f"{type(exc).__name__}: {exc}"[:200])

    if sent_count == 0:
        # Total fan-out failure. Do not touch the ledger so the next
        # morning tick retries.
        _record_outcome(
            db,
            tenant=tenant,
            now_utc=now_utc,
            event_type=EVENT_DAY7_FAILED,
            payload={
                "day_count":   day_count,
                "signal_id":   candidate.signal_id,
                "errors":      send_errors,
                "recipient_count": len(recipients),
            },
            mark_ledger=False,
        )
        return Day7Result(
            signal_id=candidate.signal_id,
            sent_count=0,
            skipped="send_failed",
        )

    # Happy path — at least one recipient received the message.
    _record_outcome(
        db,
        tenant=tenant,
        now_utc=now_utc,
        event_type=EVENT_DAY7_SENT,
        payload={
            "day_count":       day_count,
            "signal_id":       candidate.signal_id,
            "signal_payload":  candidate.payload,
            "recipient_count": sent_count,
            "send_errors":     send_errors,
        },
    )
    logger.info(
        "Day-7 gate: tenant %s fired signal=%s recipients=%d.",
        tenant_id, candidate.signal_id, sent_count,
    )
    return Day7Result(signal_id=candidate.signal_id, sent_count=sent_count)


# ---------------------------------------------------------------------------
# Day-count helper
# ---------------------------------------------------------------------------

def _compute_day_count(tenant: Tenant, now_utc: datetime) -> tuple[date, int]:
    """Return (today_in_tenant_tz, calendar-days-since-first-briefing).

    Called by:    evaluate_and_send (this file).
    Calls into:   ZoneInfo (zoneinfo); attribute access on Tenant.
    Side effects: none — read-only.

    Why tenant timezone: "Day 7" is a calendar-day concept relative to
    when the owner's morning briefing started arriving. Computing it in
    UTC drifts by hours either way and breaks the day-7-exact assertion
    on tenants near a UTC midnight boundary.

    A bad timezone string (column held an unresolvable IANA name) falls
    back to UTC with a warning — same approach as briefings/dispatcher
    _tenant_zoneinfo so the two paths agree on what "today" means.
    """
    raw = tenant.briefing_timezone or "UTC"
    try:
        tz = ZoneInfo(raw)
    except Exception as exc:  # noqa: BLE001 - timezone DB miss must not crash
        logger.warning(
            "Day-7 gate: tenant %s briefing_timezone %r unresolvable (%s); "
            "falling back to UTC.",
            tenant.id, raw, exc,
        )
        tz = ZoneInfo("UTC")

    today_local = now_utc.astimezone(tz).date()
    anchor_local = tenant.first_briefing_sent_at.astimezone(tz).date()
    return today_local, (today_local - anchor_local).days


# ---------------------------------------------------------------------------
# Signal selection
# ---------------------------------------------------------------------------

_DETECTOR_ORDER: tuple[Callable[..., SignalCandidate], ...] = ()  # filled below


def _select_signal(
    *,
    tenant: Tenant,
    today: date,
    db: Session,
) -> SignalCandidate:
    """Run detectors in priority order; return the first one that fires.

    Called by:    evaluate_and_send (this file).
    Calls into:   _detect_attendance_signal, _detect_skill_bottleneck,
                  _detect_machine_utilisation, _detect_recurring_customer
                  (this file). On all-None, _compose_fallback_message
                  (this file).
    Side effects: none — pure read pipeline.

    A detector raising is treated as "did not fire" (logged at WARN).
    The gate must never crash because one detector's data is malformed
    — the worst case is a fallback message, which is still useful.
    """
    detectors: tuple[Callable[..., SignalCandidate], ...] = (
        _detect_attendance_signal,
        _detect_skill_bottleneck,
        _detect_machine_utilisation,
        _detect_recurring_customer,
    )
    for detector in detectors:
        try:
            cand = detector(tenant=tenant, today=today, db=db)
        except Exception:  # noqa: BLE001
            logger.exception(
                "Day-7 gate: detector %s raised for tenant %s; treating as no-fire.",
                detector.__name__, tenant.id,
            )
            continue
        if cand.fired:
            return cand

    # Nothing crossed threshold — send the routine-set acknowledgement.
    return _compose_fallback_message(tenant)


# ---------------------------------------------------------------------------
# Signal 1 — attendance pattern
# ---------------------------------------------------------------------------

def _detect_attendance_signal(
    *,
    tenant: Tenant,
    today: date,
    db: Session,
) -> SignalCandidate:
    """Detect "worker absent N+ days" OR "same weekday absent for K+ workers".

    Called by:    _select_signal (this file).
    Calls into:   _attendance_timeline (this file).
    Side effects: none — read-only ORM scans.

    Reads attendance.recorded events written by whatsapp_checkin
    (see briefing_intelligence/catalog/attendance.py for the payload
    schema we share). The two sub-checks fire independently; whichever
    crosses threshold first wins, and a tie chooses the per-worker
    absence message because it is the more actionable one.

    Returns SignalCandidate(fired=False) when neither sub-check
    qualifies. Returns SignalCandidate(fired=True, ...) with a Hinglish
    body, the chosen sub-check id in payload['variant'], and the
    detected counts in payload for downstream analytics.
    """
    timeline = _attendance_timeline(tenant.id, today, LOOKBACK_DAYS, db)
    if not timeline:
        return SignalCandidate(fired=False)

    # Sub-check (a): a single worker absent on >= N of the last 7 working days.
    per_worker: dict[int, int] = defaultdict(int)
    for _d, absent_ids in timeline:
        for emp_id in absent_ids:
            per_worker[emp_id] += 1

    chronic_emp_id: Optional[int] = None
    chronic_days = 0
    for emp_id, days in per_worker.items():
        if days >= ATTENDANCE_MIN_ABSENT_DAYS_PER_WORKER and days > chronic_days:
            chronic_emp_id = emp_id
            chronic_days = days

    if chronic_emp_id is not None:
        emp = db.get(Employee, chronic_emp_id)
        name = emp.full_name if emp is not None else f"employee#{chronic_emp_id}"
        message = (
            f"Pichhle hafte mein {name} {chronic_days} din gayab the. "
            f"Sab theek hai? Reply HELP."
        )
        return SignalCandidate(
            fired=True,
            signal_id=SIGNAL_ATTENDANCE,
            message=message,
            payload={
                "variant":     "chronic_worker",
                "employee_id": chronic_emp_id,
                "absent_days": chronic_days,
                "window_days": LOOKBACK_DAYS,
            },
        )

    # Sub-check (b): the same weekday absent for >= K distinct workers.
    # Group attendance days by ISO weekday; within a weekday, pool the
    # set of distinct absent worker ids. >= K means "K different workers
    # missed at least one of these weekdays".
    by_weekday: dict[int, set[int]] = defaultdict(set)
    for d, absent_ids in timeline:
        if absent_ids:
            by_weekday[d.isoweekday()].update(absent_ids)

    weekday_hit: Optional[int] = None
    weekday_count = 0
    for iso_weekday, worker_ids in by_weekday.items():
        if (
            len(worker_ids) >= ATTENDANCE_MIN_WORKERS_SAME_WEEKDAY
            and len(worker_ids) > weekday_count
        ):
            weekday_hit = iso_weekday
            weekday_count = len(worker_ids)

    if weekday_hit is not None:
        weekday_name = _weekday_label(weekday_hit)
        message = (
            f"Pichhle hafte har {weekday_name} ko {weekday_count} log gayab "
            f"the. Aksar hota hai kya? Reply HELP."
        )
        return SignalCandidate(
            fired=True,
            signal_id=SIGNAL_ATTENDANCE,
            message=message,
            payload={
                "variant":      "weekday_pattern",
                "weekday_iso":  weekday_hit,
                "worker_count": weekday_count,
                "window_days":  LOOKBACK_DAYS,
            },
        )

    return SignalCandidate(fired=False)


def _attendance_timeline(
    tenant_id: int,
    today: date,
    window_days: int,
    db: Session,
) -> list[tuple[date, set[int]]]:
    """Chronological [(working_date, set_of_absent_employee_ids)].

    Called by:    _detect_attendance_signal (this file).
    Calls into:   Event ORM read on event_type='attendance.recorded'.
    Side effects: read-only.

    Mirrors the helper in briefing_intelligence/catalog/attendance.py.
    Duplicated rather than imported because the v6.4.0 file move (this
    file becoming part of engagement_ladder/) should not depend on the
    pattern-briefings package surviving in its current shape.
    """
    cutoff_dt = datetime.combine(
        today - timedelta(days=window_days + 2),
        time.min,
    ).replace(tzinfo=timezone.utc)

    rows = db.execute(
        select(Event).where(
            Event.tenant_id == tenant_id,
            Event.event_type == "attendance.recorded",
            Event.created_at >= cutoff_dt,
        ).order_by(Event.created_at.asc())
    ).scalars().all()

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
        if (today - for_date).days >= window_days:
            continue
        absent_ids = payload.get("absent_employee_ids") or []
        try:
            absent_set = {int(x) for x in absent_ids}
        except (TypeError, ValueError):
            absent_set = set()
        # Last write wins on the (rare) duplicate-for-date case.
        by_date[for_date] = absent_set

    return sorted(by_date.items(), key=lambda pair: pair[0])


def _weekday_label(iso_weekday: int) -> str:
    """ISO weekday number -> capitalised English name.

    Called by:    _detect_attendance_signal (weekday_pattern variant).
    Calls into:   nothing — pure lookup.
    Side effects: none.
    """
    names = {
        1: "Monday", 2: "Tuesday", 3: "Wednesday", 4: "Thursday",
        5: "Friday", 6: "Saturday", 7: "Sunday",
    }
    return names.get(iso_weekday, f"weekday-{iso_weekday}")


# ---------------------------------------------------------------------------
# Signal 2 — skill bottleneck
# ---------------------------------------------------------------------------

def _detect_skill_bottleneck(
    *,
    tenant: Tenant,
    today: date,
    db: Session,
) -> SignalCandidate:
    """One worker handled >= 70% of jobs requiring some skill last week.

    Called by:    _select_signal (this file).
    Calls into:   Job + JobSkillRequirement + JobAssignment + Skill +
                  Employee ORM reads.
    Side effects: none.

    Algorithm:
        1. Find every Job in the look-back window (jobs whose
           start_date overlaps the window OR were created within it).
        2. Group by JobSkillRequirement.skill_id.
        3. For each skill, count jobs and pool the distinct
           JobAssignment.employee_id values. If one employee covers
           >= SKILL_BOTTLENECK_RATIO of the jobs and the per-skill
           job count is >= SKILL_BOTTLENECK_MIN_JOBS, flag.
        4. Multiple skills can qualify; pick the highest concentration
           (ties broken by largest absolute job count).

    Returns SignalCandidate(fired=False) on no qualification or empty
    fixtures (no jobs, no skill reqs, no assignments).
    """
    window_start = today - timedelta(days=LOOKBACK_DAYS)

    # Pull jobs whose work happened (or was created) in the window. We
    # include "in flight" jobs because the bottleneck is a current
    # observation, not a completed-only one.
    jobs = db.execute(
        select(Job).where(
            Job.tenant_id == tenant.id,
            Job.start_date <= today,
            Job.end_date >= window_start,
        )
    ).scalars().all()
    if not jobs:
        return SignalCandidate(fired=False)
    job_ids = [j.id for j in jobs]

    # Skill requirements on those jobs.
    requirements = db.execute(
        select(JobSkillRequirement).where(
            JobSkillRequirement.tenant_id == tenant.id,
            JobSkillRequirement.job_id.in_(job_ids),
        )
    ).scalars().all()
    if not requirements:
        return SignalCandidate(fired=False)

    # Assignments on those jobs (employee_id may be None for an
    # unstaffed job — we exclude None from the worker pool).
    assignments = db.execute(
        select(JobAssignment).where(
            JobAssignment.tenant_id == tenant.id,
            JobAssignment.job_id.in_(job_ids),
            JobAssignment.employee_id.is_not(None),
        )
    ).scalars().all()
    if not assignments:
        return SignalCandidate(fired=False)

    # employee_id -> set of job_ids
    emp_jobs: dict[int, set[int]] = defaultdict(set)
    for a in assignments:
        emp_jobs[a.employee_id].add(a.job_id)

    # skill_id -> set of job_ids that require it
    skill_jobs: dict[int, set[int]] = defaultdict(set)
    for r in requirements:
        skill_jobs[r.skill_id].add(r.job_id)

    best: Optional[tuple[int, int, int, float]] = None  # (skill, emp, count, ratio)
    for skill_id, jids in skill_jobs.items():
        if len(jids) < SKILL_BOTTLENECK_MIN_JOBS:
            continue
        # For each employee, how many of THIS skill's jobs they touched.
        per_emp: dict[int, int] = {}
        for emp_id, e_jobs in emp_jobs.items():
            overlap = len(e_jobs & jids)
            if overlap:
                per_emp[emp_id] = overlap
        if not per_emp:
            continue
        top_emp_id, top_count = max(per_emp.items(), key=lambda kv: kv[1])
        ratio = top_count / len(jids)
        if ratio < SKILL_BOTTLENECK_RATIO:
            continue
        if best is None or (ratio, top_count) > (best[3], best[2]):
            best = (skill_id, top_emp_id, top_count, ratio)

    if best is None:
        return SignalCandidate(fired=False)

    skill_id, emp_id, count, ratio = best
    skill = db.get(Skill, skill_id)
    emp = db.get(Employee, emp_id)
    skill_name = skill.name if skill is not None else f"skill#{skill_id}"
    emp_name = emp.full_name if emp is not None else f"employee#{emp_id}"
    pct = int(round(ratio * 100))
    total_jobs = len(skill_jobs[skill_id])
    message = (
        f"{emp_name} ne {skill_name} wale {pct}% kaam akele kiye pichhle "
        f"hafte ({count}/{total_jobs}). Backup banaye? Reply HELP."
    )
    return SignalCandidate(
        fired=True,
        signal_id=SIGNAL_SKILL,
        message=message,
        payload={
            "skill_id":    skill_id,
            "employee_id": emp_id,
            "covered":     count,
            "total":       total_jobs,
            "ratio":       round(ratio, 3),
            "window_days": LOOKBACK_DAYS,
        },
    )


# ---------------------------------------------------------------------------
# Signal 3 — machine utilisation spread
# ---------------------------------------------------------------------------

def _detect_machine_utilisation(
    *,
    tenant: Tenant,
    today: date,
    db: Session,
) -> SignalCandidate:
    """Detect a >= 4x spread between most-used and least-used machine.

    Called by:    _select_signal (this file).
    Calls into:   schedule_entries reflection via late import (shape:
                  tenant_id, assigned_machine_ids ARRAY, scheduled_start,
                  scheduled_end). The ScheduleEntryModel class lives in
                  app/routers/scheduler_router.py — late-imported so
                  this module does not pull a router at import time.
                  Falls back to a JobAssignment-based proxy when the
                  schedule_entries table is unreachable (e.g. fresh
                  test DB that did not run the scheduling migrations).
    Side effects: none.

    Algorithm:
        1. Sum (scheduled_end - scheduled_start) hours per machine
           across schedule_entries that overlap the look-back.
        2. Divide by LOOKBACK_DAYS to get hours/day.
        3. Drop machines with hours/day < MIN_HOURS_PER_DAY (the
           "least-used floor" — stops a 6-minute outlier from
           collapsing the ratio denominator).
        4. If at least MIN_MACHINES survive and max/min >= ratio
           threshold, fire.

    Returns SignalCandidate(fired=False) on empty schedule_entries
    or when the surviving machine count is below the floor.
    """
    window_start_local = today - timedelta(days=LOOKBACK_DAYS)
    window_start_dt = datetime.combine(window_start_local, time.min)
    today_dt = datetime.combine(today + timedelta(days=1), time.min)

    try:
        from app.routers.scheduler_router import ScheduleEntryModel
    except Exception:  # noqa: BLE001
        # Router import failure should not crash the gate. No schedule
        # data → no machine signal — fall through.
        logger.exception(
            "Day-7 gate: ScheduleEntryModel unavailable for tenant %s.",
            tenant.id,
        )
        return SignalCandidate(fired=False)

    try:
        rows = db.execute(
            select(ScheduleEntryModel).where(
                ScheduleEntryModel.tenant_id == tenant.id,
                ScheduleEntryModel.scheduled_end >= window_start_dt,
                ScheduleEntryModel.scheduled_start < today_dt,
            )
        ).scalars().all()
    except Exception:  # noqa: BLE001
        # On a test DB that has never created schedule_entries the
        # query raises; treat as "no data" and let another signal
        # decide.
        logger.exception(
            "Day-7 gate: schedule_entries query failed for tenant %s.",
            tenant.id,
        )
        return SignalCandidate(fired=False)

    if not rows:
        return SignalCandidate(fired=False)

    hours_per_machine: dict[int, float] = defaultdict(float)
    for row in rows:
        machine_ids = list(row.assigned_machine_ids or [])
        if not machine_ids:
            continue
        # Clip the entry to the look-back window so an entry that
        # straddles the boundary contributes only its in-window hours.
        eff_start = max(row.scheduled_start, window_start_dt)
        eff_end = min(row.scheduled_end, today_dt)
        if eff_end <= eff_start:
            continue
        hours = (eff_end - eff_start).total_seconds() / 3600.0
        for mid in machine_ids:
            hours_per_machine[int(mid)] += hours

    # Apply the per-day floor. min_hours candidates must be at least
    # MIN_HOURS_PER_DAY × LOOKBACK_DAYS total hours.
    min_total_hours = MACHINE_UTILISATION_MIN_HOURS_PER_DAY * LOOKBACK_DAYS
    eligible: list[tuple[int, float]] = [
        (mid, hrs) for mid, hrs in hours_per_machine.items() if hrs >= min_total_hours
    ]
    if len(eligible) < MACHINE_UTILISATION_MIN_MACHINES:
        return SignalCandidate(fired=False)

    eligible.sort(key=lambda kv: kv[1])
    least_id, least_hours = eligible[0]
    busy_id, busy_hours = eligible[-1]
    if least_hours <= 0:
        return SignalCandidate(fired=False)
    ratio = busy_hours / least_hours
    if ratio < MACHINE_UTILISATION_RATIO_THRESHOLD:
        return SignalCandidate(fired=False)

    busy = db.get(Machine, busy_id)
    least = db.get(Machine, least_id)
    busy_name = busy.name if busy is not None else f"machine#{busy_id}"
    least_name = least.name if least is not None else f"machine#{least_id}"

    labels = industry_labels(getattr(tenant, "industry_type", None))
    machine_singular = labels.get("machine", "machine")
    ratio_str = f"{ratio:.1f}".rstrip("0").rstrip(".")
    message = (
        f"{busy_name} pichhle hafte {ratio_str}x zyada chala {least_name} "
        f"se. Load shift karne ka mauka? ({machine_singular} hours: "
        f"{busy_hours:.1f} vs {least_hours:.1f}.) Reply HELP."
    )
    return SignalCandidate(
        fired=True,
        signal_id=SIGNAL_MACHINE,
        message=message,
        payload={
            "busy_machine_id":  busy_id,
            "least_machine_id": least_id,
            "busy_hours":       round(busy_hours, 2),
            "least_hours":      round(least_hours, 2),
            "ratio":            round(ratio, 2),
            "window_days":      LOOKBACK_DAYS,
            "eligible_count":   len(eligible),
        },
    )


# ---------------------------------------------------------------------------
# Signal 4 — recurring customer name
# ---------------------------------------------------------------------------

def _detect_recurring_customer(
    *,
    tenant: Tenant,
    today: date,
    db: Session,
) -> SignalCandidate:
    """Customer-name extraction-candidate seen >=5 times, not yet a customer.

    Called by:    _select_signal (this file).
    Calls into:   ExtractionCandidate ORM (entity_type='customer'),
                  Job ORM (existing customer text), _alias_overlaps
                  (this file).
    Side effects: none.

    "Not yet in the customers table" maps to "not appearing in
    Job.customer for this tenant" because the schema has no separate
    customers table (Job.customer is free text, see model). The
    additional alias-overlap rule (4-character continuous substring,
    case-insensitive, either direction) catches "Patel Trading Co."
    matching "Patel Traders" and similar.

    Returns SignalCandidate(fired=False) when no candidate qualifies.
    """
    cutoff = datetime.combine(today - timedelta(days=LOOKBACK_DAYS), time.min)
    cutoff = cutoff.replace(tzinfo=timezone.utc)

    candidates = db.execute(
        select(ExtractionCandidate).where(
            ExtractionCandidate.tenant_id == tenant.id,
            ExtractionCandidate.entity_type == "customer",
            ExtractionCandidate.last_seen >= cutoff,
            ExtractionCandidate.mention_count >= CUSTOMER_RECURRING_MIN_MENTIONS,
        )
    ).scalars().all()
    if not candidates:
        return SignalCandidate(fired=False)

    # Pull existing customer strings once per evaluation.
    existing_rows = db.execute(
        select(Job.customer).where(
            Job.tenant_id == tenant.id,
            Job.customer.isnot(None),
        )
    ).all()
    existing_names = {
        row[0].strip() for row in existing_rows
        if row[0] is not None and row[0].strip()
    }

    # Sort candidates by (mention_count DESC, last_seen DESC) so the
    # winner is the most "loud" recent recurrence.
    sorted_cands = sorted(
        candidates,
        key=lambda c: (-int(c.mention_count or 0), -(c.last_seen or cutoff).timestamp()),
    )

    for cand in sorted_cands:
        candidate_name = (cand.normalized_value or cand.raw_value or "").strip()
        if not candidate_name:
            continue
        if _alias_overlaps(candidate_name, existing_names):
            continue
        message = (
            f"{candidate_name} ka naam pichhle hafte {cand.mention_count} "
            f"baar aaya — but customer list mein nahi. Add karna hai? "
            f"Reply HELP."
        )
        return SignalCandidate(
            fired=True,
            signal_id=SIGNAL_CUSTOMER,
            message=message,
            payload={
                "candidate_id":   cand.id,
                "candidate_name": candidate_name,
                "mention_count":  int(cand.mention_count or 0),
                "window_days":    LOOKBACK_DAYS,
            },
        )

    return SignalCandidate(fired=False)


def _alias_overlaps(candidate: str, existing_names: set[str]) -> bool:
    """True iff candidate shares a >=N-char substring with any existing name.

    Called by:    _detect_recurring_customer (this file).
    Calls into:   nothing — pure string scan.
    Side effects: none.

    Comparison is case-insensitive, both directions (candidate-in-
    existing AND existing-in-candidate). The minimum overlap length
    is CUSTOMER_RECURRING_ALIAS_MIN_OVERLAP characters of contiguous
    substring — short enough to catch surname matches ("Patel" = 5
    chars), long enough to skip suffix words ("Co." = 3 chars,
    ignored).

    Exact case-insensitive match short-circuits (a candidate already
    in the customer list is not an alias question).
    """
    cand_lower = candidate.casefold()
    n = CUSTOMER_RECURRING_ALIAS_MIN_OVERLAP
    if len(cand_lower) < n:
        # Too short to share an n-character window — accept as new.
        return False
    for existing in existing_names:
        ex_lower = existing.casefold()
        if not ex_lower:
            continue
        if cand_lower == ex_lower:
            return True
        if len(ex_lower) < n:
            continue
        # Sliding window: does any n-char chunk of one appear in the other?
        if any(
            cand_lower[i:i + n] in ex_lower
            for i in range(len(cand_lower) - n + 1)
        ):
            return True
        if any(
            ex_lower[i:i + n] in cand_lower
            for i in range(len(ex_lower) - n + 1)
        ):
            return True
    return False


# ---------------------------------------------------------------------------
# Fallback — routine set acknowledgement
# ---------------------------------------------------------------------------

def _compose_fallback_message(tenant: Tenant) -> SignalCandidate:
    """Build the "7 days in, routine set" message when no signal qualifies.

    Called by:    _select_signal (this file).
    Calls into:   nothing — string assembly only.
    Side effects: none.

    The body is the romanised-Hindi variant from the spec's
    zetaops_day7_routine_set template. We use the session-message
    path everywhere in v6.3.16; the Meta template is registered as
    a fallback for the 24h-window-expired edge case (registered
    separately as part of ops, not by this code).
    """
    message = (
        "7 din ho gaye. Routine set ho gayi hai. Ab koi bhi unusual "
        "cheez hogi to turant batayenge. Kuch badalne ke liye HELP "
        "bhejein."
    )
    return SignalCandidate(
        fired=True,
        signal_id=SIGNAL_FALLBACK,
        message=message,
        payload={
            "tenant_industry": getattr(tenant, "industry_type", None),
        },
    )


# ---------------------------------------------------------------------------
# Recipient resolution
# ---------------------------------------------------------------------------

def _resolve_recipients_for_tenant(tenant_id: int, db: Session) -> list[str]:
    """List of WhatsApp phone numbers for top-tier subscribed users.

    Called by:    evaluate_and_send (this file).
    Calls into:   briefings.dispatcher.resolve_recipients via late
                  import — same recipient set the morning briefing
                  uses, single source of truth.
    Side effects: read-only.

    Returns an empty list when no eligible recipient exists. The
    caller treats empty as "skip without writing the ledger" so the
    gate stays eligible after a tenant links a phone.
    """
    from app.services.briefings.dispatcher import resolve_recipients
    tenant = db.get(Tenant, tenant_id)
    if tenant is None:
        return []
    rows = resolve_recipients(tenant, db)
    return [r.phone_number for r in rows if r.phone_number]


# ---------------------------------------------------------------------------
# Default send wiring
# ---------------------------------------------------------------------------

async def _default_send(phone_number: str, message: str, alert_type: str) -> None:
    """Late-imported send wiring shared with the briefing dispatcher.

    Called by:    evaluate_and_send (this file) when the caller did
                  not supply a send_fn override.
    Calls into:   app.services.whatsapp_alerts._send_alert (mock-mode
                  aware; routes to _send_whatsapp_message in prod).
    Side effects: WhatsApp send, OR mock-mode log breadcrumb.

    Identical to briefings.dispatcher._default_send — duplicated to
    keep the two send paths import-independent so the briefing
    dispatcher and the Day-7 gate can each be moved between modules
    without dragging the other along.

    v6.3.22 deferral — this path stays free-form. The Day-7 owner
    template (zetaops_owner_day7_insight) is still pending Meta
    approval (CHANGELOG v6.3.21 §4) and the SignalCandidate dataclass
    does not yet carry the 6 positional args the template expects
    (week_label, owner_first_name, pattern, evidence_1, evidence_2,
    action). Routing this caller through whatsapp_send_helper.send_with
    _window_decision will require extending each detector to surface
    its template args; tracked alongside the v6.4.0 engagement-ladder
    work.
    """
    from app.services.whatsapp_alerts import _send_alert  # late: avoids cycle
    await _send_alert(
        phone_number=phone_number, message=message, alert_type=alert_type,
    )


# ---------------------------------------------------------------------------
# Outcome recording
# ---------------------------------------------------------------------------

def _record_outcome(
    db: Session,
    *,
    tenant: Tenant,
    now_utc: datetime,
    event_type: str,
    payload: dict[str, Any],
    mark_ledger: bool = True,
) -> None:
    """Stage an audit event and (optionally) update the tenant ledger.

    Called by:    evaluate_and_send (this file). Three flavours:
                  EVENT_DAY7_SENT       — happy path, ledger marked.
                  EVENT_DAY7_SUPPRESSED — anchor too old, ledger marked.
                  EVENT_DAY7_FAILED     — fan-out flop, ledger NOT marked.
    Calls into:   db.add (Event), tenant attribute reassignment.
    Side effects: stages one Event row; optionally mutates
                  tenant.engagement_ladder_state. Caller commits.

    Why reassign engagement_ladder_state instead of mutating in place:
    SQLAlchemy's JSONB / JSON type does not track in-place dict
    mutations by default. Replacing the dict (or alternatively calling
    flag_modified) is the supported way. We replace because it leaves
    the audit-log payload immune to later in-memory edits on the
    tenant row.
    """
    db.add(Event(
        tenant_id=tenant.id,
        event_type=event_type,
        entity_type="tenant",
        entity_id=tenant.id,
        actor_user_id=None,
        source="system",
        payload=payload,
    ))
    if mark_ledger:
        ts = now_utc.astimezone(timezone.utc).isoformat()
        current = dict(tenant.engagement_ladder_state or {})
        current[LADDER_KEY_DAY7_SENT] = ts
        tenant.engagement_ladder_state = current
