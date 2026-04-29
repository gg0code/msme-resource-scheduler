# app/services/briefings/morning_content.py
# Branch: v5-whatsapp
#
# FILE PURPOSE
# Forward-looking morning-briefing content builder. Given a tenant and
# the current date in the tenant's timezone, returns a single WhatsApp-
# ready string covering: today's jobs, expected crew, and blockers.
# Industry vocabulary is supplied via app.services.briefings.templates;
# this module never branches control flow on industry_type.
#
# WHO CALLS THIS FILE
# - app/services/briefings/dispatcher.py - cron-fired and manual triggers.
# - tests/test_briefings.py              - service-direct assertions.
#
# WHAT THIS FILE CALLS
# - app/services/briefings/templates.py - locale strings + industry
#                                         labels.
# - app/models/job.py, app/models/employee.py - SQLAlchemy ORM reads.
# - sqlalchemy core (select, func) - no raw SQL.
#
# KEY DESIGN DECISIONS
# - Pure data + string assembly. No DB writes. No side effects beyond
#   the SELECTs.
# - Output capped at 1000 characters (SRS 6.28.4). The job-list section
#   is the only variable-length payload, so it is truncated first with
#   an "and N more" marker if needed; the header and totals remain.
# - Top 5 jobs by start_date asc, end_date asc as a deterministic
#   ordering. Anything beyond that is collapsed into the more-marker.
# - Idle-floor case (zero today's jobs) returns the dedicated idle
#   template - still counts as delivered per the prompt brief.
# - All queries scoped by tenant_id - mandatory per CLAUDE.md.

from datetime import date
from typing import Optional

from sqlalchemy import and_, func, select
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
MAX_JOB_LINES: int = 5


def build_morning_briefing(
    tenant_id: int,
    industry_type: Optional[str],
    today: date,
    db: Session,
    locale: Locale = DEFAULT_LOCALE,
) -> str:
    """
    Build the forward-looking morning briefing for one tenant.

    Called by:    dispatcher.dispatch_briefing (kind='morning'),
                  dispatcher.manual_trigger_briefing (kind='morning').
    Calls into:   industry_labels, pick_template, _today_jobs,
                  _active_employee_count, _delayed_job_count.
    Side effects: none - read-only DB queries.

    Args:
        tenant_id:     Multi-tenancy scope. Every SELECT filters on it.
        industry_type: Tenant.industry_type value. May be None for
                       legacy tenants - templates degrade to printing
                       vocabulary.
        today:         Date the briefing is for, computed in the
                       tenant's configured timezone by the dispatcher.
        db:            Sync SQLAlchemy Session. Never AsyncSession.
        locale:        'en' / 'hi' / 'hi-en'. Defaults to Hinglish.

    Returns:
        WhatsApp-ready string, ASCII-only, at most MAX_BRIEFING_CHARS.
        Idle-floor case returns the dedicated idle template - still
        non-empty and still counts as delivered.
    """
    labels = industry_labels(industry_type)

    today_jobs = _today_jobs(tenant_id, today, db)
    employee_count = _active_employee_count(tenant_id, db)
    blocker_count = _delayed_job_count(tenant_id, today, db)

    if not today_jobs:
        # Idle-floor template. Even an empty floor still gets a message.
        idle = pick_template("morning_idle", locale).format(
            jobs_label=labels["jobs"],
        )
        return _truncate(idle)

    # Header + summary line + (optional blockers) + job list.
    date_label = today.strftime("%d %b")
    header = pick_template("morning_header", locale).format(date=date_label)

    summary = pick_template("morning_jobs_line", locale).format(
        job_label_caps=labels["jobs"].capitalize(),
        today_count=len(today_jobs),
        employee_label=labels["employees"],
        employee_count=employee_count,
    )

    blocker_line = ""
    if blocker_count > 0:
        blocker_line = pick_template("morning_blocker_line", locale).format(
            blocker_count=blocker_count,
        )

    job_lines, more_marker = _format_job_list(today_jobs, locale)

    parts: list[str] = [header, "", summary]
    if blocker_line:
        parts.append(blocker_line)
    parts.append("")
    parts.extend(job_lines)
    if more_marker:
        parts.append(more_marker)

    body = "\n".join(parts)
    return _truncate(body)


# ---------------------------------------------------------------------------
# PRIVATE QUERY HELPERS
# ---------------------------------------------------------------------------

def _today_jobs(tenant_id: int, today: date, db: Session) -> list[Job]:
    """
    Return all jobs whose date range covers `today` for this tenant.

    Called by:    build_morning_briefing.
    Calls into:   SQLAlchemy SELECT on Job filtered by tenant + date
                  range, ordered by start_date asc then id asc for a
                  deterministic top-5 cut.
    Side effects: none - read only.
    """
    return list(
        db.execute(
            select(Job)
            .where(
                Job.tenant_id == tenant_id,
                Job.start_date <= today,
                Job.end_date >= today,
                Job.status.notin_([
                    "completed", "cancelled", "Completed", "Cancelled",
                ]),
            )
            .order_by(Job.start_date.asc(), Job.id.asc())
        ).scalars().all()
    )


def _active_employee_count(tenant_id: int, db: Session) -> int:
    """
    Count active employees for the tenant (proxy for expected crew).

    Called by:    build_morning_briefing.
    Calls into:   SELECT COUNT(*) on Employee filtered by tenant + active.
    Side effects: none.

    The Employee model uses 'active' (lowercase) as the canonical
    status string - matches the v5.10 _build_morning_briefing query.
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
    Count jobs whose end_date has passed without a terminal status.

    Called by:    build_morning_briefing.
    Calls into:   SELECT COUNT(*) on Job.
    Side effects: none.

    Mirrors the v5.10 delayed-jobs heuristic. Casing variants are
    included because legacy seed data used title-case statuses.
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


# ---------------------------------------------------------------------------
# FORMATTING HELPERS
# ---------------------------------------------------------------------------

def _format_job_list(
    jobs: list[Job],
    locale: Locale,
) -> tuple[list[str], str]:
    """
    Render the top-N job names as bullet lines, plus an "and N more"
    marker when the list was truncated.

    Called by:    build_morning_briefing.
    Calls into:   pick_template (for the more-marker only).
    Side effects: none.

    Returns:
        (lines, marker). `lines` is at most MAX_JOB_LINES entries.
        `marker` is '' when `len(jobs) <= MAX_JOB_LINES`, otherwise the
        localised "and N more" string with N = `len(jobs) - MAX_JOB_LINES`.
    """
    visible = jobs[:MAX_JOB_LINES]
    lines = [f"- {job.name}" for job in visible]
    remaining = len(jobs) - len(visible)
    if remaining <= 0:
        return lines, ""
    marker = pick_template("morning_more_marker", locale).format(
        n_more=remaining,
    )
    return lines, marker


def _truncate(text: str) -> str:
    """
    Hard-cap a briefing string at MAX_BRIEFING_CHARS.

    Called by:    build_morning_briefing.
    Calls into:   nothing.
    Side effects: none.

    Truncation strategy: cut to the cap minus the four-character
    ellipsis tail so the recipient sees a clear "..." indicator and
    knows the message was clipped. The morning generator is designed
    so the cap should rarely fire - the more-marker keeps the body
    short - but enforcing it here means a runaway data-set never
    breaks WhatsApp's per-message length budget.
    """
    if len(text) <= MAX_BRIEFING_CHARS:
        return text
    return text[: MAX_BRIEFING_CHARS - 4].rstrip() + " ..."
