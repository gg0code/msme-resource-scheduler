# app/services/consolidated_briefing.py
# Branch: v5-whatsapp
#
# FILE PURPOSE
# v6.3.19 consolidated morning/evening push dispatcher and supporting
# helpers. Three layers in one file:
#
#   1. Selector (slice 1) — select_flag_and_next_step picks the top
#      blocker-class signal and returns (flag_text, next_step_text)
#      for rendering through the v6.3.18 Meta-bound templates.
#
#   2. Field computers (slice 2B) — _compute_jobs_starting,
#      _compute_continuing, _compute_crew_expected. Pure SQL reads,
#      no clock access. Feed the morning briefing's data fields.
#
#   3. Dispatchers (slice 2C) — async dispatch_morning and
#      dispatch_evening. Wire PushConfig + field computers + selector
#      + Meta-bound templates + per-tenant idempotency through to
#      the existing _send_whatsapp_message transport. Targeted by
#      slice 2D's push_v2_tick (shadow mode initially).
#
# WHO CALLS THIS FILE
# - tests/services/test_consolidated_briefing.py
# - (planned) v6.3.19 morning dispatch path — wires this into the
#   template render layer once the consolidated dispatcher lands.
#
# WHAT THIS FILE CALLS
# - app.services.briefing_intelligence.signals.SignalResult (type
#   only — does not invoke detectors or any DB).
#
# DESIGN NOTES
# - Static next_step lookup chosen over extending SignalResult
#   (Choice 1 from the v6.3.19 audit). Smallest blast radius:
#   doesn't touch the 13-evaluator catalog or the 5 xfail tests in
#   the catalog test files. Trade-off: action text lives away from
#   the detector that fires it; future tone refresh updates one
#   table here, not 8 evaluators.
# - 8 blocker-class signal_ids cover job/machine/attendance
#   categories. The 5 informational ids
#   (recurring_customer_callout, revenue_at_risk,
#   day_2_first_observation, day_7_marker, manager_silence) are
#   deliberately excluded — they convey context, not actions.
# - Locale "hi_en" maps to SignalResult.message_hi_en (Hinglish);
#   "en" maps to SignalResult.message_en. Per-recipient locale
#   resolution lives in the dispatcher, not here.
# - Module-level assertion fails loud at import time when someone
#   adds a signal_id to _BLOCKER_CLASS_SIGNALS without registering a
#   template — preferred over silently skipping at runtime.

from app.services.briefing_intelligence.signals import SignalResult


# Blocker-class signal_ids — the 8 ids whose semantics are "operational
# blocker that warrants a one-line flag + a one-line next step". The
# literal strings match the SIGNAL_ID constants on the corresponding
# evaluators (see catalog/job.py, catalog/machine.py, catalog/attendance.py).
_BLOCKER_CLASS_SIGNALS: frozenset[str] = frozenset(
    {
        "delayed_jobs_count",
        "no_progress",
        "idle_machine",
        "low_utilization",
        "status_change_alert",
        "consecutive_absence",
        "attendance_ratio_concern",
        "new_employee_no_show",
    }
)


# next_step text per signal_id, per locale. Tone follows v6.3.18 SRS
# Section 23: calm, specific, no exclamation, no emoji, polite imperative
# (e.g. "...karein" / "Plan a..."). Each string stays under 70 chars so
# it fits on one WhatsApp line on small-screen devices.
_NEXT_STEP_TEMPLATES: dict[str, dict[str, str]] = {
    "delayed_jobs_count": {
        "hi_en": "Crew ke saath aaj inka revised plan tay kar lein.",
        "en": "Set a revised plan with the crew today.",
    },
    "no_progress": {
        "hi_en": "Assigned worker se status update lein.",
        "en": "Ask the assigned worker for a status update.",
    },
    "idle_machine": {
        "hi_en": "Is hafte ke liye iska koi job plan kar lein.",
        "en": "Plan a job for it this week.",
    },
    "low_utilization": {
        "hi_en": "Iska weekly schedule review karke job add karein.",
        "en": "Review its weekly schedule and add a job.",
    },
    "status_change_alert": {
        "hi_en": "Repair timeline confirm karein aur jobs reassign karein.",
        "en": "Confirm the repair timeline and reassign affected jobs.",
    },
    "consecutive_absence": {
        "hi_en": "Employee se baat karke wajah samjhein.",
        "en": "Speak with the employee to understand the reason.",
    },
    "attendance_ratio_concern": {
        "hi_en": "Employee ke saath 1-on-1 plan karein.",
        "en": "Plan a one-on-one with the employee.",
    },
    "new_employee_no_show": {
        "hi_en": "Call karke joining confirm karein.",
        "en": "Call to confirm their joining date.",
    },
}


# Loud-failure guard — fires at import time if a developer adds an id
# to _BLOCKER_CLASS_SIGNALS without registering a matching template
# (or vice versa). Preferred over silently skipping the signal at
# runtime when the dispatcher tries to look it up.
assert _BLOCKER_CLASS_SIGNALS == _NEXT_STEP_TEMPLATES.keys(), (
    "Blocker-class signals without next_step template: "
    f"{_BLOCKER_CLASS_SIGNALS - _NEXT_STEP_TEMPLATES.keys()}; "
    "extra templates without blocker entry: "
    f"{_NEXT_STEP_TEMPLATES.keys() - _BLOCKER_CLASS_SIGNALS}"
)


_VALID_LOCALES: frozenset[str] = frozenset({"hi_en", "en"})


def select_flag_and_next_step(
    signals: list[SignalResult],
    locale: str,
) -> tuple[str | None, str | None]:
    """Pick the top blocker-class signal for the morning briefing flag line.

    Called by:    (planned) v6.3.19 morning dispatch path. Today only
                  test_consolidated_briefing.py exercises it.
    Calls into:   nothing — pure function over the input list.
    Side effects: none. No DB, no logging, no clock reads.

    Iterates `signals` in given order and returns (flag_text,
    next_step_text) for the first entry whose signal_id is in
    _BLOCKER_CLASS_SIGNALS. The caller MUST pre-sort via composer's
    _sort_key (tier ASC, confidence DESC, severity DESC) — this
    function does not re-sort.

    Returns (None, None) when:
      - signals is empty
      - no blocker-class signal_id is present (only informational ones)

    Raises ValueError when locale is not in {"hi_en", "en"}.
    """
    if locale not in _VALID_LOCALES:
        raise ValueError(
            f"Invalid locale {locale!r}. "
            f"Expected one of {sorted(_VALID_LOCALES)}."
        )

    for sig in signals:
        if sig.signal_id not in _BLOCKER_CLASS_SIGNALS:
            continue
        flag_text = sig.message_hi_en if locale == "hi_en" else sig.message_en
        next_step_text = _NEXT_STEP_TEMPLATES[sig.signal_id][locale]
        return flag_text, next_step_text

    return None, None


# ---------------------------------------------------------------------------
# v6.3.19 slice 2B — field computation helpers
# ---------------------------------------------------------------------------
# These three helpers feed the morning briefing's data fields. They are
# pure SQL reads, no clock reads, no scheduling concerns. The dispatcher
# (slice 2C) calls them once per tick with the resolved tenant_id and
# tenant-local "today" date.
#
# CLAUDE.md rule 1: every DB query filters by tenant_id. Each helper
# takes tenant_id as a required positional argument and applies it as
# the first filter clause.

from datetime import date  # noqa: E402  — kept beneath the slice 2A header
from sqlalchemy.orm import Session  # noqa: E402

from app.models.employee import Employee  # noqa: E402
from app.models.job import Job  # noqa: E402
from app.models.unavailability import EmployeeLeave  # noqa: E402


# Status sets mirror catalog/job.py:50-53 — production carries both
# 'in_progress' and 'In Progress' casings, so comparisons normalise
# before membership lookup.
_TERMINAL_STATUSES: frozenset[str] = frozenset({"completed", "cancelled"})
_IN_PROGRESS_STATUSES: frozenset[str] = frozenset({"in_progress", "in progress"})

# Worker / status vocabulary for the crew-expected helper. Lowercase
# canonical form; the helper lower()s the column value before lookup
# so production rows carrying 'Active' / 'Permanent' / 'Contractor'
# (titlecase) match correctly.
_ACTIVE_STATUS = "active"
_PERMANENT_WORKER_TYPE = "permanent"
_CONTRACTOR_WORKER_TYPE = "contractor"


def _normalize_status(status: str | None) -> str:
    """Lowercase, trim, and tolerate None for status comparisons.

    Called by:    _compute_jobs_starting, _compute_continuing,
                  _compute_crew_expected (this file).
    Calls into:   nothing — pure string normalisation.
    Side effects: none.
    """
    return (status or "").strip().lower()


def _compute_jobs_starting(
    tenant_id: int,
    today: date,
    db: Session,
) -> int:
    """Count jobs scheduled to start today, excluding terminal statuses.

    Called by:    (planned) consolidated_briefing.dispatch_morning (slice 2C).
    Calls into:   Job ORM (read-only).
    Side effects: none.

    Filter:
      Job.tenant_id == tenant_id
      Job.start_date == today
      Job.status NOT IN {'completed', 'cancelled'} (case-insensitive)
    """
    rows = (
        db.query(Job)
        .filter(
            Job.tenant_id == tenant_id,
            Job.start_date == today,
        )
        .all()
    )
    return sum(
        1 for j in rows
        if _normalize_status(j.status) not in _TERMINAL_STATUSES
    )


def _compute_continuing(
    tenant_id: int,
    today: date,
    db: Session,
) -> str:
    """Format the continuing-jobs line: count plus up to 3 names.

    Called by:    (planned) consolidated_briefing.dispatch_morning (slice 2C).
    Calls into:   Job ORM (read-only).
    Side effects: none.

    Selects in_progress jobs whose start_date is strictly before today
    and whose end_date covers today or later. Status comparison is
    case-insensitive against {'in_progress', 'in progress'} — both
    casings are observed in production (catalog/job.py:53 documents
    the same convention).

    Ordering — is_locked DESC, start_date ASC, id ASC:
      - is_locked DESC: locked jobs are explicit owner commitments;
        they lead the line so the briefing matches the owner's mental
        model of what matters most.
      - start_date ASC: surfaces older work first (more time-pressured).
      - id ASC: stable tiebreak.

    Format:
      0 jobs:    "" (empty — caller decides whether to render the line)
      1 job:     "1 ({name})"
      2-3 jobs:  "{N} ({n1}, {n2}, ...)"
      4+ jobs:   "{N} ({n1}, {n2}, {n3} and {N-3} more)"
    """
    rows = (
        db.query(Job)
        .filter(
            Job.tenant_id == tenant_id,
            Job.start_date < today,
            Job.end_date >= today,
        )
        .order_by(
            Job.is_locked.desc(),
            Job.start_date.asc(),
            Job.id.asc(),
        )
        .all()
    )
    in_progress = [
        j for j in rows
        if _normalize_status(j.status) in _IN_PROGRESS_STATUSES
    ]

    n = len(in_progress)
    if n == 0:
        return ""

    names = [j.name for j in in_progress[:3]]
    if n == 1:
        return f"1 ({names[0]})"
    if n in (2, 3):
        return f"{n} ({', '.join(names)})"
    return f"{n} ({', '.join(names)} and {n - 3} more)"


def _compute_crew_expected(
    tenant_id: int,
    today: date,
    db: Session,
) -> str:
    """Format the crew-expected line: "{expected} of {roster} permanent",
    optionally followed by a contractor gap-disclosure.

    Called by:    (planned) consolidated_briefing.dispatch_morning (slice 2C).
    Calls into:   Employee + EmployeeLeave ORM (both read-only).
    Side effects: none.

    Math (PERMANENT-ONLY by deliberate v6.3.19 scoping decision):
      roster   = count of employees with worker_type='permanent' AND
                 status='active' (case-insensitive on both)
      on_leave = count of permanent-roster employees whose
                 EmployeeLeave row covers today (start_date <= today
                 <= end_date)
      expected = max(0, roster - on_leave)

    CONTRACTORS ARE EXCLUDED from both numerator and denominator. This
    is intentional: contractor check-in does not exist as a feature
    today (no per-day confirmed-presence table), so the briefing
    cannot honestly count contractors as either expected or absent.
    Counting contractors as expected would inflate the number;
    counting them as absent would inflate the gap. Excluding them
    keeps the math honest.

    GAP-DISCLOSURE rule:
      When `contractor_count >= roster` AND `contractor_count > 0`,
      the output appends " ({N} contractors not yet tracked)" so a
      tenant whose floor is contractor-majority sees the gap
      explicitly rather than reading "2 of 2 permanent" and feeling
      reassured. Tone follows SRS §23: neutral statement, no
      exclamation. The future feature that closes the gap is
      per-day contractor check-in (no design yet).

    Output format:
      "{expected} of {roster} permanent"
      "{expected} of {roster} permanent ({N} contractors not yet tracked)"
    """
    employees = (
        db.query(Employee)
        .filter(Employee.tenant_id == tenant_id)
        .all()
    )

    permanent = [
        e for e in employees
        if (e.worker_type or "").strip().lower() == _PERMANENT_WORKER_TYPE
        and _normalize_status(e.status) == _ACTIVE_STATUS
    ]
    contractor_count = sum(
        1 for e in employees
        if (e.worker_type or "").strip().lower() == _CONTRACTOR_WORKER_TYPE
        and _normalize_status(e.status) == _ACTIVE_STATUS
    )
    roster = len(permanent)

    on_leave = 0
    if roster:
        permanent_ids = [e.id for e in permanent]
        on_leave = (
            db.query(EmployeeLeave)
            .filter(
                EmployeeLeave.tenant_id == tenant_id,
                EmployeeLeave.employee_id.in_(permanent_ids),
                EmployeeLeave.start_date <= today,
                EmployeeLeave.end_date >= today,
            )
            .count()
        )

    expected = max(0, roster - on_leave)
    base = f"{expected} of {roster} permanent"
    if contractor_count > 0 and contractor_count >= roster:
        return f"{base} ({contractor_count} contractors not yet tracked)"
    return base


# ---------------------------------------------------------------------------
# v6.3.19 slice 2C — async dispatch_morning / dispatch_evening
# ---------------------------------------------------------------------------
# Wires together the slice 1 selector, slice 2A PushConfig cascade, and
# slice 2B field computers with the v6.3.18 Meta-bound templates and
# the existing _send_whatsapp_message transport. Targeted by slice 2D's
# push_v2_tick scheduler job (shadow mode initially — push_v2_enabled
# defaults False so calls log shadow events without sending until the
# cutover happens in v6.3.19.1).
#
# DESIGN DECISIONS DOCUMENTED HERE FOR FUTURE READERS
#
#   A1 — Locale defaults to 'hi_en' for ALL recipients in slice 2C.
#        Per-recipient locale resolution is deferred until a future
#        slice adds a User.language_preference field. The brief assumed
#        that field already existed; an audit found it does not.
#
#   B1 — Recipients come from PhoneTenantMap (matching the v5.10
#        dispatcher pattern), not from User. The is_top_tier filter on
#        PhoneTenantMap (phone_role in TOP_TIER_ROLES) gates who
#        receives the push. Audience-model unification with users
#        belongs in its own future slice.
#
#   D4 — Slice 2C ships ONLY morning + evening dispatchers. The
#        delay-alert and conflict-alert dispatchers are deferred to
#        v6.3.19.1; the legacy 8:00 delay tick and 8:30 conflict tick
#        in whatsapp_alerts.py remain authoritative and ungated by
#        push_v2_enabled in this release.
#
#   E  — Idempotency is implemented as an events-table dedup query
#        keyed on (tenant_id, event_type, payload['scheduled_for_date']).
#        Migration 034 adds the supporting composite index.
#
# DELAY/CONFLICT IS DELIBERATELY ABSENT — see CHANGELOG [Unreleased]
# "v6.3.19 scope reduction" note. Adding delay/conflict here would
# break the D4 scope discipline.

import logging  # noqa: E402
from dataclasses import dataclass  # noqa: E402
from datetime import datetime  # noqa: E402
from typing import Any  # noqa: E402

try:
    # Python 3.9+ stdlib timezone database. The project pins 3.14, so
    # this import always succeeds in production. Wrapped only so that
    # static analysers without the typeshed entry don't choke.
    from zoneinfo import ZoneInfo
except ImportError:  # pragma: no cover — defensive fallback
    ZoneInfo = None  # type: ignore[assignment]

from app.models.event import Event  # noqa: E402
from app.models.whatsapp import PhoneTenantMap  # noqa: E402
from app.services import message_formatters  # noqa: E402
from app.services.push_config import resolve_push_config  # noqa: E402
from app.services.whatsapp_send import _send_whatsapp_message  # noqa: E402

# Private cross-module imports from briefing_intelligence: composer's
# _run_detectors and _select_signals expose the detector pipeline
# without rendering. The public compose_briefing renders into a
# multi-bullet string we don't want here. Aliased for clarity at call
# sites and isolated to this module so consumers of consolidated_briefing
# see a clean public surface.
from app.services.briefing_intelligence.composer import (  # noqa: E402
    _run_detectors as _bi_run_detectors,
    _select_signals as _bi_select_signals,
)


_log = logging.getLogger(__name__)


# Default locale for slice 2C — see header decision A1. Per-recipient
# locale resolution defers until User.language_preference is added.
_DEFAULT_LOCALE: str = "hi_en"


# Hybrid flag-rendering placeholders. Used when the selector returns
# (None, None) for flag/next_step (i.e. no blocker-class signal fired).
# Tone follows SRS §23: calm, neutral, no exclamation. Will collapse to
# empty when the v2 conditional-section template lands; until then the
# template's hard {flag} / {next_step} placeholders need a non-empty
# value so the f-string render does not break.
_PLACEHOLDER_FLAG: dict[str, str] = {
    "hi_en": "Aaj sab routine hai.",
    "en": "All systems normal today.",
}
_PLACEHOLDER_NEXT_STEP: dict[str, str] = {
    "hi_en": "Koi action nahi chahiye.",
    "en": "No action needed.",
}


# Alert-preference keys recorded on PhoneTenantMap.alert_preferences.
# Match the snake_case convention of the existing keys
# (morning_briefing, job_delay, machine_down, conflict). Default True
# when the key is missing — same as the v5.10 _get_active_phone_mappings
# convention so a tenant who has never configured push prefs still
# receives the briefing.
_ALERT_KEY_PUSH_MORNING: str = "push_morning"
_ALERT_KEY_PUSH_EVENING: str = "push_evening"


# Event-type vocabulary for the events audit log. Dotted names match
# the existing convention (briefing.sent, user.role_changed). The
# 'sent' suffix is the idempotency anchor: _already_dispatched_today
# searches only for the *_sent variants, so skip events do not
# poison the dedup window.
_EVENT_PUSH_MORNING_SENT: str = "push.morning_sent"
_EVENT_PUSH_MORNING_SKIPPED_DISABLED: str = "push.morning_skipped_disabled"
_EVENT_PUSH_MORNING_SKIPPED_PAUSED: str = "push.morning_skipped_paused"
_EVENT_PUSH_MORNING_SKIPPED_IDEMPOTENT: str = "push.morning_skipped_idempotent"
_EVENT_PUSH_MORNING_SKIPPED_NO_RECIPIENTS: str = "push.morning_skipped_no_recipients"
_EVENT_PUSH_MORNING_SEND_FAILED: str = "push.morning_send_failed"

_EVENT_PUSH_EVENING_SENT: str = "push.evening_sent"
_EVENT_PUSH_EVENING_SKIPPED_DISABLED: str = "push.evening_skipped_disabled"
_EVENT_PUSH_EVENING_SKIPPED_PAUSED: str = "push.evening_skipped_paused"
_EVENT_PUSH_EVENING_SKIPPED_IDEMPOTENT: str = "push.evening_skipped_idempotent"
_EVENT_PUSH_EVENING_SKIPPED_NO_RECIPIENTS: str = "push.evening_skipped_no_recipients"
_EVENT_PUSH_EVENING_SEND_FAILED: str = "push.evening_send_failed"


@dataclass(frozen=True)
class DispatchResult:
    """Outcome of one dispatch_morning / dispatch_evening call.

    Fields:
      success         True when the dispatcher ran to completion without
                      an unhandled exception. Skips count as success.
                      False only when at least one Meta send raised AND
                      no other recipient succeeded.
      tenant_id       The tenant the dispatcher targeted.
      kind            'morning' or 'evening'.
      sent_count      Number of recipients the Meta send succeeded for
                      (real mode) or would-have-succeeded for (shadow
                      mode). 0 on every skip path and full-failure paths.
      skip_reason     None when an actual send was attempted. Otherwise
                      one of: 'paused' | 'disabled' | 'idempotent' |
                      'no_recipients' | 'tenant_not_found'.
      rendered_message The full template-rendered string. Useful for
                      shadow-mode logging in slice 2D and for the debug
                      endpoint. None on skip paths that don't render.
      error           First Meta exception's str(). None on success
                      and on skip paths.
      recipients      Tuple of phone_e164 strings the dispatcher
                      resolved as targets. Populated on every send-loop
                      path (shadow + real). Empty tuple on skip paths
                      that returned before recipient resolution.
      event_id        Primary key of the anchor events row written by
                      this dispatch. In real mode: the *_sent row id
                      (or None if all sends failed before that row).
                      In shadow mode: the push.shadow_log row id for
                      the 'sent' or skip stage.
    """

    success: bool
    tenant_id: int
    kind: str
    sent_count: int = 0
    skip_reason: str | None = None
    rendered_message: str | None = None
    error: str | None = None
    recipients: tuple[str, ...] = ()
    event_id: int | None = None


def _resolve_top_tier_recipients(
    tenant_id: int,
    alert_pref_key: str,
    db: "Session",  # type: ignore[name-defined]  — Session imported above
) -> list[PhoneTenantMap]:
    """Top-tier active phones opted in to a specific push alert type.

    Called by:    dispatch_morning, dispatch_evening (this file).
    Calls into:   PhoneTenantMap ORM (read-only).
    Side effects: none.

    Filter (mirrors v5.10 _get_active_phone_mappings + adds the
    top-tier role gate):
      tenant_id == tenant_id
      is_active is True
      is_top_tier is True (phone_role in TOP_TIER_ROLES)
      alert_preferences[alert_pref_key] is not False (default True
        when the key is missing — same convention as the existing
        whatsapp_alerts._get_active_phone_mappings helper).

    Ordering: id ASC for deterministic test output and stable shadow-
    log payload formatting.
    """
    rows = (
        db.query(PhoneTenantMap)
        .filter(
            PhoneTenantMap.tenant_id == tenant_id,
            PhoneTenantMap.is_active == True,  # noqa: E712
        )
        .order_by(PhoneTenantMap.id.asc())
        .all()
    )
    out: list[PhoneTenantMap] = []
    for m in rows:
        if not m.is_top_tier:
            continue
        prefs = m.alert_preferences or {}
        if prefs.get(alert_pref_key, True) is False:
            continue
        out.append(m)
    return out


def _already_dispatched_today(
    tenant_id: int,
    event_type: str,
    scheduled_for_date: "date",  # type: ignore[name-defined] — date imported above
    db: "Session",  # type: ignore[name-defined]
) -> bool:
    """True if the (tenant, event_type, scheduled_for_date) trio has
    already been logged to the events table via a *_sent event.

    Called by:    dispatch_morning, dispatch_evening (this file).
    Calls into:   Event ORM (read-only).
    Side effects: none.

    Migration 034 (v6.3.19 slice 2C) added the composite index
    ix_events_tenant_type_dedup on events(tenant_id, event_type) to
    keep this query fast as the events table grows. The
    payload['scheduled_for_date'] filter runs in Python because
    payload is JSONB on Postgres and JSON on SQLite (test conftest
    patch); the dialect-agnostic Python filter is cleaner than
    branching on engine type and the index already narrows the
    candidate set to a small per-tenant per-event-type slice.
    """
    date_str = scheduled_for_date.isoformat()
    candidates = (
        db.query(Event)
        .filter(
            Event.tenant_id == tenant_id,
            Event.event_type == event_type,
        )
        .all()
    )
    return any(
        (e.payload or {}).get("scheduled_for_date") == date_str
        for e in candidates
    )


def _log_event(
    *,
    tenant_id: int,
    event_type: str,
    payload: dict[str, Any],
    db: "Session",  # type: ignore[name-defined]
) -> Event:
    """Insert one events row and flush. Caller commits.

    Called by:    dispatch_morning, dispatch_evening (this file).
    Calls into:   Event ORM, db.add + db.flush.
    Side effects: writes one row. Caller is responsible for db.commit().

    entity_type='briefing' across all push.* events — matches the
    convention briefing.sent uses today.  source='system' identifies
    the dispatcher tick as the originator (not a web or whatsapp
    user action).
    """
    e = Event(
        tenant_id=tenant_id,
        event_type=event_type,
        entity_type="briefing",
        source="system",
        payload=payload,
    )
    db.add(e)
    db.flush()
    return e


def _scheduled_date_for(
    now: datetime,
    push_timezone: str,
) -> "date":  # type: ignore[name-defined]
    """Convert `now` to the tenant timezone and take the calendar date.

    Called by:    dispatch_morning, dispatch_evening (this file).
    Calls into:   zoneinfo.ZoneInfo, datetime.astimezone.
    Side effects: none.

    The dispatcher uses this calendar date as the idempotency key and
    as the date displayed in the rendered briefing. Falls back to
    `now`'s date as-is when zoneinfo is unavailable (defensive — the
    project pins Python 3.14 so this path is unreachable in
    production).
    """
    if ZoneInfo is None:
        return now.date()
    try:
        tz = ZoneInfo(push_timezone)
    except Exception:  # noqa: BLE001 — ZoneInfo raises a hierarchy of types
        return now.date()
    return now.astimezone(tz).date()


def _render_morning_message(
    tenant_id: int,
    now: datetime,
    db: "Session",  # type: ignore[name-defined]
    locale: str = _DEFAULT_LOCALE,
) -> str:
    """Render the MORNING_BRIEFING template for one tenant.

    Called by:    dispatch_morning, dispatch_evening (this file).
    Calls into:   _compute_jobs_starting / _compute_continuing /
                  _compute_crew_expected (slice 2B), select_flag_and_next_step
                  (slice 1), _bi_run_detectors / _bi_select_signals
                  (private cross-module access — composer detector
                  pipeline without rendering).
    Side effects: read-only DB.

    Evening reuses the same template in slice 2C — there is no
    separate evening template constant in v6.3.18 yet. The brief
    explicitly notes the evening template is on the v6.4 backlog;
    until it lands, the structural skip / log / send path is the
    only difference between morning and evening dispatch.

    Hybrid flag rendering: when select_flag_and_next_step returns
    (None, None) — no blocker-class signal fired or pattern_briefing
    is not enabled for the tenant — the placeholder values from
    _PLACEHOLDER_FLAG / _PLACEHOLDER_NEXT_STEP are substituted so
    the template's hard {flag} / {next_step} placeholders render
    cleanly. The Meta v2 conditional-section template will collapse
    these to empty when approved (see CHANGELOG [Unreleased] hybrid
    note).
    """
    today = now.date()

    jobs_starting = _compute_jobs_starting(tenant_id, today, db)
    continuing = _compute_continuing(tenant_id, today, db) or "0"
    crew_expected = _compute_crew_expected(tenant_id, today, db)

    signals = _bi_run_detectors(tenant_id, today, db)
    selected = _bi_select_signals(signals)
    flag, next_step = select_flag_and_next_step(selected, locale=locale)

    if flag is None:
        flag = _PLACEHOLDER_FLAG[locale]
    if next_step is None:
        next_step = _PLACEHOLDER_NEXT_STEP[locale]

    template = (
        message_formatters.MORNING_BRIEFING_HI
        if locale == "hi_en"
        else message_formatters.MORNING_BRIEFING_EN
    )
    return template.format(
        date=today.strftime("%d %b"),
        jobs_starting=jobs_starting,
        continuing=continuing,
        crew_expected=crew_expected,
        flag=flag,
        next_step=next_step,
    )


async def _dispatch_one(
    tenant_id: int,
    now: datetime,
    db: "Session",  # type: ignore[name-defined]
    *,
    kind: str,  # 'morning' | 'evening'
) -> DispatchResult:
    """Shared dispatch path for morning and evening.

    Called by:    dispatch_morning, dispatch_evening (this file).
    Calls into:   resolve_push_config (slice 2A), _scheduled_date_for,
                  _resolve_top_tier_recipients, _already_dispatched_today,
                  _log_event, _render_morning_message,
                  _send_whatsapp_message.
    Side effects: writes events rows + commits, calls Meta send
                  (mock-aware via WHATSAPP_MOCK_MODE inside
                  _send_whatsapp_message).

    The kind parameter selects:
      - which PushConfig.<kind>_enabled flag gates the send,
      - which alert_preferences key recipients must opt in to,
      - which event_type prefix is logged,
      - which template (currently both share MORNING_BRIEFING_*).

    v6.3.19.1 — `shadow` kwarg removed. The cutover release dropped
    the PUSH_V2_ENABLED flag and made the new push system the sole
    code path. Shadow-mode logging is no longer available.
    """
    from app.models.auth import Tenant  # local import — avoid cycle

    if kind == "morning":
        alert_key = _ALERT_KEY_PUSH_MORNING
        event_sent = _EVENT_PUSH_MORNING_SENT
        event_skipped_disabled = _EVENT_PUSH_MORNING_SKIPPED_DISABLED
        event_skipped_paused = _EVENT_PUSH_MORNING_SKIPPED_PAUSED
        event_skipped_idempotent = _EVENT_PUSH_MORNING_SKIPPED_IDEMPOTENT
        event_skipped_no_recipients = _EVENT_PUSH_MORNING_SKIPPED_NO_RECIPIENTS
        event_send_failed = _EVENT_PUSH_MORNING_SEND_FAILED
    else:
        alert_key = _ALERT_KEY_PUSH_EVENING
        event_sent = _EVENT_PUSH_EVENING_SENT
        event_skipped_disabled = _EVENT_PUSH_EVENING_SKIPPED_DISABLED
        event_skipped_paused = _EVENT_PUSH_EVENING_SKIPPED_PAUSED
        event_skipped_idempotent = _EVENT_PUSH_EVENING_SKIPPED_IDEMPOTENT
        event_skipped_no_recipients = _EVENT_PUSH_EVENING_SKIPPED_NO_RECIPIENTS
        event_send_failed = _EVENT_PUSH_EVENING_SEND_FAILED

    tenant = db.get(Tenant, tenant_id)
    if tenant is None:
        return DispatchResult(
            success=False,
            tenant_id=tenant_id,
            kind=kind,
            skip_reason="tenant_not_found",
            error=f"Tenant {tenant_id} not found",
        )

    config = resolve_push_config(tenant)
    scheduled_for = _scheduled_date_for(now, config.push_timezone)
    scheduled_for_str = scheduled_for.isoformat()
    now_str = now.isoformat()

    # `emit` writes the per-stage event (push.{kind}_skipped_disabled etc).
    _stage_to_real_event = {
        "skipped_disabled": event_skipped_disabled,
        "skipped_paused": event_skipped_paused,
        "skipped_idempotent": event_skipped_idempotent,
        "skipped_no_recipients": event_skipped_no_recipients,
        "sent": event_sent,
        "send_failed": event_send_failed,
    }

    last_event_id: int | None = None

    def emit(stage: str, payload: dict[str, Any]) -> None:
        nonlocal last_event_id
        row = _log_event(
            tenant_id=tenant_id,
            event_type=_stage_to_real_event[stage],
            payload=payload,
            db=db,
        )
        last_event_id = row.id

    # Disabled gate (per-direction).
    direction_enabled = (
        config.morning_enabled if kind == "morning" else config.evening_enabled
    )
    if not direction_enabled:
        emit(
            "skipped_disabled",
            {"scheduled_for_date": scheduled_for_str, "now": now_str},
        )
        db.commit()
        return DispatchResult(
            success=True,
            tenant_id=tenant_id,
            kind=kind,
            skip_reason="disabled",
            event_id=last_event_id,
        )

    # Paused gate. Inclusive boundary: a tenant with push_paused_until
    # exactly equal to today is still paused for today.
    if config.push_paused_until and config.push_paused_until >= scheduled_for:
        emit(
            "skipped_paused",
            {
                "scheduled_for_date": scheduled_for_str,
                "paused_until": config.push_paused_until.isoformat(),
                "now": now_str,
            },
        )
        db.commit()
        return DispatchResult(
            success=True,
            tenant_id=tenant_id,
            kind=kind,
            skip_reason="paused",
            event_id=last_event_id,
        )

    # Idempotency. The *_sent event from a prior dispatch is the
    # dedup anchor.
    if _already_dispatched_today(
        tenant_id, event_sent, scheduled_for, db,
    ):
        emit(
            "skipped_idempotent",
            {"scheduled_for_date": scheduled_for_str, "now": now_str},
        )
        db.commit()
        return DispatchResult(
            success=True,
            tenant_id=tenant_id,
            kind=kind,
            skip_reason="idempotent",
            event_id=last_event_id,
        )

    # Recipient resolution.
    recipients = _resolve_top_tier_recipients(tenant_id, alert_key, db)
    if not recipients:
        emit(
            "skipped_no_recipients",
            {"scheduled_for_date": scheduled_for_str, "now": now_str},
        )
        db.commit()
        return DispatchResult(
            success=True,
            tenant_id=tenant_id,
            kind=kind,
            skip_reason="no_recipients",
            event_id=last_event_id,
        )

    # Render. Slice 2C uses _DEFAULT_LOCALE for all recipients (A1).
    rendered = _render_morning_message(tenant_id, now, db, locale=_DEFAULT_LOCALE)

    # Send + per-recipient failure logging. One failure does not stop
    # the loop — other recipients still attempt.
    sent_count = 0
    last_error: str | None = None
    for r in recipients:
        try:
            await _send_whatsapp_message(r.phone_number, rendered)
            sent_count += 1
        except Exception as exc:  # noqa: BLE001 — Meta SDK raises many types
            last_error = str(exc) or exc.__class__.__name__
            emit(
                "send_failed",
                {
                    "scheduled_for_date": scheduled_for_str,
                    "phone": r.phone_number,
                    "error": last_error,
                    "now": now_str,
                },
            )
            _log.warning(
                "push.%s send_failed tenant=%s phone=****%s error=%s",
                kind, tenant_id, r.phone_number[-4:], last_error,
            )

    # Idempotency anchor — only when at least one recipient received
    # the message. Failed-only dispatches do NOT create a *_sent event,
    # so the next tick can retry.
    if sent_count > 0:
        emit(
            "sent",
            {
                "scheduled_for_date": scheduled_for_str,
                "now": now_str,
                "recipients": [r.phone_number for r in recipients],
                "sent_count": sent_count,
                "rendered_message": rendered,
                "locale": _DEFAULT_LOCALE,
            },
        )
    db.commit()

    return DispatchResult(
        success=sent_count > 0 or last_error is None,
        tenant_id=tenant_id,
        kind=kind,
        sent_count=sent_count,
        rendered_message=rendered,
        error=last_error,
        recipients=tuple(r.phone_number for r in recipients),
        event_id=last_event_id,
    )


async def dispatch_morning(
    tenant_id: int,
    now: datetime,
    db: "Session",  # type: ignore[name-defined]
) -> DispatchResult:
    """Send the morning briefing to one tenant's top-tier WhatsApp recipients.

    Called by:    push_v2_tick (this file), the debug dispatch
                  endpoint, and tests.
    Calls into:   _dispatch_one (this file). All template / send /
                  event-log work happens there.
    Side effects: writes events rows, commits, calls Meta send
                  (mock-aware via WHATSAPP_MOCK_MODE).

    Argument order — `(tenant_id, now, db)` — matches slice 2B field
    helpers. Diverges from the v6.3.19 brief sketch
    `(now, db, tenant_id)` in favour of consistency with merged code.

    Locale: slice 2C dispatches all recipients in 'hi_en'. Per-recipient
    locale resolution defers until User.language_preference exists.

    v6.3.19.1 — `shadow` kwarg removed in the cutover release.
    """
    return await _dispatch_one(tenant_id, now, db, kind="morning")


async def dispatch_evening(
    tenant_id: int,
    now: datetime,
    db: "Session",  # type: ignore[name-defined]
) -> DispatchResult:
    """Send the evening recap to one tenant's top-tier WhatsApp recipients.

    Called by:    push_v2_tick (this file), the debug dispatch
                  endpoint, and tests.
    Calls into:   _dispatch_one (this file).
    Side effects: writes events rows, commits, calls Meta send.

    Slice 2C limitation: the evening render path currently uses the
    MORNING_BRIEFING template because no separate evening template
    constant exists in message_formatters.py yet. The skip / send /
    log behaviour and idempotency keying are evening-specific
    (briefing_evening_enabled, push.evening_*). A dedicated EVENING_*
    template constant + render path is on the v6.4 backlog.

    v6.3.19.1 — `shadow` kwarg removed in the cutover release.
    """
    return await _dispatch_one(tenant_id, now, db, kind="evening")


# ---------------------------------------------------------------------------
# v6.3.19.1 — push_v2_tick + hash stagger (sole code path post-cutover)
# ---------------------------------------------------------------------------
# APScheduler tick running every minute (cron, not interval, to avoid
# drift). Iterates tenants and dispatches morning/evening pushes when
# the per-tenant briefing_*_time matches `now`, plus delay alerts at
# the legacy 8/10/12/14/16/18/20 IST cadence and conflict alerts at
# 8:30/12:30/16:30/20:30 IST. Per-tenant hash stagger spreads sends
# across the 60-second window so 3000 tenants don't all fire in the
# same second.
#
# v6.3.19.1 removed the PUSH_V2_ENABLED shadow-mode gate. The new
# push system is now the only push code path; the legacy v5.10
# functions (run_briefing_dispatch_tick / check_delayed_jobs /
# check_scheduling_conflicts) were deleted from whatsapp_alerts.py.

import asyncio  # noqa: E402


def _offset_seconds_for(tenant_id: int) -> int:
    """Per-tenant stagger offset within the 60-second tick window.

    Called by:    _dispatch_with_offset, push_v2_tick (this file).
                  Tests in slice 2D-tests assert the spread.
    Calls into:   nothing — pure arithmetic.
    Side effects: none.

    Returns `tenant_id % 60` so a tenant's offset is deterministic
    and stable for owners (predictable arrival time minute-to-minute).
    Tenant 1  -> offset 1.   Tenant 12 -> offset 12.
    Tenant 60 -> offset 0.   Tenant 120 -> offset 0.
    """
    return tenant_id % 60


def _tenants_due_for(
    now: datetime,
    kind: str,
    db: "Session",  # type: ignore[name-defined]
) -> list[int]:
    """Tenant IDs whose configured push_time matches `now` (in their tz).

    Called by:    push_v2_tick (this file).
    Calls into:   Tenant ORM, resolve_push_config (slice 2A),
                  zoneinfo.ZoneInfo.
    Side effects: read-only DB.

    Filters at the DB level by direction-enabled to keep the
    candidate set small. For v6.3.19 scale this iterates every
    enabled tenant in Python; a per-tenant push_time index is on the
    backlog if 3000+ tenants becomes a hotpath concern.
    """
    from app.models.auth import Tenant  # local import — avoid cycle

    q = db.query(Tenant)
    if kind == "morning":
        q = q.filter(Tenant.briefing_morning_enabled == True)  # noqa: E712
    else:
        q = q.filter(Tenant.briefing_evening_enabled == True)  # noqa: E712

    out: list[int] = []
    for t in q.all():
        config = resolve_push_config(t)
        push_time = (
            config.morning_push_time if kind == "morning"
            else config.evening_push_time
        )
        if ZoneInfo is None:
            local_now = now
        else:
            try:
                tz = ZoneInfo(config.push_timezone)
            except Exception:  # noqa: BLE001 — defensive
                continue
            local_now = now.astimezone(tz)
        if (
            local_now.hour == push_time.hour
            and local_now.minute == push_time.minute
        ):
            out.append(t.id)
    return out


async def _dispatch_with_offset(
    tenant_id: int,
    now: datetime,
    db: "Session",  # type: ignore[name-defined]
    *,
    kind: str,
    apply_stagger: bool,
    job_id: int | None = None,
    conflict_payload: dict | None = None,
) -> DispatchResult:
    """Sleep for the per-tenant offset then dispatch. Wraps any
    dispatcher exception in a push.tick_failed log so a single
    bad tenant cannot stop the whole tick.

    Called by:    push_v2_tick (this file).
    Calls into:   asyncio.sleep, dispatch_morning / dispatch_evening /
                  dispatch_delay_alert / dispatch_conflict_alert,
                  _log_event.
    Side effects: ~0–60 second deferral, writes events rows on failure.

    For kind='delay' the caller must pass job_id; for kind='conflict'
    the caller must pass conflict_payload. Morning/evening ignore
    both extras.
    """
    if apply_stagger:
        offset = _offset_seconds_for(tenant_id)
        if offset > 0:
            await asyncio.sleep(offset)

    try:
        if kind == "morning":
            return await dispatch_morning(tenant_id, now, db)
        if kind == "evening":
            return await dispatch_evening(tenant_id, now, db)
        if kind == "delay":
            return await dispatch_delay_alert(
                tenant_id, now, db, job_id=job_id,
            )
        if kind == "conflict":
            return await dispatch_conflict_alert(
                tenant_id, now, db, conflict_payload=conflict_payload,
            )
        raise ValueError(f"Unknown dispatch kind: {kind!r}")
    except Exception as exc:  # noqa: BLE001 — protect the tick loop
        # One bad tenant must not abort the tick. Log and return a
        # failure result so push_v2_tick's gather() does not raise.
        try:
            _log_event(
                tenant_id=tenant_id,
                event_type="push.tick_failed",
                payload={
                    "kind": kind,
                    "now": now.isoformat(),
                    "error": str(exc) or exc.__class__.__name__,
                },
                db=db,
            )
            db.commit()
        except Exception:  # noqa: BLE001 — log fallback
            db.rollback()
            _log.exception(
                "push.tick_failed log itself failed for tenant=%s", tenant_id,
            )
        _log.exception(
            "push_v2_tick: tenant=%s kind=%s raised %s",
            tenant_id, kind, exc,
        )
        return DispatchResult(
            success=False,
            tenant_id=tenant_id,
            kind=kind,
            error=str(exc) or exc.__class__.__name__,
        )


# v6.3.19.1 — multi-pass cadence matching legacy `check_delayed_jobs`
# (which fired every 2 hours during working hours) and
# `check_scheduling_conflicts` (every 4 hours starting 8:30 IST,
# filtered to working hours). Hour values are tenant-local IST.
# Stay synchronous with the deleted legacy schedule so dispatcher
# behaviour is one-for-one with the v5.10 era.
_DELAY_HOURS_IST: tuple[int, ...] = (8, 10, 12, 14, 16, 18, 20)
_CONFLICT_HOURS_IST: tuple[int, ...] = (8, 12, 16, 20)
_CONFLICT_MINUTE_IST: int = 30


def _is_delay_tick(now: datetime) -> bool:
    """True when `now` matches one of the legacy delay-alert hours at :00.

    Called by:    push_v2_tick (this file).
    Calls into:   zoneinfo.ZoneInfo.
    Side effects: none.
    """
    if ZoneInfo is None:
        return False
    try:
        local = now.astimezone(ZoneInfo("Asia/Kolkata"))
    except Exception:  # noqa: BLE001 — defensive
        return False
    return local.hour in _DELAY_HOURS_IST and local.minute == 0


def _is_conflict_tick(now: datetime) -> bool:
    """True when `now` matches one of the legacy conflict-alert minute
    marks (8:30 / 12:30 / 16:30 / 20:30 IST).

    Called by:    push_v2_tick (this file).
    Calls into:   zoneinfo.ZoneInfo.
    Side effects: none.
    """
    if ZoneInfo is None:
        return False
    try:
        local = now.astimezone(ZoneInfo("Asia/Kolkata"))
    except Exception:  # noqa: BLE001 — defensive
        return False
    return (
        local.hour in _CONFLICT_HOURS_IST
        and local.minute == _CONFLICT_MINUTE_IST
    )


def _tenants_for_alert_pref(
    alert_pref_key: str,
    db: "Session",  # type: ignore[name-defined]
) -> list[int]:
    """Distinct tenant_ids that have at least one active top-tier phone
    opted in to the given alert preference key. Used by the delay /
    conflict tick to find the candidate set per pass.

    Called by:    push_v2_tick (this file) when _is_delay_tick or
                  _is_conflict_tick fires.
    Calls into:   PhoneTenantMap ORM (read-only).
    Side effects: none.
    """
    from app.models.auth import Tenant  # local — avoid import cycle

    rows = (
        db.query(Tenant.id, PhoneTenantMap)
        .join(PhoneTenantMap, PhoneTenantMap.tenant_id == Tenant.id)
        .filter(PhoneTenantMap.is_active == True)  # noqa: E712
        .all()
    )
    seen: set[int] = set()
    out: list[int] = []
    for tenant_id, ptm in rows:
        if tenant_id in seen:
            continue
        if not ptm.is_top_tier:
            continue
        prefs = ptm.alert_preferences or {}
        if prefs.get(alert_pref_key, True) is False:
            continue
        seen.add(tenant_id)
        out.append(tenant_id)
    return sorted(out)


async def push_v2_tick(
    now: datetime,
    db: "Session",  # type: ignore[name-defined]
    *,
    apply_stagger: bool = True,
) -> list[DispatchResult]:
    """One per-minute scheduler tick for the v6.3.19.1 consolidated
    push cadence.

    Called by:    APScheduler 'push_v2_tick_job' (registered in
                  whatsapp_alerts.start_scheduler), the debug endpoint,
                  and integration tests.
    Calls into:   _tenants_due_for, _tenants_for_alert_pref,
                  _is_delay_tick, _is_conflict_tick,
                  _dispatch_with_offset, _get_delayed_jobs_for_dispatch,
                  _get_conflicts_for_dispatch.
    Side effects: writes events rows, Meta sends. Bounded asyncio.sleep
                  up to 59 seconds per tenant when apply_stagger=True
                  (default in production); tests pass apply_stagger=False
                  to bypass the wait.

    Cadence in v6.3.19.1 (post-cutover — the only push code path):
      - Morning: per-tenant briefing_morning_time (default 07:30 IST).
      - Evening: per-tenant briefing_evening_time (default 18:30 IST).
      - Delay alerts: hours 8/10/12/14/16/18/20 IST at :00 — one
        dispatch per delayed job per tenant per matching tick. Mirrors
        the legacy `check_delayed_jobs` cadence (which was a "*-hour-
        on-the-hour during working hours" cron). No dedup; consecutive
        ticks both fire push.delay_sent. Spam-fix tracked as a future
        release.
      - Conflict alerts: 8:30 / 12:30 / 16:30 / 20:30 IST — one dispatch
        per conflict per tenant per matching tick. Mirrors the legacy
        `check_scheduling_conflicts` cadence. No dedup.

    Per-tenant exceptions are captured and logged as push.tick_failed
    rows; the tick continues to the next tenant.
    """
    tasks: list = []

    # Morning / evening (per-tenant time match).
    due_morning = _tenants_due_for(now, "morning", db)
    due_evening = _tenants_due_for(now, "evening", db)
    for tenant_id in due_morning:
        tasks.append(_dispatch_with_offset(
            tenant_id, now, db,
            kind="morning", apply_stagger=apply_stagger,
        ))
    for tenant_id in due_evening:
        tasks.append(_dispatch_with_offset(
            tenant_id, now, db,
            kind="evening", apply_stagger=apply_stagger,
        ))

    # Delay alerts (multi-pass IST cadence, one task per delayed job).
    if _is_delay_tick(now):
        today_local = _scheduled_date_for(now, "Asia/Kolkata")
        for tenant_id in _tenants_for_alert_pref(_ALERT_KEY_PUSH_DELAY, db):
            for job in _get_delayed_jobs_for_dispatch(
                tenant_id, today_local, db,
            ):
                tasks.append(_dispatch_with_offset(
                    tenant_id, now, db,
                    kind="delay", apply_stagger=apply_stagger,
                    job_id=job.id,
                ))

    # Conflict alerts (multi-pass IST cadence, one task per conflict).
    if _is_conflict_tick(now):
        today_local = _scheduled_date_for(now, "Asia/Kolkata")
        for tenant_id in _tenants_for_alert_pref(_ALERT_KEY_PUSH_CONFLICT, db):
            for payload in _get_conflicts_for_dispatch(
                tenant_id, today_local, db,
            ):
                tasks.append(_dispatch_with_offset(
                    tenant_id, now, db,
                    kind="conflict", apply_stagger=apply_stagger,
                    conflict_payload=payload,
                ))

    if not tasks:
        return []

    return await asyncio.gather(*tasks, return_exceptions=False)


# ---------------------------------------------------------------------------
# v6.3.19.1 — dispatch_delay_alert + dispatch_conflict_alert
# ---------------------------------------------------------------------------
# Per-job / per-conflict singular dispatches, matching the shape of
# the Meta-bound DELAY_ALERT_EN and CONFLICT_ALERT_EN templates
# (zetaops_job_ending_soon and zetaops_job_conflict_alert). The
# legacy whatsapp_alerts.check_delayed_jobs sent a summary message
# per tenant (one row per tick); v6.3.19.1 splits into per-job
# messages to match the Meta template's singular shape. This is
# more verbose than legacy by design — the Meta-side templates
# treat each delayed job as a discrete actionable item.

from app.models.job import Job  # noqa: E402
from sqlalchemy import select, text as sa_text  # noqa: E402


_ALERT_KEY_PUSH_DELAY: str = "push_delay"
_ALERT_KEY_PUSH_CONFLICT: str = "push_conflict"

_EVENT_PUSH_DELAY_SENT: str = "push.delay_sent"
_EVENT_PUSH_DELAY_SKIPPED_PAUSED: str = "push.delay_skipped_paused"
_EVENT_PUSH_DELAY_SKIPPED_NO_RECIPIENTS: str = "push.delay_skipped_no_recipients"
_EVENT_PUSH_DELAY_SEND_FAILED: str = "push.delay_send_failed"

_EVENT_PUSH_CONFLICT_SENT: str = "push.conflict_sent"
_EVENT_PUSH_CONFLICT_SKIPPED_PAUSED: str = "push.conflict_skipped_paused"
_EVENT_PUSH_CONFLICT_SKIPPED_NO_RECIPIENTS: str = "push.conflict_skipped_no_recipients"
_EVENT_PUSH_CONFLICT_SEND_FAILED: str = "push.conflict_send_failed"


_TERMINAL_JOB_STATUSES_LOWER = frozenset({"completed", "cancelled"})


def _get_delayed_jobs_for_dispatch(
    tenant_id: int,
    today: "date",  # type: ignore[name-defined]
    db: "Session",  # type: ignore[name-defined]
) -> list[Job]:
    """Mirror of legacy whatsapp_alerts._get_delayed_jobs as a sync
    helper that accepts an external session and `today` anchor.

    Called by:    push_v2_tick (this file).
    Calls into:   Job ORM (read-only).
    Side effects: none.

    Filter: tenant_id matches AND end_date < today AND status NOT IN
    (completed, cancelled), case-insensitive.
    """
    rows: list[Job] = (
        db.query(Job)
        .filter(
            Job.tenant_id == tenant_id,
            Job.end_date.isnot(None),
            Job.end_date < today,
        )
        .order_by(Job.end_date.asc(), Job.id.asc())
        .all()
    )
    return [
        j for j in rows
        if (j.status or "").strip().lower() not in _TERMINAL_JOB_STATUSES_LOWER
    ]


def _get_conflicts_for_dispatch(
    tenant_id: int,
    today: "date",  # type: ignore[name-defined]
    db: "Session",  # type: ignore[name-defined]
) -> list[dict[str, Any]]:
    """Mirror of legacy whatsapp_alerts._get_conflicts as a sync
    helper that returns conflict-payload dicts shaped for the
    CONFLICT_ALERT_EN template ({job_a, job_b, resource, window,
    next_step}).

    Called by:    push_v2_tick (this file).
    Calls into:   Job ORM + schedule_entries raw SQL (read-only).
    Side effects: none.

    Conflict detection mirrors v5.10: a job has fewer schedule_entries
    rows than (end_date - start_date + 1) calendar days. The new
    template wants TWO jobs in conflict; the legacy detector only
    flagged single jobs with allocation gaps, so v6.3.19.1 pairs
    consecutive conflict jobs into the (job_a, job_b) slots. When
    there is exactly one conflict, job_b renders as '—' (placeholder
    matching the template's required-field shape).

    The `resource` field is filled as '—' today — the v5.10 detector
    does not expose which specific machine / employee is contended.
    Surfacing the real resource is on the v6.4 scheduler-conflict
    rewrite backlog; until then the placeholder is honest about the
    information gap.
    """
    rows = (
        db.query(Job)
        .filter(
            Job.tenant_id == tenant_id,
            Job.status.notin_([
                "completed", "cancelled", "Completed", "Cancelled",
            ]),
            Job.start_date.isnot(None),
            Job.end_date.isnot(None),
        )
        .all()
    )
    if not rows:
        return []

    # Count schedule_entries per job — same pattern as legacy.
    job_ids = [j.id for j in rows]
    entry_counts: dict[int, int] = {}
    try:
        result = db.execute(
            sa_text(
                "SELECT job_id, COUNT(*) AS entry_count "
                "FROM schedule_entries "
                "WHERE job_id = ANY(:job_ids) "
                "GROUP BY job_id"
            ),
            {"job_ids": job_ids},
        ).all()
        for row in result:
            entry_counts[row.job_id] = row.entry_count
    except Exception:  # noqa: BLE001 — defensive (SQLite test path may miss)
        entry_counts = {}

    conflicted: list[Job] = []
    for j in rows:
        expected_days = max(1, (j.end_date - j.start_date).days + 1)
        if entry_counts.get(j.id, 0) < expected_days:
            conflicted.append(j)

    if not conflicted:
        return []

    # Pair consecutive conflicts into (job_a, job_b) slots. Lone
    # conflicts render job_b as '—'.
    payloads: list[dict[str, Any]] = []
    i = 0
    while i < len(conflicted):
        ja = conflicted[i]
        jb = conflicted[i + 1] if i + 1 < len(conflicted) else None
        payloads.append({
            "job_a": ja.name or f"Job #{ja.id}",
            "job_b": (jb.name or f"Job #{jb.id}") if jb else "—",
            "resource": "—",
            "window": _format_conflict_window(ja, jb),
            "job_a_id": ja.id,
            "job_b_id": jb.id if jb else None,
        })
        i += 2
    return payloads


def _format_conflict_window(job_a: Job, job_b: Job | None) -> str:
    """Format a date range string for the conflict template's
    `window` field.

    Called by:    _get_conflicts_for_dispatch (this file).
    Calls into:   nothing — pure formatting.
    Side effects: none.

    When only job_a is in scope (lone conflict), the window is its
    own start/end. When both are present, the window is the overlap
    (max start to min end), which is the slice the two jobs
    contend for.
    """
    if job_b is None:
        return f"{job_a.start_date.isoformat()} to {job_a.end_date.isoformat()}"
    start = max(job_a.start_date, job_b.start_date)
    end = min(job_a.end_date, job_b.end_date)
    if end < start:
        return (
            f"{job_a.start_date.isoformat()} to {job_a.end_date.isoformat()} "
            f"vs {job_b.start_date.isoformat()} to {job_b.end_date.isoformat()}"
        )
    return f"{start.isoformat()} to {end.isoformat()}"


def _compute_delay_alert_fields(
    job: Job,
    now: datetime,
    db: "Session",  # type: ignore[name-defined]
) -> dict[str, str]:
    """Compute the five fields the Meta-bound DELAY_ALERT_EN template
    expects from one delayed Job.

    Called by:    dispatch_delay_alert (this file).
    Calls into:   Job ORM (read-only) for the next-job lookup.
    Side effects: none.

    Template field semantics (best-effort for "delayed" within the
    Meta template's "ending soon" shape):
      - job_name      Job.name (or 'Job #<id>' fallback)
      - customer      Job.customer (or 'your customer' fallback)
      - time_remaining  human string: 'overdue by N day(s)' or 'past due'
      - progress        Job.status as displayed
      - next_job        the next job by start_date for the same tenant,
                        or '—' when none exists
    """
    today = now.date()
    overdue_days = (today - job.end_date).days if job.end_date else 0
    if overdue_days <= 0:
        time_remaining = "past due"
    elif overdue_days == 1:
        time_remaining = "overdue by 1 day"
    else:
        time_remaining = f"overdue by {overdue_days} days"

    next_job_row = (
        db.query(Job)
        .filter(
            Job.tenant_id == job.tenant_id,
            Job.id != job.id,
            Job.start_date.isnot(None),
            Job.start_date >= today,
            Job.status.notin_([
                "completed", "cancelled", "Completed", "Cancelled",
            ]),
        )
        .order_by(Job.start_date.asc(), Job.id.asc())
        .first()
    )
    next_job_name = (next_job_row.name if next_job_row else None) or "—"

    return {
        "job_name": job.name or f"Job #{job.id}",
        "customer": (job.customer or "your customer"),
        "time_remaining": time_remaining,
        "progress": (job.status or "—"),
        "next_job": next_job_name,
    }


def _compute_conflict_alert_fields(
    conflict_payload: dict[str, Any],
) -> dict[str, str]:
    """Decorate a conflict payload dict with the `next_step` field the
    CONFLICT_ALERT_EN template expects.

    Called by:    dispatch_conflict_alert (this file).
    Calls into:   nothing — pure dict construction.
    Side effects: none.

    `next_step` is a static suggestion today — surfacing the real
    "what should the owner do?" requires v6.4 scheduling intelligence
    that exposes conflict-resolution moves. Until then, the suggestion
    is "Review the schedule conflict in the desktop app."
    """
    return {
        "job_a": str(conflict_payload.get("job_a", "—")),
        "job_b": str(conflict_payload.get("job_b", "—")),
        "resource": str(conflict_payload.get("resource", "—")),
        "window": str(conflict_payload.get("window", "—")),
        "next_step": (
            "Review the schedule conflict in the desktop app."
        ),
    }


async def dispatch_delay_alert(
    tenant_id: int,
    now: datetime,
    db: "Session",  # type: ignore[name-defined]
    *,
    job_id: int | None,
) -> DispatchResult:
    """Send one delayed-job alert for a specific job to the tenant's
    top-tier WhatsApp recipients.

    Called by:    push_v2_tick at the legacy delay tick marks
                  (8/10/12/14/16/18/20 IST), the debug dispatch endpoint,
                  and tests.
    Calls into:   _compute_delay_alert_fields, message_formatters.DELAY_ALERT_EN,
                  _resolve_top_tier_recipients, _log_event,
                  _send_whatsapp_message.
    Side effects: writes events rows, commits, calls Meta send
                  (mock-aware via WHATSAPP_MOCK_MODE).

    No dedup. Consecutive ticks for the same job both emit
    push.delay_sent — matches legacy `check_delayed_jobs` behaviour
    (which also had no dedup). Spam fix tracked as a future release.

    Skip rules:
      - push_paused_until covers today → push.delay_skipped_paused
      - no top-tier recipient opted in to push_delay → push.delay_skipped_no_recipients

    Note: no morning_enabled / evening_enabled gate — delay alerts use
    their own `push_delay` alert_preferences key (default True for
    parity with legacy default-True opt-in).
    """
    from app.models.auth import Tenant  # local — avoid import cycle

    if job_id is None:
        return DispatchResult(
            success=False,
            tenant_id=tenant_id,
            kind="delay",
            error="dispatch_delay_alert requires job_id",
        )

    tenant = db.get(Tenant, tenant_id)
    if tenant is None:
        return DispatchResult(
            success=False,
            tenant_id=tenant_id,
            kind="delay",
            skip_reason="tenant_not_found",
            error=f"Tenant {tenant_id} not found",
        )

    job = db.get(Job, job_id)
    if job is None or job.tenant_id != tenant_id:
        return DispatchResult(
            success=False,
            tenant_id=tenant_id,
            kind="delay",
            error=f"Job {job_id} not found for tenant {tenant_id}",
        )

    config = resolve_push_config(tenant)
    scheduled_for = _scheduled_date_for(now, config.push_timezone)
    scheduled_for_str = scheduled_for.isoformat()
    now_str = now.isoformat()
    last_event_id: int | None = None

    # Paused gate.
    if config.push_paused_until and config.push_paused_until >= scheduled_for:
        row = _log_event(
            tenant_id=tenant_id,
            event_type=_EVENT_PUSH_DELAY_SKIPPED_PAUSED,
            payload={
                "scheduled_for_date": scheduled_for_str,
                "paused_until": config.push_paused_until.isoformat(),
                "now": now_str,
                "job_id": job_id,
            },
            db=db,
        )
        last_event_id = row.id
        db.commit()
        return DispatchResult(
            success=True, tenant_id=tenant_id, kind="delay",
            skip_reason="paused", event_id=last_event_id,
        )

    recipients = _resolve_top_tier_recipients(tenant_id, _ALERT_KEY_PUSH_DELAY, db)
    if not recipients:
        row = _log_event(
            tenant_id=tenant_id,
            event_type=_EVENT_PUSH_DELAY_SKIPPED_NO_RECIPIENTS,
            payload={
                "scheduled_for_date": scheduled_for_str,
                "now": now_str,
                "job_id": job_id,
            },
            db=db,
        )
        last_event_id = row.id
        db.commit()
        return DispatchResult(
            success=True, tenant_id=tenant_id, kind="delay",
            skip_reason="no_recipients", event_id=last_event_id,
        )

    fields = _compute_delay_alert_fields(job, now, db)
    rendered = message_formatters.DELAY_ALERT_EN.format(**fields)

    sent_count = 0
    last_error: str | None = None
    for r in recipients:
        try:
            await _send_whatsapp_message(r.phone_number, rendered)
            sent_count += 1
        except Exception as exc:  # noqa: BLE001
            last_error = str(exc) or exc.__class__.__name__
            row = _log_event(
                tenant_id=tenant_id,
                event_type=_EVENT_PUSH_DELAY_SEND_FAILED,
                payload={
                    "scheduled_for_date": scheduled_for_str,
                    "phone": r.phone_number,
                    "error": last_error,
                    "now": now_str,
                    "job_id": job_id,
                },
                db=db,
            )
            last_event_id = row.id
            _log.warning(
                "push.delay send_failed tenant=%s phone=****%s error=%s",
                tenant_id, r.phone_number[-4:], last_error,
            )

    if sent_count > 0:
        row = _log_event(
            tenant_id=tenant_id,
            event_type=_EVENT_PUSH_DELAY_SENT,
            payload={
                "scheduled_for_date": scheduled_for_str,
                "now": now_str,
                "recipients": [r.phone_number for r in recipients],
                "sent_count": sent_count,
                "rendered_message": rendered,
                "job_id": job_id,
                "fields": fields,
            },
            db=db,
        )
        last_event_id = row.id
    db.commit()

    return DispatchResult(
        success=sent_count > 0 or last_error is None,
        tenant_id=tenant_id,
        kind="delay",
        sent_count=sent_count,
        rendered_message=rendered,
        error=last_error,
        recipients=tuple(r.phone_number for r in recipients),
        event_id=last_event_id,
    )


async def dispatch_conflict_alert(
    tenant_id: int,
    now: datetime,
    db: "Session",  # type: ignore[name-defined]
    *,
    conflict_payload: dict | None,
) -> DispatchResult:
    """Send one scheduling-conflict alert for a specific conflict to the
    tenant's top-tier WhatsApp recipients.

    Called by:    push_v2_tick at the legacy conflict tick marks
                  (8:30 / 12:30 / 16:30 / 20:30 IST), the debug dispatch
                  endpoint, and tests.
    Calls into:   _compute_conflict_alert_fields,
                  message_formatters.CONFLICT_ALERT_EN,
                  _resolve_top_tier_recipients, _log_event,
                  _send_whatsapp_message.
    Side effects: writes events rows, commits, calls Meta send.

    No dedup. Skip rules mirror dispatch_delay_alert.
    """
    from app.models.auth import Tenant  # local — avoid import cycle

    if conflict_payload is None:
        return DispatchResult(
            success=False,
            tenant_id=tenant_id,
            kind="conflict",
            error="dispatch_conflict_alert requires conflict_payload",
        )

    tenant = db.get(Tenant, tenant_id)
    if tenant is None:
        return DispatchResult(
            success=False,
            tenant_id=tenant_id,
            kind="conflict",
            skip_reason="tenant_not_found",
            error=f"Tenant {tenant_id} not found",
        )

    config = resolve_push_config(tenant)
    scheduled_for = _scheduled_date_for(now, config.push_timezone)
    scheduled_for_str = scheduled_for.isoformat()
    now_str = now.isoformat()
    last_event_id: int | None = None

    if config.push_paused_until and config.push_paused_until >= scheduled_for:
        row = _log_event(
            tenant_id=tenant_id,
            event_type=_EVENT_PUSH_CONFLICT_SKIPPED_PAUSED,
            payload={
                "scheduled_for_date": scheduled_for_str,
                "paused_until": config.push_paused_until.isoformat(),
                "now": now_str,
                "conflict_payload": conflict_payload,
            },
            db=db,
        )
        last_event_id = row.id
        db.commit()
        return DispatchResult(
            success=True, tenant_id=tenant_id, kind="conflict",
            skip_reason="paused", event_id=last_event_id,
        )

    recipients = _resolve_top_tier_recipients(tenant_id, _ALERT_KEY_PUSH_CONFLICT, db)
    if not recipients:
        row = _log_event(
            tenant_id=tenant_id,
            event_type=_EVENT_PUSH_CONFLICT_SKIPPED_NO_RECIPIENTS,
            payload={
                "scheduled_for_date": scheduled_for_str,
                "now": now_str,
                "conflict_payload": conflict_payload,
            },
            db=db,
        )
        last_event_id = row.id
        db.commit()
        return DispatchResult(
            success=True, tenant_id=tenant_id, kind="conflict",
            skip_reason="no_recipients", event_id=last_event_id,
        )

    fields = _compute_conflict_alert_fields(conflict_payload)
    rendered = message_formatters.CONFLICT_ALERT_EN.format(**fields)

    sent_count = 0
    last_error: str | None = None
    for r in recipients:
        try:
            await _send_whatsapp_message(r.phone_number, rendered)
            sent_count += 1
        except Exception as exc:  # noqa: BLE001
            last_error = str(exc) or exc.__class__.__name__
            row = _log_event(
                tenant_id=tenant_id,
                event_type=_EVENT_PUSH_CONFLICT_SEND_FAILED,
                payload={
                    "scheduled_for_date": scheduled_for_str,
                    "phone": r.phone_number,
                    "error": last_error,
                    "now": now_str,
                    "conflict_payload": conflict_payload,
                },
                db=db,
            )
            last_event_id = row.id
            _log.warning(
                "push.conflict send_failed tenant=%s phone=****%s error=%s",
                tenant_id, r.phone_number[-4:], last_error,
            )

    if sent_count > 0:
        row = _log_event(
            tenant_id=tenant_id,
            event_type=_EVENT_PUSH_CONFLICT_SENT,
            payload={
                "scheduled_for_date": scheduled_for_str,
                "now": now_str,
                "recipients": [r.phone_number for r in recipients],
                "sent_count": sent_count,
                "rendered_message": rendered,
                "conflict_payload": conflict_payload,
                "fields": fields,
            },
            db=db,
        )
        last_event_id = row.id
    db.commit()

    return DispatchResult(
        success=sent_count > 0 or last_error is None,
        tenant_id=tenant_id,
        kind="conflict",
        sent_count=sent_count,
        rendered_message=rendered,
        error=last_error,
        recipients=tuple(r.phone_number for r in recipients),
        event_id=last_event_id,
    )
