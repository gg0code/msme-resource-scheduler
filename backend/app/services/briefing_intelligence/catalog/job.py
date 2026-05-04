# app/services/briefing_intelligence/catalog/job.py
# Branch: v5-whatsapp
#
# FILE PURPOSE
# Job-category signal evaluators for v6.3.11 pattern briefings.
# Session 2B implemented detect_delayed_jobs (spec B.3.delayed_jobs_count).
# Session 2C adds detect_no_progress (spec B.3.no_progress).
# detect_conflict_jobs is deferred per Q4 (source unidentified).
#
# WHO CALLS THIS FILE
# - app/services/briefing_intelligence/composer.py — both evaluators
#   are registered in ALL_DETECTORS.
# - tests/test_detect_delayed_jobs.py
# - tests/services/test_detect_no_progress.py
#
# WHAT THIS FILE CALLS
# - app/models/job.py — Job ORM (status, end_date, updated_at,
#   actual_start_at, is_locked).
# - app/services/briefing_intelligence/signals.py — SignalResult.
# - app/services/status_normalize.py — case-insensitive status_in().
#
# DESIGN NOTES
# - Status comparison is case-insensitive via status_in(). The status
#   column has both 'in_progress' (3 rows) and 'In Progress' (3 rows)
#   in production data — both must trigger no_progress, so the
#   evaluator filters in Python after a tenant-scoped scan.
# - detect_no_progress reads updated_at instead of actual_start_at
#   because actual_start_at is mostly NULL in production (Section
#   A.3). Combined trigger: status IN in_progress family AND
#   actual_start_at IS NULL AND updated_at < today - 3.
# - severity_score for delayed_jobs_count == count(delayed jobs).
#   For no_progress the score is also the count of stale jobs so the
#   escalation rule (D.5) treats new-job-entered as a fire-again.

import logging
from datetime import date, datetime, time, timedelta
from typing import Optional

from sqlalchemy.orm import Session

from app.models.job import Job
from app.services.briefing_intelligence.signals import SignalResult
from app.services.status_normalize import status_in

logger = logging.getLogger(__name__)

# Terminal statuses — case-insensitive match excludes these from the
# delayed list. Lower-case canonical form; comparison normalises the
# DB value before lookup.
TERMINAL_STATUSES: frozenset[str] = frozenset({"completed", "cancelled"})

# In-progress family — both casings observed in production (Section C).
IN_PROGRESS_STATUSES: frozenset[str] = frozenset({"in_progress", "in progress"})

SIGNAL_ID = "delayed_jobs_count"
CATEGORY = "job"
TIER = 1
CONFIDENCE = "high"
COOLDOWN_DAYS = 1

# detect_no_progress configuration (spec B.3.no_progress, tier 3).
NO_PROGRESS_SIGNAL_ID = "no_progress"
NO_PROGRESS_TIER = 3
NO_PROGRESS_CONFIDENCE = "low"
NO_PROGRESS_COOLDOWN_DAYS = 3
# Days since updated_at threshold. Spec says today - 3, treated as a
# strict-less-than: a job whose updated_at is exactly 3 days old does
# not qualify, matching the legacy "3 din se" output template.
NO_PROGRESS_STALE_DAYS = 3


def detect_delayed_jobs(
    tenant_id: int,
    today: date,
    db: Session,
) -> Optional[SignalResult]:
    """Detect jobs whose end_date has passed without a terminal status.

    Called by:    composer.compose_briefing via ALL_DETECTORS.
    Calls into:   Job ORM read (read-only).
    Side effects: none — pure read.

    Per spec B.3.delayed_jobs_count:
      - Trigger:   end_date < today AND status NOT IN terminal set
                   (case-insensitive). end_date IS NOT NULL.
      - Templates:
          1 job:   "{name} kal end hone wala tha, abhi tak chal raha hai."
          2-3:     "{j1}, {j2} aur {j3} sab delayed hai."
          4+:      "{N} jobs ab tak end nahi hue."
      - Tier 1, confidence high, cooldown 1 day, severity = count.

    Returns:
        SignalResult when there is at least one delayed job, otherwise
        None (the signal did not fire).
    """
    delayed_jobs: list[Job] = (
        db.query(Job)
        .filter(
            Job.tenant_id == tenant_id,
            Job.end_date.isnot(None),
            Job.end_date < today,
        )
        .order_by(Job.end_date.asc(), Job.id.asc())
        .all()
    )

    # Filter out terminal statuses in Python — case-insensitive,
    # tolerates None status defensively (treats None as non-terminal,
    # which is consistent with the legacy v5.10 behaviour).
    active_delayed: list[Job] = [
        j for j in delayed_jobs
        if (j.status or "").strip().lower() not in TERMINAL_STATUSES
    ]

    count = len(active_delayed)
    if count == 0:
        return None

    message = _format_delayed_message(active_delayed)
    message_en = _format_delayed_message_en(active_delayed)

    return SignalResult(
        signal_id=SIGNAL_ID,
        category=CATEGORY,
        tier=TIER,
        confidence=CONFIDENCE,
        subject_entity_type="tenant",
        subject_entity_id=None,
        severity_score=float(count),
        message_hi_en=message,
        message_en=message_en,
        cooldown_days=COOLDOWN_DAYS,
    )


def _format_delayed_message(jobs: list[Job]) -> str:
    """Pick the Hinglish template for delayed_jobs_count by list length.

    Called by:    detect_delayed_jobs (this file).
    Calls into:   nothing — pure string assembly.
    Side effects: none.

    Branches by count to match spec B.3:
      1 → name + "kal end hone wala tha"
      2-3 → comma-and join + "delayed hai"
      4+ → count-only fallback (no names — keeps the briefing terse).
    """
    n = len(jobs)
    if n == 1:
        return f"{jobs[0].name} kal end hone wala tha, abhi tak chal raha hai."
    if n in (2, 3):
        names = [j.name for j in jobs[:n]]
        head = ", ".join(names[:-1])
        return f"{head} aur {names[-1]} sab delayed hai."
    return f"{n} jobs ab tak end nahi hue."


def _format_delayed_message_en(jobs: list[Job]) -> str:
    """English mirror of _format_delayed_message.

    Called by:    detect_delayed_jobs (this file) — populates
                  SignalResult.message_en.
    Calls into:   nothing — pure string assembly.
    Side effects: none.
    """
    n = len(jobs)
    if n == 1:
        return f"{jobs[0].name} was due yesterday and is still running."
    if n in (2, 3):
        names = [j.name for j in jobs[:n]]
        head = ", ".join(names[:-1])
        return f"{head} and {names[-1]} are all delayed."
    return f"{n} jobs are past their end date."


# ---------------------------------------------------------------------------
# detect_no_progress (spec B.3.no_progress)
# ---------------------------------------------------------------------------

def detect_no_progress(
    tenant_id: int,
    today: date,
    db: Session,
) -> Optional[SignalResult]:
    """Detect in_progress jobs that have not been touched in N days.

    Tier: 3 (experimental).
    Confidence: low — actual_start_at is mostly NULL in production
        because the timer feature is rarely used (Section A.3 of the
        spec). Many "real" in-progress jobs would falsely trigger; the
        signal is gated to tier 3 so it surfaces only when no tier-1/2
        signals fill the slots.
    Data: jobs.status, jobs.actual_start_at, jobs.updated_at, jobs.is_locked.
    Suppression: skip is_locked=True (owner pinned the job deliberately).
    Spec: v6_3_11_signals_spec.md B.3 no_progress.

    Called by:    composer.compose_briefing via ALL_DETECTORS.
    Calls into:   Job ORM read, status_in(), pure datetime arithmetic.
    Side effects: none — pure read.

    Returns:
        SignalResult tagged at the tenant level (subject_entity_id=None)
        whose severity_score equals the count of stale jobs. None when
        no job satisfies the trigger.
    """
    stale_cutoff_date = today - timedelta(days=NO_PROGRESS_STALE_DAYS)
    # Compare against midnight at the cutoff so "older than 3 days"
    # means strictly older — a job updated yesterday at noon does not
    # qualify when stale_days=3, which matches the spec wording.
    stale_cutoff_dt = datetime.combine(stale_cutoff_date, time.min)

    candidates: list[Job] = (
        db.query(Job)
        .filter(
            Job.tenant_id == tenant_id,
            Job.is_locked.is_(False),
            Job.actual_start_at.is_(None),
        )
        .order_by(Job.updated_at.asc(), Job.id.asc())
        .all()
    )

    matching: list[Job] = []
    for j in candidates:
        if not status_in(j.status, IN_PROGRESS_STATUSES):
            continue
        if j.updated_at is None:
            continue
        # Strip tz-info to allow comparison under both naive (SQLite)
        # and aware (Postgres) datetime columns.
        ua = j.updated_at
        if ua.tzinfo is not None:
            ua = ua.replace(tzinfo=None)
        if ua < stale_cutoff_dt:
            matching.append(j)

    count = len(matching)
    if count == 0:
        return None

    return SignalResult(
        signal_id=NO_PROGRESS_SIGNAL_ID,
        category=CATEGORY,
        tier=NO_PROGRESS_TIER,
        confidence=NO_PROGRESS_CONFIDENCE,
        subject_entity_type="tenant",
        subject_entity_id=None,
        severity_score=float(count),
        message_hi_en=_format_no_progress_message(matching),
        message_en=_format_no_progress_message_en(matching),
        cooldown_days=NO_PROGRESS_COOLDOWN_DAYS,
    )


def _format_no_progress_message(jobs: list[Job]) -> str:
    """Hinglish template for stale in-progress jobs.

    Called by:    detect_no_progress (this file) — populates
                  SignalResult.message_hi_en.
    Calls into:   nothing — pure string assembly.
    Side effects: none.

    Uses the singular template ("{name} 3 din se in-progress hai") for
    one stale job and the count-only fallback for many. Names are
    omitted when the list grows past one because the briefing already
    surfaces the worst case via subject_entity_id.
    """
    n = len(jobs)
    if n == 1:
        return (
            f"{jobs[0].name} {NO_PROGRESS_STALE_DAYS} din se in-progress "
            f"hai par koi update nahi mila."
        )
    return (
        f"{n} jobs {NO_PROGRESS_STALE_DAYS}+ din se in-progress hai "
        f"par koi update nahi mila."
    )


def _format_no_progress_message_en(jobs: list[Job]) -> str:
    """English mirror of _format_no_progress_message.

    Called by:    detect_no_progress (this file) — populates
                  SignalResult.message_en.
    Calls into:   nothing — pure string assembly.
    Side effects: none.
    """
    n = len(jobs)
    if n == 1:
        return (
            f"{jobs[0].name} has been in progress for "
            f"{NO_PROGRESS_STALE_DAYS}+ days with no update."
        )
    return (
        f"{n} jobs have been in progress for {NO_PROGRESS_STALE_DAYS}+ "
        f"days with no update."
    )
