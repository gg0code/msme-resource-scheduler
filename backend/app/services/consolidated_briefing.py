# app/services/consolidated_briefing.py
# Branch: v5-whatsapp
#
# FILE PURPOSE
# v6.3.19 morning-briefing flag/next_step selector. Picks the top
# blocker-class signal from a sorted SignalResult list and returns
# (flag_text, next_step_text) for rendering through the v6.3.18
# Meta-bound MORNING_BRIEFING templates.
#
# This file is the lookup-table-only slice of v6.3.19. The dispatcher
# rewrite, cascade resolver, migrations 033/034, and template registry
# wiring are deliberately deferred to follow-up prompts; nothing in
# the codebase imports this module yet.
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
