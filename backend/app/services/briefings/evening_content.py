# app/services/briefings/evening_content.py
# Branch: v5-whatsapp
#
# FILE PURPOSE
# Backward-looking evening-briefing content builder. Given a tenant and
# the current date in the tenant's timezone, returns a single WhatsApp-
# ready string covering: jobs completed today, attendance, blockers
# raised today, and the top item to watch for tomorrow.
#
# WHO CALLS THIS FILE
# - app/services/briefings/dispatcher.py - cron-fired and manual triggers.
# - tests/test_briefings.py              - service-direct assertions.
#
# WHAT THIS FILE CALLS
# - app/services/briefings/templates.py - locale strings + industry
#                                         labels (BUG-6 regression: never
#                                         branch on industry_type).
# - app/models/job.py, app/models/employee.py - SQLAlchemy ORM reads.
# - sqlalchemy core - no raw SQL.
#
# KEY DESIGN DECISIONS
# - Same 1000-char cap as the morning generator. Truncation strategy
#   identical to keep behaviour consistent across both content types.
# - "Top for tomorrow" picks the next-day job with the earliest
#   start_date (ties broken by id asc). When no tomorrow jobs exist,
#   the line is omitted instead of saying "nothing scheduled" - the
#   evening briefing should not nag.
# - "Hours logged" is intentionally NOT computed: the timer_log column
#   is JSON with no canonical schema across the v5.10/v5.15 lineage,
#   so claiming a number here would be misleading. The prompt mentions
#   it as a nice-to-have - we ship the safer subset and document the
#   deferral in the v6.3.4 handoff.
# - Idle-floor case (zero completed jobs and zero today-active jobs)
#   returns the dedicated idle template - still counts as delivered.

from datetime import date, timedelta
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.employee import Employee
from app.models.job import Job
from app.services.briefings.templates import (
    DEFAULT_LOCALE,
    Locale,
    industry_labels,
    pick_template,
)

MAX_BRIEFING_CHARS: int = 1000


def build_evening_briefing(
    tenant_id: int,
    industry_type: Optional[str],
    today: date,
    db: Session,
    locale: Locale = DEFAULT_LOCALE,
) -> str:
    """
    Build the backward-looking evening briefing for one tenant.

    Called by:    dispatcher.dispatch_briefing (kind='evening'),
                  dispatcher.manual_trigger_briefing (kind='evening').
    Calls into:   industry_labels, pick_template, _completed_today_count,
                  _active_employee_count, _delayed_job_count,
                  _top_for_tomorrow.
    Side effects: none - read-only.

    Args:
        tenant_id:     Multi-tenancy scope.
        industry_type: Tenant.industry_type. None falls back to printing
                       vocabulary.
        today:         Date the recap covers, computed in the tenant's
                       configured timezone.
        db:            Sync SQLAlchemy Session.
        locale:        'en' / 'hi' / 'hi-en'. Defaults to Hinglish.

    Returns:
        WhatsApp-ready string, ASCII-only, at most MAX_BRIEFING_CHARS.
        Idle-floor case returns the dedicated idle template.
    """
    labels = industry_labels(industry_type)

    completed_count = _completed_today_count(tenant_id, today, db)
    today_active_count = _today_job_count(tenant_id, today, db)
    attendance_count = _active_employee_count(tenant_id, db)
    blocker_count = _delayed_job_count(tenant_id, today, db)
    top_for_tomorrow = _top_for_tomorrow(tenant_id, today, db)

    if completed_count == 0 and today_active_count == 0:
        # Idle-floor template - no work today, no completions to report.
        idle = pick_template("evening_idle", locale).format(
            jobs_label=labels["jobs"],
        )
        return _truncate(idle)

    date_label = today.strftime("%d %b")
    header = pick_template("evening_header", locale).format(date=date_label)

    done_line = pick_template("evening_done_line", locale).format(
        job_label_caps=labels["jobs"].capitalize(),
        jobs_label=labels["jobs"],
        completed_count=completed_count,
    )

    attendance_line = pick_template("evening_attendance_line", locale).format(
        employee_label_caps=labels["employees"].capitalize(),
        employees_label=labels["employees"],
        attendance_count=attendance_count,
    )

    parts: list[str] = [header, "", done_line, attendance_line]

    if blocker_count > 0:
        parts.append(pick_template("evening_blocker_line", locale).format(
            blocker_count=blocker_count,
        ))

    if top_for_tomorrow is not None:
        parts.append("")
        parts.append(pick_template("evening_top_for_tomorrow_line", locale).format(
            top_for_tomorrow=top_for_tomorrow,
        ))

    body = "\n".join(parts)
    return _truncate(body)


# ---------------------------------------------------------------------------
# PRIVATE QUERY HELPERS
# ---------------------------------------------------------------------------

def _completed_today_count(tenant_id: int, today: date, db: Session) -> int:
    """
    Count jobs marked completed and last-updated today.

    Called by:    build_evening_briefing.
    Calls into:   SELECT COUNT(*) on Job with status in completed
                  variants AND date(updated_at) == today.
    Side effects: none.

    The Job model has no first-class completed_at column - the prompt
    brief notes this is a v5.10 carry-forward. updated_at::date is the
    closest proxy and matches the v5.10 dashboard count.
    """
    return int(
        db.execute(
            select(func.count(Job.id)).where(
                Job.tenant_id == tenant_id,
                Job.status.in_(["completed", "Completed"]),
                func.date(Job.updated_at) == today,
            )
        ).scalar() or 0
    )


def _today_job_count(tenant_id: int, today: date, db: Session) -> int:
    """
    Count jobs whose date range covers `today`. Used only to decide
    whether the idle-floor template should fire.

    Called by:    build_evening_briefing.
    Calls into:   SELECT COUNT(*) on Job.
    Side effects: none.
    """
    return int(
        db.execute(
            select(func.count(Job.id)).where(
                Job.tenant_id == tenant_id,
                Job.start_date <= today,
                Job.end_date >= today,
            )
        ).scalar() or 0
    )


def _active_employee_count(tenant_id: int, db: Session) -> int:
    """
    Active employees for the tenant - proxy for attendance.

    Called by:    build_evening_briefing.
    Calls into:   SELECT COUNT(*) on Employee.
    Side effects: none.

    Same heuristic as morning: the Employee model has no per-day
    attendance column at v6.3.4. The future attendance ledger (planned
    in v6.4) will replace this proxy with real per-day data.
    """
    return int(
        db.execute(
            select(func.count(Employee.id)).where(
                Employee.tenant_id == tenant_id,
                Employee.status == "active",
            )
        ).scalar() or 0
    )


def _delayed_job_count(tenant_id: int, today: date, db: Session) -> int:
    """
    Count jobs whose end_date has passed without a terminal status -
    the same blocker definition as the morning briefing.

    Called by:    build_evening_briefing.
    Calls into:   SELECT COUNT(*) on Job.
    Side effects: none.
    """
    return int(
        db.execute(
            select(func.count(Job.id)).where(
                Job.tenant_id == tenant_id,
                Job.end_date < today,
                Job.status.notin_([
                    "completed", "cancelled", "Completed", "Cancelled",
                ]),
            )
        ).scalar() or 0
    )


def _top_for_tomorrow(tenant_id: int, today: date, db: Session) -> Optional[str]:
    """
    Pick the single most relevant job to flag for tomorrow.

    Called by:    build_evening_briefing.
    Calls into:   SELECT on Job filtered by tomorrow's date range.
    Side effects: none.

    Returns:
        Job.name string when at least one job is scheduled to run
        tomorrow. None when the floor is idle tomorrow - the evening
        recap omits the line rather than nagging.

    Tie-break: earliest start_date asc, then earliest id asc - matches
    the morning briefing's deterministic ordering so "top tomorrow"
    today is the same job that headlines tomorrow's morning briefing.
    """
    tomorrow = today + timedelta(days=1)
    job = db.execute(
        select(Job)
        .where(
            Job.tenant_id == tenant_id,
            Job.start_date <= tomorrow,
            Job.end_date >= tomorrow,
            Job.status.notin_([
                "completed", "cancelled", "Completed", "Cancelled",
            ]),
        )
        .order_by(Job.start_date.asc(), Job.id.asc())
        .limit(1)
    ).scalars().first()
    return job.name if job is not None else None


def _truncate(text: str) -> str:
    """
    Hard-cap an evening briefing at MAX_BRIEFING_CHARS - same strategy
    as the morning generator. See morning_content._truncate for design
    notes; the implementation is duplicated here so each generator can
    evolve its truncation strategy independently if needed.

    Called by:    build_evening_briefing.
    Calls into:   nothing.
    Side effects: none.
    """
    if len(text) <= MAX_BRIEFING_CHARS:
        return text
    return text[: MAX_BRIEFING_CHARS - 4].rstrip() + " ..."
